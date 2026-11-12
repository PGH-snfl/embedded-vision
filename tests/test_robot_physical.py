"""Test design/code consistency, not physical or electrical safety."""
import sys
import types

import pytest

from backend.design.robot_physical import robot_rover_design


def test_design_wiring_uses_real_hat_and_separate_supplies():
    design=robot_rover_design()
    assert not design['hardware_tested']
    parts={p['id']:p for p in design['parts']}
    assert '#2348' in parts['HAT1']['model']
    assert '#2939' in parts['CHASSIS']['model']
    connections={(c['from'],c['to']) for c in design['connections']}
    assert connections=={
        ('U1.GPIO40','HAT1.GPIO40'),('U1.USB_C','PS1.USB_C'),
        ('MOTOR_L.black','HAT1.M1.left'),('MOTOR_L.red','HAT1.M1.right'),
        ('MOTOR_R.black','HAT1.M2.left'),('MOTOR_R.red','HAT1.M2.right'),
        ('BAT1.red','HAT1.PWR.positive'),('BAT1.black','HAT1.PWR.negative')}
    assert '공통 접지' in design['board']['ground']
    assert all(c['id'] in {x['id'] for x in design['connections']} for c in design['connections'])
    assert 'UNKNOWN' in design['structure']['dimensions_status']


@pytest.mark.parametrize('command,expected',[
    ('forward',(0.5,0.5)),('backward',(-0.5,-0.5)),
    ('left',(0,0.5)),('right',(0.5,0)),('stop',(0,0))])
def test_generated_firmware_commands_and_cleanup(monkeypatch,command,expected):
    histories=[[],[]]
    class Motor:
        def __init__(self,history):self.history=history
        @property
        def throttle(self):return self.history[-1]
        @throttle.setter
        def throttle(self,value):self.history.append(value)
    class Kit:
        def __init__(self):self.motor1=Motor(histories[0]);self.motor2=Motor(histories[1])
    monkeypatch.setitem(sys.modules,'adafruit_motorkit',types.SimpleNamespace(MotorKit=Kit))
    import time
    monkeypatch.setattr(time,'sleep',lambda _:None)
    ns={'__name__':'test_robot_generated'}
    exec(compile(robot_rover_design()['code']['source'],'pi_rover.py','exec'),ns)
    ns['run'](command,0.1)
    assert (histories[0][0],histories[1][0])==expected
    assert (histories[0][-1],histories[1][-1])==(0,0)
    with pytest.raises(ValueError):ns['run'](command,2.1)
    with pytest.raises(ValueError):ns['run']('unknown',1)


def test_generated_firmware_stops_both_motors_when_interrupted(monkeypatch):
    state=[[],[]]
    class Motor:
        def __init__(self,index):self.index=index
        @property
        def throttle(self):return state[self.index][-1]
        @throttle.setter
        def throttle(self,value):state[self.index].append(value)
    class Kit:
        def __init__(self):self.motor1=Motor(0);self.motor2=Motor(1)
    monkeypatch.setitem(sys.modules,'adafruit_motorkit',types.SimpleNamespace(MotorKit=Kit))
    import time
    def interrupt(_):raise KeyboardInterrupt
    monkeypatch.setattr(time,'sleep',interrupt)
    ns={'__name__':'test_robot_generated'}
    exec(compile(robot_rover_design()['code']['source'],'pi_rover.py','exec'),ns)
    with pytest.raises(KeyboardInterrupt):ns['run']('forward',1)
    assert state==[[0.5,0],[0.5,0]]


def test_recipe_is_copied():
    changed=robot_rover_design();changed['parts'][0]['name']='변경'
    assert robot_rover_design()['parts'][0]['name']!='변경'

def test_default_motion_duration_matches_simulation_example():
    import ast
    source=robot_rover_design()['code']['source']
    module=ast.parse(source)
    run=next(node for node in module.body if isinstance(node,ast.FunctionDef) and node.name=='run')
    assert ast.literal_eval(run.args.defaults[0])==1.0
    assert '--seconds 1' in robot_rover_design()['code']['run']
