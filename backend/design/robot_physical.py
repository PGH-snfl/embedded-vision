"""Reviewed two-wheel rover design, not a reconstruction of photographed wiring.

The 3-D model and hypothetical driving do not prove real hardware function.
"""
from copy import deepcopy

PI='https://www.raspberrypi.com/documentation/computers/raspberry-pi.html'
HAT='https://www.adafruit.com/product/2348'
ROVER='https://www.adafruit.com/product/2939'
MOTOR='https://www.adafruit.com/product/2941'
GUIDE='https://learn.adafruit.com/simple-raspberry-pi-robot?view=all'
POWER='https://learn.adafruit.com/adafruit-dc-and-stepper-motor-hat-for-raspberry-pi/powering-motors'
SOFTWARE='https://learn.adafruit.com/adafruit-dc-and-stepper-motor-hat-for-raspberry-pi/installing-software'

CODE='''# 새 Raspberry Pi 4B + Adafruit Motor HAT 2륜 주행 예제
# 실제 GPIO/I2C와 모터를 제어합니다. 실물 시험 전입니다.
# 바퀴를 바닥에서 띄우고 모터 전원 스위치에 손이 닿는 상태로 시험하세요.
import argparse
import time
from adafruit_motorkit import MotorKit

# M1=왼쪽, M2=오른쪽. 실제 연결 방향에 따라 각 모터 부호 조정 필요.
COMMANDS = {
    "forward": (0.5, 0.5),
    "backward": (-0.5, -0.5),
    "left": (0.0, 0.5),
    "right": (0.5, 0.0),
    "stop": (0.0, 0.0),
}

def run(command, seconds=1.0):
    if command not in COMMANDS or not 0.0 <= seconds <= 2.0:
        raise ValueError("지원하는 명령과 0~2초를 입력하세요")
    kit = MotorKit()
    try:
        kit.motor1.throttle, kit.motor2.throttle = COMMANDS[command]
        time.sleep(seconds)
    finally:
        # 버스 오류 등으로 소프트웨어 정지가 실패할 수도 있으므로
        # 독립 모터 전원 스위치를 항상 사용할 수 있게 유지하세요.
        for motor in (kit.motor1, kit.motor2):
            try:
                motor.throttle = 0.0
            except Exception:
                pass

def main():
    parser = argparse.ArgumentParser(description="두 바퀴 저속 주행 시험")
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("--seconds", type=float, default=1.0)
    args = parser.parse_args()
    run(args.command, args.seconds)

if __name__ == "__main__":
    main()
'''

DESIGN={
 'id':'raspberry_pi_2wd_robot',
 'title':'Raspberry Pi · 2륜 이동 로봇 새 설계',
 'behavior':'전진·후진·좌회전·우회전·정지 명령을 실행합니다. 각 명령은 최대 2초 후 정지합니다.',
 'board':{'model':'Raspberry Pi 4 Model B','logic':'I²C: GPIO2/SDA 물리 3번, GPIO3/SCL 물리 5번','ground':'HAT 40핀 헤더로 공통 접지 연결'},
 'parts':[
  {'id':'U1','kind':'board','name':'라즈베리파이 보드','model':'Raspberry Pi 4 Model B','quantity':1,'note':'Raspberry Pi OS가 설치된 microSD, 화면 또는 원격 접속 수단 필요','source':PI},
  {'id':'HAT1','kind':'motor_driver','name':'모터 구동 보드','model':'Adafruit DC & Stepper Motor HAT #2348','quantity':1,'note':'미조립 키트는 제조사 지침에 따라 헤더와 단자대를 납땜해야 합니다. Pi 40핀에 장착합니다. 최대 1.2A 연속/채널, 모터 전원 권장 5–12V. 모터 정지 전류를 먼저 검증하세요.','source':HAT},
  {'id':'CHASSIS','kind':'chassis','name':'2륜 로봇 섀시 키트','model':'Adafruit Mini Robot Rover Kit #2939','quantity':1,'note':'키트에 DC 모터 2개, 바퀴 2개, 지지 바퀴와 섀시 포함. 4–6V 모터 사양 확인. 제조사 판매 상태는 변경될 수 있습니다.','source':ROVER},
  {'id':'MOTOR_L','kind':'motor','name':'왼쪽 DC 모터','model':'#2939에 포함된 #2941','quantity':1,'note':'별도 구매 수량에 중복하지 마세요. 무부하·기동·정지 전류는 확인 필요.','source':MOTOR},
  {'id':'MOTOR_R','kind':'motor','name':'오른쪽 DC 모터','model':'#2939에 포함된 #2941','quantity':1,'note':'별도 구매 수량에 중복하지 마세요. 무부하·기동·정지 전류는 확인 필요.','source':MOTOR},
  {'id':'BAT1','kind':'power','name':'모터 전원','model':'별도 5V 정전압 DC 전원, 3A 이상, 차단 스위치','quantity':1,'note':'모터 정격과 실제 기동/정지 전류를 확인하고 보호 기능을 적용하세요. Pi 전원과 분리합니다. 배터리 사용 시 5V 정전압 출력 확인.','source':POWER},
  {'id':'PS1','kind':'power','name':'Pi 전원','model':'Pi 4용 5.1V USB-C 전원','quantity':1,'note':'제조사 규격에 맞는 5.1V 3A Pi 전용 전원. 모터 전원과 분리합니다.','source':PI},
 ],
 'connections':[
  {'id':'C1','from':'U1.GPIO40','to':'HAT1.GPIO40','color':'green','description':'전원이 꺼진 상태에서 40핀 방향을 맞춰 HAT를 Pi 헤더에 장착합니다. I²C와 공통 접지는 헤더로 연결됩니다.'},
  {'id':'C2','from':'U1.USB_C','to':'PS1.USB_C','color':'black','description':'Pi USB-C에 Pi 전용 전원을 연결합니다. 모터 전원과 별개입니다.'},
  {'id':'C3','from':'MOTOR_L.black','to':'HAT1.M1.left','color':'black','description':'왼쪽 모터 검정선 → HAT M1 왼쪽 단자. 가운데 GND는 사용하지 않습니다.'},
  {'id':'C4','from':'MOTOR_L.red','to':'HAT1.M1.right','color':'red','description':'왼쪽 모터 빨강선 → HAT M1 오른쪽 단자.'},
  {'id':'C5','from':'MOTOR_R.black','to':'HAT1.M2.left','color':'black','description':'오른쪽 모터 검정선 → HAT M2 왼쪽 단자. 가운데 GND는 사용하지 않습니다.'},
  {'id':'C6','from':'MOTOR_R.red','to':'HAT1.M2.right','color':'red','description':'오른쪽 모터 빨강선 → HAT M2 오른쪽 단자.'},
  {'id':'C7','from':'BAT1.red','to':'HAT1.PWR.positive','color':'red','description':'별도 5V 모터 전원 + → HAT 전원 +.'},
  {'id':'C8','from':'BAT1.black','to':'HAT1.PWR.negative','color':'black','description':'별도 모터 전원 − → HAT 전원 −. 두 전원의 기준 접지는 40핀 헤더를 통해 공유됩니다.'},
 ],
 'steps':[
  {'id':'power','title':'전원 분리와 부품 확인','description':'Pi와 모터 전원을 모두 끄고 분리합니다. 모터 정격 4–6V, 전원 5V, HAT 전류 범위와 모터 실제 정지 전류를 확인하세요. 미확인인 경우 전원을 연결하지 않습니다.','highlight':['U1','HAT1','BAT1']},
  {'id':'chassis','title':'섀시와 바퀴 조립','description':'제조사 2WD 키트에 좌우 모터와 바퀴, 앞쪽 지지 바퀴를 장착합니다. 금속 섀시와 Pi 기판 사이에 절연 지지대를 사용합니다.','highlight':['CHASSIS','MOTOR_L','MOTOR_R']},
  {'id':'hat','title':'Pi와 모터 구동 보드 결합','description':'HAT가 미조립 키트라면 전원을 분리하고 제조사 조립 지침에 따라 헤더와 단자대를 납땜합니다. Pi와 HAT의 40핀 헤더 방향과 위치를 맞춰 결합하고 지지대로 고정합니다. I²C와 GND가 헤더에 포함되므로 별도 신호 점퍼를 꽂지 않습니다.','highlight':['U1','HAT1','C1']},
  {'id':'left','title':'왼쪽 모터 연결','description':'왼쪽 모터의 검정선과 빨강선을 각각 HAT M1 왼쪽·오른쪽 단자에 연결합니다. M1의 가운데 GND 단자는 비워 둡니다.','highlight':['MOTOR_L','HAT1','C3','C4']},
  {'id':'right','title':'오른쪽 모터 연결','description':'오른쪽 모터의 검정선과 빨강선을 각각 HAT M2 왼쪽·오른쪽 단자에 연결합니다. M2의 가운데 GND 단자는 비워 둡니다.','highlight':['MOTOR_R','HAT1','C5','C6']},
  {'id':'motor_power','title':'별도 모터 전원 연결','description':'모터 전원이 꺼진 상태에서 정전압 5V의 빨강 +와 검정 −를 HAT의 전원 +와 −에 각각 연결합니다. 극성과 실제 출력 전압을 측정해 확인하세요.','highlight':['BAT1','HAT1','C7','C8']},
  {'id':'pi_power','title':'Pi 전원과 소프트웨어 준비','description':'배선을 다시 확인한 뒤 Pi 전용 USB-C 전원을 연결합니다. 터미널에서 sudo raspi-config를 실행하고 Interface Options → I2C → Yes를 선택한 후 필요하면 재부팅합니다. 아래 안내대로 MotorKit을 설치합니다. 모터 전원은 아직 끈 상태로 둡니다.','highlight':['U1','PS1','C2']},
  {'id':'test','title':'바퀴를 띄워 방향 확인','description':'바퀴를 바닥에서 띄워 고정하고 모터 전원 스위치를 조작할 수 있게 한 뒤 짧게 실행합니다. 양 바퀴 방향이 다르면 전원을 끈 뒤 해당 모터의 선을 서로 바꿉니다. 충돌이나 추락을 자동 감지하지 않습니다.','highlight':['MOTOR_L','MOTOR_R','BAT1']},
 ],
 'code':{'filename':'pi_rover.py','language':'python','source':CODE,
   'dependencies':'Raspberry Pi OS, I²C 활성화, Adafruit Blinka와 CircuitPython MotorKit',
   'install':'python3 -m venv ~/rover-env --system-site-packages\n~/rover-env/bin/pip install adafruit-circuitpython-motorkit',
   'run':'~/rover-env/bin/python pi_rover.py forward --seconds 1',
   'commands':'forward 전진 · backward 후진 · left 좌회전 · right 우회전 · stop 정지. --seconds는 0~2초입니다.'},
 'structure':{'kind':'two_wheel_rover','description':'차체·바퀴·Pi·HAT의 단순화된 배치','dimensions_status':'UNKNOWN: 3D는 개략 시각화이며 실측·제조 치수가 아닙니다.'},
 'sources':[{'title':'Raspberry Pi 공식 문서','url':PI},{'title':'Adafruit Motor HAT 사양','url':HAT},{'title':'2WD 섀시와 모터 사양','url':ROVER},{'title':'모터 전원 가이드','url':POWER},{'title':'모터 배선과 기존 로봇 가이드','url':GUIDE},{'title':'MotorKit 설치','url':SOFTWARE}],
 'warnings':['이 설계는 사진의 원본 배선·원본 코드가 아니라 사용자가 선택한 2륜 주행 기능의 새 제안입니다.',
  '실제 부품·실제 전류·하드웨어·배선은 시험하지 않았으며 실물 안전성은 확인되지 않았습니다.',
  '장애물·낙하 감지와 자율주행 기능이 없습니다. 센서나 비상정지 하드웨어가 포함되지 않습니다.',
  'MotorKit 오류나 정전으로 코드의 정지 명령이 전달되지 않을 수 있습니다. 독립 모터 전원 스위치를 사용하세요.',
  '모터를 GPIO에 직접 연결하지 마세요. 3D 시각화는 실측 치수나 구조 검증이 아닙니다.'],
 'hardware_tested':False,
}

def robot_rover_design():
    return deepcopy(DESIGN)
