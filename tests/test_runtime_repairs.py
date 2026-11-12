from copy import deepcopy
from pathlib import Path
from backend.design.runtime_repairs import complete_missing_grounds
from backend.design.inventory import inventory_plan
from backend.design.recipes import new_graph
from test_functional_build import build_inputs,OrderedProvider

def test_repairs_only_missing_module_grounds_and_preserves_existing_design_choices():
    observed,raw,_=build_inputs('servo');original=deepcopy(raw['functional_build'])
    for wire in original['connections']:
        if 'M1.GND' in [wire['source'],wire['target']]:wire['source']='PS1.-';wire['target']='U1.GND'
    # Keep all other component connections and the program unchanged.
    before=deepcopy(original);fixed,repairs=complete_missing_grounds(original)
    assert original==before and fixed['firmware']==original['firmware']
    assert any(w['source']=='M1.GND' and w['target']=='U1.GND' for w in fixed['connections'])
    assert any(r['source']=='M1.GND' for r in repairs)
    again,second=complete_missing_grounds(fixed)
    assert second==[] and again==fixed

def test_wired_ground_is_not_reconnected_even_if_the_user_chose_a_different_net():
    _,raw,_=build_inputs('servo');design=raw['functional_build']
    for wire in design['connections']:
        if wire['source']=='M1.GND':wire['target']='U1.7'
    result,repairs=complete_missing_grounds(design)
    assert result==design and not repairs

def test_fresh_analysis_records_ground_completion_without_an_extra_model_call():
    observed,raw,_=build_inputs('servo')
    raw['functional_build']['connections']=[w for w in raw['functional_build']['connections'] if 'M1.GND' not in [w['source'],w['target']]]
    provider=OrderedProvider(observed,raw)
    plan=inventory_plan(new_graph('a'*32,'arduino_lcd')[0],[('image',Path('unused'))],provider)
    assert len(provider.calls)==2 and plan['simulation_repairs']
    assert plan['component_datasheet']['simulation_repairs']==plan['simulation_repairs']
    assert plan['functional_build']['firmware']==raw['functional_build']['firmware']
