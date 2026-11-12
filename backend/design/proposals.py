"""Compose supported designs from observed parts; never recover hidden wiring.

The vision model provides the inventory. This deterministic planner only uses
reviewed circuit recipes and keeps proposed specifications separate from evidence.
"""
import re
from .recipes import RECIPES,recipe_info,new_graph,LED_RECIPES,BUTTON_RECIPE,LIGHT_RECIPE
from ..firmware import firmware


def family(part):
    if part.kind!='board' or part.status=='UNKNOWN':return None
    text=' '.join([part.name,*part.model_candidates,*part.markings]).casefold()
    found=set()
    if re.search(r'\buno\b',text):found.add('uno')
    if 'esp32' in text:found.add('esp32')
    # Pico is a microcontroller board, while a Raspberry Pi 3/4/5 is a Linux
    # single-board computer. The manufacturer's name alone is not a model.
    if re.search(r'\bpico\b',text):found.add('pico')
    if re.search(r'\braspberry[\s_-]+pi\b(?![\s_-]*pico\b)',text):found.add('raspberry_pi')
    if re.search(r'\bnano\b|\bmega\b',text):found.add('other')
    # Supported UNO recipe requires R3/ATmega328P; ESP32 S/C variants have different pins.
    if re.search(r'\br4\b|esp32[- ]?[sch][236]',text):return None
    return next(iter(found)) if len(found)==1 else None


def light_sensor_candidate(part):
    if part.kind != 'sensor': return False
    text=' '.join([part.name,*part.model_candidates,*part.markings]).casefold()
    return bool(re.search(r'photoresistor|\bldr\b|light.?sensor|조도|광.?센서|광저항',text))


def compatible(part,recipe,slot):
    if part.status=='UNKNOWN' or part.kind!=slot['kind']:return False
    if part.kind=='board':return family(part)==('esp32' if recipe=='esp32_led_button' else 'uno')
    if part.kind=='sensor' and recipe==LIGHT_RECIPE:
        text=' '.join([part.name,*part.model_candidates,*part.markings]).casefold()
        # A bare two-pin LDR is not the three-pin virtual module.  Generic
        # sensor labels also do not prove the module's physical interface.
        is_module=bool(re.search(r'\bmodule\b|\bbreakout\b|모듈',text))
        bare=bool(re.search(r'\b2\s*[- ]?\s*pin\b|2\s*핀|두\s*핀|단독|단품',text))
        return light_sensor_candidate(part) and is_module and not bare
    if part.kind=='display':
        text=' '.join([part.name,*part.model_candidates,*part.markings]).casefold()
        return 'lcd' in text and not re.search(r'i2c|i²c|oled|spi',text)
    return True


def propose(inventory,function_kind=None,allow_completion=False):
    recipes=recipe_info();candidates=[];rejected=[]
    boards=[p for p in inventory.parts if p.kind=='board']
    for key,r in recipes.items():
        assigned={};used={};reason=None
        # A function hypothesis can require a newly chosen sensor even when
        # the photograph cannot identify it. Never silently force light control
        # onto an unrelated sensor or other behavior.
        if key==LIGHT_RECIPE and function_kind!='light_led' and not any(light_sensor_candidate(p) for p in inventory.parts):
            rejected.append({'recipe':key,'name':r['name'],'reason':'조도 기능이나 조도 센서 후보를 확인하지 못했습니다.'});continue
        for ref,slot in r['slots'].items():
            matches=[p for p in inventory.parts if compatible(p,key,slot) and used.get(p.id,0)<p.quantity]
            if ref=='U1' and len(matches)!=1 and key not in LED_RECIPES | {BUTTON_RECIPE,LIGHT_RECIPE} and not allow_completion:
                reason='호환 보드 후보가 없거나 여러 개여서 보드를 하나로 선택할 수 없습니다.';break
            part=matches[0] if matches and not (ref=='U1' and len(matches)!=1) else None
            if not part and ref in r['required_observed'] and not allow_completion:
                reason=f'{ref}: 필요한 핵심 부품을 사진에서 식별하지 못했습니다.';break
            assigned[ref]=part.id if part else None
            if part:used[part.id]=used.get(part.id,0)+1
        if reason:
            rejected.append({'recipe':key,'name':r['name'],'reason':reason});continue
        graph,_=new_graph('0'*32,key)
        added=[ref for ref,p in assigned.items() if p is None]
        replacements=[]
        if key==LIGHT_RECIPE and assigned.get('S1') is None:
            sensor_candidates=[p.id for p in inventory.parts if light_sensor_candidate(p)]
            seen='사진의 센서 후보와 3핀 모듈은 같은 부품으로 확인되지 않았습니다. ' if sensor_candidates else '사진에서 호환되는 센서 모듈을 확인하지 못했습니다. '
            replacements=[{'reference':'S1','candidate_ids':sensor_candidates,
                'reason':seen+'이 새 회로에는 VCC·GND·AO 3핀 조도 센서 모듈을 별도로 준비하세요. 2핀 광저항은 그대로 연결할 수 없습니다.'}]
        leftovers=[{'id':p.id,'name':p.name,'quantity':p.quantity-used.get(p.id,0),
           'role':'assembly' if p.kind=='breadboard' or '점퍼' in p.name or 'jumper' in p.name.casefold() else 'unused',
           'reason':'미식별 부품은 새 회로에 사용하지 않습니다.' if p.status=='UNKNOWN' else '회로에 배정하지 않은 잔여 부품·준비물입니다.'}
           for p in inventory.parts if p.quantity>used.get(p.id,0)]
        candidates.append({'recipe':key,'name':r['name'],'behavior':r['behavior'],'assignments':assigned,
            'added_parts':added,'replacements':replacements,'remaining_parts':leftovers,'allows_inferred_parts':allow_completion,
            'reason':('사진 보드 모델을 확정하지 않고 시뮬레이션용 UNO R3를 새로 선정했습니다.' if assigned['U1'] is None else '관측 보드 후보와 사용 가능한 부품 수량에 맞춰 구성했습니다.'),
            'simulation_notice':('새 설계는 VCC/GND/AO 3핀 가상 조도 센서 모듈을 사용합니다. 2핀 광저항과는 다릅니다. 실제 모듈의 정격·핀·출력 방향·임계값을 확인해야 합니다.' if key==LIGHT_RECIPE else 'UNO R3 · 16×2 병렬 LCD · 10kΩ 가변저항 · 220Ω은 새 설계 사양입니다. 실물 LCD의 핀·전압과 백라이트 정격은 확인이 필요합니다.' if key=='arduino_lcd' else 'UNO R3 · 적색 LED · 220Ω은 새 설계 사양입니다. 사진 속 보드·LED 모델과 저항값을 확정한 결과가 아닙니다.' if key in LED_RECIPES | {BUTTON_RECIPE,LIGHT_RECIPE} else ''),
            'simulator_supported':key in LED_RECIPES | {BUTTON_RECIPE,LIGHT_RECIPE,'arduino_lcd'} or key=='arduino_voltage_divider', 
            'specifications':{ref:{'name':s['name'],'value':s['value'],'source':s['source'],'note':s['note']} for ref,s in r['slots'].items()},
            'connections':[{'from':w.from_terminal,'to':w.to_terminal} for w in graph.links],
            'firmware':firmware(graph),
            'review_required':True,'hardware_verified':False,'original_wiring_reused':False})
    # Prefer fewer new purchases, then greater use of observed components.
    candidates.sort(key=lambda p:(len(p['added_parts']),-sum(v is not None for v in p['assignments'].values()),p['recipe']))
    return {'policy':'observed-parts-reviewed-recipes-v1','recommended':candidates[0]['recipe'] if candidates else None,
       'boards':[{'id':p.id,'name':p.name,'family':family(p),'status':p.status} for p in boards],
       'proposals':candidates,'unavailable':rejected,
       'notice':'새 기능·배선·값은 설계 제안입니다. 사진 속 원래 기능을 복원한 결과가 아니며, 실물 모델·정격 확인 전에는 조립 확정이 아닙니다.'}
