"""Control-plane records. All resource lookups require a workspace ID.

SQLite/WAL is the single-host adapter; the API/worker contract does not depend
on a shared process or an in-memory task dictionary.
"""
import hashlib
import hmac
import json
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager


class Limited(Exception):
    pass


class Stale(Exception):
    pass


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000)
    return salt + ":" + derived.hex()


class Repository:
    def __init__(self, settings):
        self.settings = settings
        settings.data.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = settings.data / "control.sqlite3"
        with self.connect() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS members(workspace TEXT,user TEXT,role TEXT NOT NULL,PRIMARY KEY(workspace,user));
                CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user TEXT,csrf TEXT,expires REAL);
                CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT,created REAL);
                CREATE INDEX IF NOT EXISTS attempts_ip ON login_attempts(ip,created);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,workspace TEXT NOT NULL,actor TEXT NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,lease REAL,result TEXT,idempotency TEXT,fingerprint TEXT);
                CREATE UNIQUE INDEX IF NOT EXISTS job_idempotency ON jobs(workspace,actor,idempotency) WHERE idempotency IS NOT NULL;
                CREATE INDEX IF NOT EXISTS job_queue ON jobs(status,created);
                CREATE TABLE IF NOT EXISTS drafts(workspace TEXT,project TEXT,draft TEXT,revision INTEGER NOT NULL,payload TEXT NOT NULL,actor TEXT NOT NULL,updated REAL NOT NULL,PRIMARY KEY(workspace,project,draft));
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,workspace TEXT,actor TEXT,action TEXT,resource TEXT,created REAL);
                CREATE TABLE IF NOT EXISTS workers(id TEXT PRIMARY KEY,updated REAL,model_ready INTEGER);
                CREATE TABLE IF NOT EXISTS local_preview(singleton INTEGER PRIMARY KEY CHECK(singleton=1),user TEXT NOT NULL,workspace TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self, write=False):
        c = sqlite3.connect(self.db, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA foreign_keys=ON")
            if write:
                c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def provision(self, email, password, workspace):
        email = email.strip().lower()
        if not 3 <= len(email) <= 254 or "@" not in email or len(password) < 12 or len(password) > 256:
            raise ValueError("이메일과 12~256자 비밀번호가 필요합니다.")
        if not workspace.strip() or len(workspace) > 100:
            raise ValueError("작업공간 이름은 1~100자입니다.")
        uid, wid = uuid.uuid4().hex, uuid.uuid4().hex
        encoded = password_hash(password)
        with self.connect(True) as c:
            c.execute("INSERT INTO users(id,email,password) VALUES(?,?,?)", (uid, email, encoded))
            c.execute("INSERT INTO workspaces VALUES(?,?)", (wid, workspace))
            c.execute("INSERT INTO members VALUES(?,?,?)", (wid, uid, "owner"))
        return uid, wid

    def preview_identity(self):
        """A persistent internal actor/workspace; never impersonate an existing account."""
        with self.connect(True) as c:
            row = c.execute("SELECT user,workspace FROM local_preview WHERE singleton=1").fetchone()
            if row is None:
                uid, wid = uuid.uuid4().hex, uuid.uuid4().hex
                # No usable login credentials are issued for this internal actor.
                encoded = password_hash(secrets.token_urlsafe(48))
                c.execute("INSERT INTO users(id,email,password) VALUES(?,?,?)",(uid,"preview-"+uid+"@local.invalid",encoded))
                c.execute("INSERT INTO workspaces VALUES(?,?)",(wid,"기본 작업공간"))
                c.execute("INSERT INTO members VALUES(?,?,?)",(wid,uid,"owner"))
                c.execute("INSERT INTO local_preview VALUES(1,?,?)",(uid,wid))
            else:
                uid, wid = row["user"], row["workspace"]
        return {"user":uid,"workspace":wid,"email":"로그인 없이 사용 중","csrf":""}

    def add_workspace(self, uid, name):
        wid = uuid.uuid4().hex
        with self.connect(True) as c:
            c.execute("INSERT INTO workspaces VALUES(?,?)", (wid, name))
            c.execute("INSERT INTO members VALUES(?,?,?)", (wid, uid, "owner"))
        return wid

    def login(self, email, password, ip):
        now = time.time()
        with self.connect(True) as c:
            c.execute("DELETE FROM login_attempts WHERE created<?", (now-300,))
            if c.execute("SELECT COUNT(*) FROM login_attempts WHERE ip=?", (ip,)).fetchone()[0] >= 12:
                raise Limited("로그인 시도가 많습니다. 5분 뒤 다시 시도하세요.")
            c.execute("INSERT INTO login_attempts VALUES(?,?)", (ip, now))
            row = c.execute("SELECT * FROM users WHERE email=? AND enabled=1", (email.strip().lower(),)).fetchone()
        encoded = row["password"] if row else "00"*16 + ":" + "00"*32
        salt, _ = encoded.split(":")
        valid = hmac.compare_digest(password_hash(password, salt), encoded)
        if not row or not valid:
            return None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connect(True) as c:
            c.execute("DELETE FROM sessions WHERE expires<?", (now,))
            c.execute("INSERT INTO sessions VALUES(?,?,?,?)", (digest(token), row["id"], digest(csrf), now+self.settings.session_seconds))
        return token, csrf

    def session(self, token):
        if not token:
            return None
        with self.connect() as c:
            row = c.execute("SELECT s.user,s.csrf,u.email FROM sessions s JOIN users u ON u.id=s.user WHERE s.token=? AND s.expires>? AND u.enabled=1", (digest(token), time.time())).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.connect(True) as c:
            c.execute("DELETE FROM sessions WHERE token=?", (digest(token),))

    def workspaces(self, uid):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT w.id,w.name,m.role FROM workspaces w JOIN members m ON m.workspace=w.id WHERE m.user=? ORDER BY w.name", (uid,))]

    def role(self, wid, uid):
        with self.connect() as c:
            row = c.execute("SELECT role FROM members WHERE workspace=? AND user=?", (wid, uid)).fetchone()
        return row[0] if row else None

    def audit(self, wid, uid, action, resource):
        with self.connect(True) as c:
            c.execute("INSERT INTO audit(workspace,actor,action,resource,created) VALUES(?,?,?,?,?)", (wid, uid, action, resource[:200], time.time()))

    def enqueue(self, wid, uid, kind, payload, key=None, job_id=None):
        now, jid = time.time(), job_id or uuid.uuid4().hex
        body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        fingerprint = digest(kind+":"+body)
        with self.connect(True) as c:
            if key:
                old = c.execute("SELECT * FROM jobs WHERE workspace=? AND actor=? AND idempotency=?", (wid, uid, key)).fetchone()
                if old:
                    if old["fingerprint"] != fingerprint:
                        raise Stale("같은 Idempotency-Key로 다른 작업을 제출할 수 없습니다.")
                    return dict(old)
            if c.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= 128:
                raise Limited("서버 작업 대기열이 가득 찼습니다.")
            if c.execute("SELECT COUNT(*) FROM jobs WHERE workspace=? AND status IN ('queued','running')", (wid,)).fetchone()[0] >= self.settings.max_pending:
                raise Limited("작업공간의 대기열이 가득 찼습니다.")
            if c.execute("SELECT COUNT(*) FROM jobs WHERE workspace=? AND created>?", (wid, now-86400)).fetchone()[0] >= self.settings.daily_jobs:
                raise Limited("작업공간의 일일 작업 한도에 도달했습니다.")
            c.execute("INSERT INTO jobs(id,workspace,actor,kind,payload,status,created,updated,idempotency,fingerprint) VALUES(?,?,?,?,?,'queued',?,?,?,?)", (jid,wid,uid,kind,body,now,now,key,fingerprint))
        return self.job(wid, jid)

    def job(self, wid, jid):
        with self.connect(True) as c:
            c.execute("UPDATE jobs SET status='interrupted',updated=? WHERE workspace=? AND id=? AND status='running' AND lease<?", (time.time(),wid,jid,time.time()))
            row = c.execute("SELECT * FROM jobs WHERE workspace=? AND id=?", (wid, jid)).fetchone()
        return dict(row) if row else None

    def claim(self):
        now = time.time()
        with self.connect(True) as c:
            # Never replay possibly billed model/tool calls after a worker disappears.
            c.execute("UPDATE jobs SET status='interrupted',updated=? WHERE status='running' AND lease<?", (now,now))
            row = c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:
                return None
            c.execute("UPDATE jobs SET status='running',updated=?,lease=? WHERE id=?", (now,now+120,row["id"]))
        return dict(row)

    def heartbeat(self, jid):
        with self.connect(True) as c:
            c.execute("UPDATE jobs SET lease=?,updated=? WHERE id=? AND status='running'", (time.time()+120,time.time(),jid))

    def worker_heartbeat(self, worker_id, model_ready):
        with self.connect(True) as c:
            c.execute("INSERT INTO workers VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,model_ready=excluded.model_ready",(worker_id,time.time(),int(model_ready)))

    def worker_status(self):
        with self.connect() as c:
            rows = c.execute("SELECT model_ready FROM workers WHERE updated>?",(time.time()-45,)).fetchall()
        return {"ready":bool(rows),"model_ready":any(row[0] for row in rows)}

    def finish(self, jid, result, failed=False):
        with self.connect(True) as c:
            c.execute("UPDATE jobs SET status=?,result=?,updated=?,lease=NULL WHERE id=? AND status='running'", ("failed" if failed else "done",json.dumps(result,ensure_ascii=False),time.time(),jid))

    @staticmethod
    def cleanup_project_records(conn, wid, project):
        """Delete only control records explicitly tied to this project."""
        conn.execute('DELETE FROM drafts WHERE workspace=? AND project=?',(wid,project))
        target='/api/projects/'+project
        for row in conn.execute('SELECT id,payload FROM jobs WHERE workspace=?',(wid,)).fetchall():
            try: payload=json.loads(row['payload'])
            except (ValueError,TypeError): continue
            path=payload.get('path','') if isinstance(payload,dict) else ''
            if isinstance(payload,dict) and (payload.get('project')==project or (isinstance(path,str) and (path == target or path.startswith(target+'/')))):
                conn.execute('DELETE FROM jobs WHERE id=?',(row['id'],))

    def draft(self, wid, project, draft):
        with self.connect() as c:
            row = c.execute("SELECT revision,payload,updated FROM drafts WHERE workspace=? AND project=? AND draft=?", (wid,project,draft)).fetchone()
        return {"revision":row["revision"],"payload":json.loads(row["payload"]),"updated":row["updated"]} if row else {"revision":0,"payload":None}

    def save_draft(self, wid, uid, project, draft, expected, payload):
        with self.connect(True) as c:
            row = c.execute("SELECT revision FROM drafts WHERE workspace=? AND project=? AND draft=?", (wid,project,draft)).fetchone()
            current = row[0] if row else 0
            if current != expected:
                raise Stale("다른 탭/사용자가 저장했습니다. 파일로 보관한 뒤 다시 열어주세요.")
            c.execute("INSERT INTO drafts VALUES(?,?,?,?,?,?,?) ON CONFLICT(workspace,project,draft) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,actor=excluded.actor,updated=excluded.updated", (wid,project,draft,current+1,json.dumps(payload,ensure_ascii=False),uid,time.time()))
        return {"revision":current+1}
