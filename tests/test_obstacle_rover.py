import json
import subprocess
from pathlib import Path

from backend.design.obstacle_rover import obstacle_rover_design, export_obstacle_project
from backend.workbench.server import CompileRequest, compile_edit

ROOT = Path(__file__).resolve().parents[1]


def test_obstacle_design_and_editable_project_are_consistent():
    design=obstacle_rover_design()
    project=export_obstacle_project()
    assert design['simulation_kind']=='obstacle_rover'
    assert not design['hardware_tested']
    assert project['activeBoardId']=='U1'
    assert project['fileGroups']['group-U1'][0]['content']==design['code']['source']
    expected={(w['from'],w['to']) for w in design['connections']}
    actual={(w['start']['componentId']+'.'+w['start']['pinName'],w['end']['componentId']+'.'+w['end']['pinName']) for w in project['wires']}
    assert expected==actual
    assert {('U1.9','S1.TRIG'),('U1.10','S1.ECHO'),('BAT.-','U1.GND'),('U2.OUT1','M1.+'),('U2.OUT3','M2.+')}<=actual
    assert 'visual' in project['embeddedVision']['simulation_notice'] or '시각' in project['embeddedVision']['simulation_notice']


def test_obstacle_arduino_code_compiles():
    result=compile_edit(CompileRequest(files=[{'name':'sketch.ino','content':obstacle_rover_design()['code']['source']}]))
    assert result['hex_content'].startswith(':')


def test_obstacle_controller_sequence_and_sensor_failure():
    module=(ROOT/'frontend/rover-src/obstacle-control.js').read_text()
    script=module.replace('export function','function')+'''
const c=createObstacleController();
const result=[c.step(50,0),c.step(20,50),c.step(20,449),c.step(20,450),c.step(20,1049),c.step(20,1050),c.step(null,1060),c.step(50,1070)];
process.stdout.write(JSON.stringify(result));
'''
    proc=subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)
    assert json.loads(proc.stdout)==['forward','backward','backward','left','left','forward','stop','forward']


def test_generated_code_executes_motor_sequence_with_mock_sensor(tmp_path):
    # Run the very same sketch logic against a small mock Arduino runtime.
    # This checks commanded pins, not the physical robot or an AVR emulator.
    harness = r'''
#include <cassert>
using byte=unsigned char;
const int LOW=0,HIGH=1,INPUT=0,OUTPUT=1;
unsigned long clock_ms=0, echo_us=0;
int pins[20]={}, speeds[20]={};
struct SerialMock { void begin(int){} void print(const char*){} void println(long){} } Serial;
void pinMode(int,int){} void digitalWrite(int pin,int value){pins[pin]=value;}
void analogWrite(int pin,int value){speeds[pin]=value;}
void delayMicroseconds(int){} void delay(int){} unsigned long millis(){return clock_ms;}
unsigned long pulseIn(int,int,unsigned long){return echo_us;}
''' + obstacle_rover_design()['code']['source'] + r'''
int main(){
 setup(); echo_us=3000; clock_ms=0; loop();
 assert(pins[2]==1 && pins[3]==0 && pins[4]==1 && pins[7]==0);
 echo_us=1000; clock_ms=100; loop();
 assert(pins[2]==0 && pins[3]==1 && pins[4]==0 && pins[7]==1);
 clock_ms=500; loop();
 assert(pins[2]==0 && pins[3]==1 && pins[4]==1 && pins[7]==0);
 clock_ms=1100; loop();
 assert(pins[2]==1 && pins[3]==0 && pins[4]==1 && pins[7]==0);
 echo_us=0; clock_ms=1200; loop();
 assert(speeds[5]==0 && speeds[6]==0);
}
'''
    source=tmp_path/'test.cpp'
    source.write_text(harness)
    subprocess.run(['g++','-std=c++11',str(source),'-o',str(tmp_path/'sketch')],check=True,capture_output=True,text=True)
    subprocess.run([str(tmp_path/'sketch')],check=True,capture_output=True,text=True)
