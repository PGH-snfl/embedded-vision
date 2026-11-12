"""Small MCP stdio client; isolated subprocess, fixed tools, no model-supplied commands."""
import json, os, queue, shutil, signal, subprocess, threading, time
from pathlib import Path

ALLOWED = {'kicad_get_version','kicad_get_server_info','kicad_create_new_project',
           'sch_build_circuit','export_netlist','run_erc','export_sch_svg'}
REQUIRED = {'kicad_create_new_project','sch_build_circuit','export_netlist','run_erc'}

class McpSession:
    def __init__(self, root, timeout=90):
        self.root=Path(root).resolve(); self.timeout=timeout; self.seq=0; self.events=queue.Queue(); self.proc=None
    def __enter__(self):
        executable=shutil.which('uvx')
        if not executable: raise RuntimeError('uvx/KiCad MCP 런타임을 찾을 수 없습니다.')
        self.root.mkdir(parents=True,exist_ok=True)
        env={k:v for k,v in os.environ.items() if not k.startswith('KICAD_MCP_') and k!='OPENAI_API_KEY'}
        env.update(KICAD_MCP_WORKSPACE_ROOT=str(self.root),KICAD_MCP_PROFILE='full',KICAD_MCP_OPERATING_MODE='write')
        self.log=open(self.root/'mcp-stderr.log','a')
        self.proc=subprocess.Popen([executable,'--offline','kicad-mcp-pro'],cwd=self.root,env=env,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,text=True,bufsize=1,start_new_session=True)
        def reader():
            try:
                for line in self.proc.stdout:
                    try:self.events.put(json.loads(line))
                    except json.JSONDecodeError:continue
            finally:self.events.put({'transport_closed':True})
        threading.Thread(target=reader,daemon=True).start()
        try:
            self.request('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'embedded-vision','version':'0.4'}})
            self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
            self.tools={}; cursor=None
            while True:
                page=self.request('tools/list',{'cursor':cursor} if cursor else {})
                self.tools.update({t['name']:t for t in page['tools']})
                cursor=page.get('nextCursor')
                if not cursor:break
            return self
        except Exception:
            self.__exit__(None,None,None);raise
    def send(self,payload):
        self.proc.stdin.write(json.dumps(payload)+'\n');self.proc.stdin.flush()
    def request(self,method,params):
        self.seq+=1; rid=self.seq
        self.send({'jsonrpc':'2.0','id':rid,'method':method,'params':params})
        deadline=time.monotonic()+self.timeout
        while True:
            try:item=self.events.get(timeout=max(.001,deadline-time.monotonic()))
            except queue.Empty:raise RuntimeError('KiCad MCP 응답 시간 초과; 실행 상태를 확인하세요.') from None
            if item.get('transport_closed'):raise RuntimeError('KiCad MCP 연결이 종료되었습니다. mcp-stderr.log 확인 필요')
            if item.get('id')==rid and ('result' in item or 'error' in item):
                if 'error' in item:raise RuntimeError('KiCad MCP protocol error: '+str(item['error'].get('message',''))[:250])
                return item['result']
            if 'id' in item and 'method' in item:
                self.send({'jsonrpc':'2.0','id':item['id'],'error':{'code':-32601,'message':'Client requests not supported'}})
    def call(self,name,args):
        if name not in ALLOWED or name not in self.tools:raise RuntimeError('허용되지 않거나 없는 MCP 도구: '+name)
        result=self.request('tools/call',{'name':name,'arguments':args})
        if result.get('isError'):raise RuntimeError('KiCad MCP 도구 실패: '+name)
        # Some server tools return failure as prose instead of isError.
        texts='\n'.join(c.get('text','') for c in result.get('content',[]) if c.get('type')=='text')
        if any(s in texts.lower() for s in ['refusing to','export failed','error executing tool','permission denied']):
            raise RuntimeError('KiCad MCP 작업 실패: '+name+' / '+texts[:300])
        return result
    def __exit__(self,*args):
        if self.proc:
            if self.proc.poll() is None:
                os.killpg(self.proc.pid,signal.SIGTERM)
                try:self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(self.proc.pid,signal.SIGKILL);self.proc.wait(timeout=5)
            self.proc.stdin.close();self.proc.stdout.close()
        if hasattr(self,'log'):self.log.close()

def probe(root):
    with McpSession(root,timeout=30) as mcp:
        missing=sorted(REQUIRED-set(mcp.tools))
        version=mcp.call('kicad_get_version',{})
        return {'connected':True,'required_tools':sorted(REQUIRED),'missing_tools':missing,
                'tools_ready':not missing,'version':version,'live_gui_verified':False}
