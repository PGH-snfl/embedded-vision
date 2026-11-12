"""OpenAI native local Skills adapter with a bounded virtual shell.

Only the mounted manifest and the declared crop helper are exposed. No model
command is forwarded to subprocess, an operating-system shell or a network.
"""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shlex
import time

from ..vision.component_crops import crop_image
from .models import Region

SKILL_ROOT=Path(__file__).resolve().parents[2]/'data/agent-skills/embedded-system-inspection'
VIRTUAL_ROOT='/workspace/skills/embedded-system-inspection'
DESCRIPTION='Inspect embedded-system photos by listing visible components, zooming original image regions, reviewing each candidate and checking omissions before circuit design.'


def skill_manifest():
    text=(SKILL_ROOT/'SKILL.md').read_text()
    return {'name':'embedded-system-inspection','version':'1','sha256':hashlib.sha256(text.encode()).hexdigest(),
            'description':DESCRIPTION,'path':VIRTUAL_ROOT},text


class InspectionBudget:
    def __init__(self,max_calls=16,seconds=720):
        self.max_calls=max_calls;self.calls=0;self.deadline=time.monotonic()+seconds
    def charge(self):
        if self.calls>=self.max_calls or time.monotonic()>=self.deadline:
            raise RuntimeError('부품 확대 검토의 호출·시간 한도에 도달했습니다. 자동으로 추가 호출하지 않습니다.')
        self.calls+=1
        return max(.1,min(240,self.deadline-time.monotonic()))


class InspectionRuntime:
    def __init__(self,assets,budget=None):
        self.assets=dict(assets);self.budget=budget or InspectionBudget()
        self.metadata,self.instructions=skill_manifest();self.events=[];self.extra_crops=[]
    def tool(self):
        return {'type':'shell','environment':{'type':'local','skills':[
            {k:self.metadata[k] for k in ['name','description','path']}]}}
    def execute(self,call):
        if not isinstance(call.get('call_id'),str) or not 1<=len(call['call_id'])<=200:raise RuntimeError('스킬 호출 ID가 잘못되었습니다.')
        action=call.get('action',{})
        commands=action.get('commands',[])
        requested_limit=action.get('max_output_length')
        if requested_limit is not None and (type(requested_limit) is not int or not 0<=requested_limit<=2147483647):
            raise RuntimeError('스킬 출력 길이 요청이 잘못되었습니다.')
        if not isinstance(commands,list) or not 1<=len(commands)<=2 or any(not isinstance(c,str) or len(c)>1600 for c in commands):
            raise RuntimeError('스킬 도구 요청의 형식 또는 명령 수가 잘못되었습니다.')
        output=[];images=[]
        for command in commands:
            try:
                words=shlex.split(command)
                if words==['cat',VIRTUAL_ROOT+'/SKILL.md']:
                    stdout=self.instructions;kind='read_skill'
                elif len(words)==12 and words[:2]==['python3',VIRTUAL_ROOT+'/scripts/crop.py'] and words[2]=='--asset' and words[4]=='--part' and words[6]=='--box':
                    if len(self.extra_crops)>=4:raise ValueError('추가 확대 한도 4개를 넘었습니다.')
                    asset,part=words[3],words[5]
                    if asset not in self.assets or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}',part):raise ValueError('등록 입력만 확대할 수 있습니다.')
                    region=Region(asset_id=asset,**dict(zip(['x0','y0','x1','y1'],map(float,words[7:11]))))
                    # Reject trailing options as well as shell syntax.
                    if words[11]!='--original':raise ValueError('원본 확대만 허용합니다.')
                    raw,meta=crop_image(self.assets[asset],region)
                    meta.update(crop_id='TOOL'+str(len(self.extra_crops)+1),part_ids=[part],purpose='agent_requested_zoom')
                    self.extra_crops.append(meta);stdout=json.dumps(meta,ensure_ascii=False);kind='crop'
                    images.extend([{'type':'input_text','text':'원본 추가 확대 '+meta['crop_id']+' · '+part},
                                   {'type':'input_image','image_url':'data:image/jpeg;base64,'+base64.b64encode(raw).decode(),'detail':'high'}])
                else:raise ValueError('스킬 읽기와 등록 입력 확대만 허용합니다.')
                output.append({'stdout':stdout,'stderr':'','outcome':{'type':'exit','exit_code':0}})
                self.events.append({'operation':kind,'allowed':True})
            except (ValueError,TypeError,OSError):
                output.append({'stdout':'','stderr':'허용되지 않거나 유효하지 않은 스킬 요청입니다.','outcome':{'type':'exit','exit_code':1}})
                self.events.append({'operation':'denied','allowed':False})
        # Responses validates equality with the originating shell_call.action.
        # Keep our own output cap separate from the value echoed to the API.
        remaining=min(12000,requested_limit) if requested_limit is not None else 12000
        for item in output:
            for key in ['stdout','stderr']:
                item[key]=item[key][:remaining];remaining-=len(item[key])
        response={'type':'shell_call_output','call_id':call['call_id'],'output':output}
        if 'max_output_length' in action:response['max_output_length']=requested_limit
        return [response,*([{'role':'user','content':images}] if images else [])]
    def report(self):
        return {**deepcopy(self.metadata),'binding':'responses_shell_local','tool_events':deepcopy(self.events),
                'extra_crops':deepcopy(self.extra_crops),'http_calls':self.budget.calls,'max_http_calls':self.budget.max_calls}
