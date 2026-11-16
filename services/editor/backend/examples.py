"""Local, reviewed UNO lessons; no photo analysis, model calls or user data writes."""
from copy import deepcopy
import hashlib
import json

from shared.paths import EDITOR_ROOT

LESSONS_FILE=EDITOR_ROOT/'data/arduino-lessons.json'


def lesson_specs():
    return json.loads(LESSONS_FILE.read_text(encoding='utf-8'))['lessons']


def lesson_catalog():
    return [{k:item[k] for k in ['id','title','level','summary']} | {'board':'Arduino UNO','runtime':'local'}
            for item in lesson_specs()]


def lesson_project(lesson_id):
    from backend.design.recipes import new_graph
    from backend.workbench.export import export_project
    specs=next((x for x in lesson_specs() if x['id']==lesson_id),None)
    if specs is None:raise KeyError(lesson_id)
    guide=deepcopy(specs)
    graph,_=new_graph(hashlib.sha256(lesson_id.encode()).hexdigest()[:32],guide['recipe'])
    function={'summary':guide['summary'],'display_text':guide.get('display_text')}
    project=export_project(graph,{'function':function})
    if guide['recipe']=='arduino_lcd':
        next(p for p in project['components'] if p['id']=='LCD1')['properties']['color']='white'
    names={'breadboard':'830구 빵판','led':'빨간색 LED','pushbutton-6mm':'누름 버튼',
           'photoresistor-sensor':'아날로그 조도 센서 모듈','lcd1602':'16×2 LCD (병렬형)',
           'potentiometer':'가변저항 10 kΩ'}
    guide['materials']=[{'ref':'U1','name':'Arduino UNO R3','quantity':1}]
    for part in project['components']:
        name=('저항 '+str(part['properties']['value'])+' Ω') if part['metadataId']=='resistor' else names[part['metadataId']]
        guide['materials'].append({'ref':part['id'],'name':name,'quantity':1})
    guide['jumper_count']=sum(not w.get('bb') for w in project['wires'])
    guide['version']=1
    project['name']=guide['title']+' · Arduino UNO'
    project['boards'][0]['name']='Arduino UNO R3'
    project['embeddedVision'].update(
        standalone=True,analysis_origin='',design_origin='editor_lesson',
        source_graph_sha256=hashlib.sha256(graph.model_dump_json().encode()).hexdigest(),
        inventory_plan='editor-lesson-'+lesson_id,function_version='lesson-v2',
        learning_guide=guide,standalone_notice='따라 하기용 내장 예제입니다. 회로·배선·코드를 함께 제공합니다.')
    return project
