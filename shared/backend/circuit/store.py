"""SQLite optimistic revisions: stale browser tabs cannot overwrite newer edits."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .schema import Graph


class Conflict(Exception):
    pass


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.db = root / "projects.sqlite3"
        with self.connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS revisions (project TEXT, revision INTEGER, body TEXT, note TEXT, created TEXT, PRIMARY KEY(project, revision))")
            conn.execute("CREATE TABLE IF NOT EXISTS rover_structures (project TEXT NOT NULL, plan TEXT NOT NULL, function_version TEXT NOT NULL, graph_sha256 TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(project, plan, function_version))")
            conn.execute("CREATE TABLE IF NOT EXISTS rover_circuits (project TEXT NOT NULL, plan TEXT NOT NULL, function_version TEXT NOT NULL, graph_sha256 TEXT NOT NULL, revision INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(project, plan, function_version))")

    def connect(self):
        return sqlite3.connect(self.db, timeout=10)

    def list(self):
        with self.connect() as conn:
            rows = conn.execute("SELECT body FROM revisions r WHERE revision=(SELECT MAX(revision) FROM revisions WHERE project=r.project) ORDER BY created DESC").fetchall()
        return [{"project_id": g["project_id"], "title": g["title"], "revision": g["revision"], "mode": g["mode"]} for (body,) in rows for g in [json.loads(body)]]

    def get(self, project: str, revision: int | None = None):
        with self.connect() as conn:
            if revision is None:
                row = conn.execute("SELECT body FROM revisions WHERE project=? ORDER BY revision DESC LIMIT 1", (project,)).fetchone()
            else:
                row = conn.execute("SELECT body FROM revisions WHERE project=? AND revision=?", (project, revision)).fetchone()
        if row is None:
            raise KeyError(project)
        return Graph.model_validate_json(row[0])

    def save(self, graph: Graph, expected: int, note: str):
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            current = conn.execute("SELECT MAX(revision) FROM revisions WHERE project=?", (graph.project_id,)).fetchone()[0] or 0
            if current != expected:
                raise Conflict(f"Expected revision {expected}, current {current}")
            if current:
                old = self.get(graph.project_id)
                if graph.assets[:len(old.assets)] != old.assets or graph.evidence[:len(old.evidence)] != old.evidence:
                    raise ValueError("Original assets and observations are immutable")
                # Preserve identity and provenance of the project.
                if graph.mode != old.mode:
                    raise ValueError("Project mode is immutable")
                if graph.wire_reviews[:len(old.wire_reviews)] != old.wire_reviews:
                    raise ValueError("Cross-view review history is immutable")
            updated = graph.model_copy(update={"revision": current + 1})
            # Revalidate even if callers used model_copy.
            updated = Graph.model_validate(updated.model_dump())
            conn.execute("INSERT INTO revisions VALUES (?, ?, ?, ?, ?)",
                         (updated.project_id, updated.revision, updated.model_dump_json(), note, datetime.now(timezone.utc).isoformat()))
        return updated

    def history(self, project):
        with self.connect() as conn:
            rows = conn.execute("SELECT revision,note,created FROM revisions WHERE project=? ORDER BY revision DESC", (project,)).fetchall()
        return [dict(revision=r, note=n, created=c) for r, n, c in rows]
