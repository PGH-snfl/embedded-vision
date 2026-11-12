"""Consistency checks only: these do not establish real-board operation."""
import sys
import types

from backend.design.pi_physical import pi_button_led_design


def test_pi_button_led_breadboard_wiring_has_no_shared_hole_or_short():
    design=pi_button_led_design()
    parts={p['id']:p for p in design['parts']}
    rows={}
    parent={}
    def find(node):
        parent.setdefault(node,node)
        if parent[node]!=node:parent[node]=find(parent[node])
        return parent[node]
    def join(a,b):parent[find(a)]=find(b)
    def addhole(hole):
        col,row=hole[0],int(hole[1:])
        assert col in 'ABCDEFGHIJ' and 1<=row<=30
        # A-E and F-J are electrically separate groups on each row.
        group=('left' if col in 'ABCDE' else 'right',row)
        if group in rows:join(hole,rows[group])
        else:rows[group]=hole
    occupied=[]
    for part in parts.values():
        for terminal in part['holes']:
            hole=terminal['hole'];occupied.append(hole);addhole(hole)
            join(part['id']+'.'+terminal['terminal'],hole)
    for wire in design['connections']:
        for endpoint in (wire['from'],wire['to']):
            if not endpoint.startswith('U1.'):
                occupied.append(endpoint);addhole(endpoint)
        join(wire['from'],wire['to'])
    assert len(occupied)==len(set(occupied)), 'Each physical lead uses a distinct hole'
    same=lambda a,b:find(a)==find(b)
    assert same('U1.P11','R1.1') and same('R1.2','D1.A')
    assert same('D1.K','U1.P6') and same('U1.P6','SW1.gnd_black')
    assert same('U1.P13','SW1.signal_white') and same('U1.P1','SW1.power_red')
    assert len({find(f'U1.P{i}') for i in (1,6,11,13)})==4
    assert {pin['physical']:pin['bcm'] for pin in design['board']['pins']}=={1:None,6:None,11:17,13:27}


def test_generated_pi_code_reacts_to_fake_button_and_cleans_up(monkeypatch):
    state={'values':[],'sleep_count':0,'closed':[]}
    class FakeLED:
        def __init__(self,pin,initial_value):
            assert (pin,initial_value)==(17,False)
        @property
        def value(self):return state['values'][-1]
        @value.setter
        def value(self,value):state['values'].append(value)
        def off(self):state['off']=True
        def close(self):state['closed'].append('led')
    class FakeButton:
        def __init__(self,pin,pull_up):
            assert (pin,pull_up)==(27,True)
            self.presses=iter([False,True,False])
        @property
        def is_pressed(self):return next(self.presses)
        def close(self):state['closed'].append('button')
    def fake_sleep(_):
        state['sleep_count']+=1
        if state['sleep_count']==3:raise KeyboardInterrupt
    monkeypatch.setitem(sys.modules,'gpiozero',types.SimpleNamespace(LED=FakeLED,Button=FakeButton))
    import time
    monkeypatch.setattr(time,'sleep',fake_sleep)
    namespace={'__name__':'test_generated_code'}
    exec(compile(pi_button_led_design()['code']['source'],'pi_button_led.py','exec'),namespace)
    namespace['main']()
    assert state['values']==[False,True,False]
    assert state['off'] and set(state['closed'])=={'led','button'}


def test_recipe_is_independent_copy_and_limits_claims():
    first=pi_button_led_design();first['parts'][0]['model']='changed'
    second=pi_button_led_design()
    assert second['parts'][0]['model']!='changed'
    assert second['hardware_tested'] is False
    assert any('원본' in text for text in second['warnings'])
