import copy
import pytest
from backend.design.recipes import new_graph,LED_RECIPES
from backend.workbench.export import export_project
from backend.workbench.breadboard import hole,projected_nets,BB_Y

@pytest.mark.parametrize('recipe',sorted(LED_RECIPES|{'arduino_voltage_divider'}))
def test_breadboard_no_shared_holes_and_pin_net_equivalence(recipe):
    g,_=new_graph('a'*32,recipe);before=g.model_dump_json();p=export_project(g)
    assert g.model_dump_json()==before
    endpoints=[e['pinName'] for w in p['wires'] for e in [w['start'],w['end']] if e['componentId']=='BB1']
    assert len(endpoints)==len(set(endpoints))
    assert len([w for w in p['wires'] if w.get('bb')])==4
    assert len(projected_nets(p['wires']))==3
    assert p['components'][0]['metadataId']=='breadboard'
    assert hole('63t.a')['x']>hole('1t.a')['x']
    assert hole('1t.a')['y']==BB_Y+6+48
    assert p['embeddedVision']['assembly']['layout_version']=='full-breadboard-v2'
    # A move to the opposite five-hole strip breaks connectivity, never joins through the trench.
    bad=copy.deepcopy(p['wires']);bad[0]['end']['pinName']='5b.f'
    assert projected_nets(bad)!=projected_nets(p['wires'])

@pytest.mark.parametrize('name',['0t.a','64t.b','5t.f','2b.a'])
def test_invalid_hole_rejected(name):
    with pytest.raises(ValueError):hole(name)
