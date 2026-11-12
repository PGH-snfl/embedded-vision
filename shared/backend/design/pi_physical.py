"""A reviewed *new* Raspberry Pi 4B button/LED design; not recovered wiring.

Only use after the user chooses the exact button_led design goal. The photo's
hidden functionality, part ratings and compatibility are not established.
"""
from copy import deepcopy

PI='https://www.raspberrypi.com/documentation/computers/raspberry-pi.html'
LED='https://www.kingbrightusa.com/images/catalog/SPEC/WP7113ID.pdf'
BUTTON='https://www.adafruit.com/product/4431'
GPIOZERO='https://gpiozero.readthedocs.io/en/stable/api_input.html#button'

CODE='''# Raspberry Pi 4B: 버튼을 누르는 동안 LED 켜기 (BCM 번호)
# 실제 GPIO를 사용합니다. 전원을 끈 상태에서 안내된 배선을 먼저 완성하세요.
from gpiozero import LED, Button
from time import sleep

def main():
    led = LED(17, initial_value=False)
    button = Button(27, pull_up=True)
    try:
        while True:
            led.value = button.is_pressed
            sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        led.off()
        button.close()
        led.close()

if __name__ == '__main__':
    main()
'''

DESIGN={
 'id':'raspberry_pi_4b_button_led',
 'title':'Raspberry Pi 4B · 버튼으로 LED 켜기',
 'behavior':'버튼을 누르는 동안 빨간 LED가 켜지고, 놓으면 꺼집니다.',
 'board':{'model':'Raspberry Pi 4 Model B (40핀 헤더)', 'gpio_voltage':'3.3 V',
   'pins':[{'name':'3V3','physical':1,'bcm':None},{'name':'GND','physical':6,'bcm':None},
           {'name':'GPIO17','physical':11,'bcm':17},{'name':'GPIO27','physical':13,'bcm':27}]},
 'parts':[
   {'id':'U1','kind':'board','name':'Raspberry Pi 4 Model B','model':'Raspberry Pi 4B, 40핀','quantity':1,'note':'Raspberry Pi OS가 설치된 microSD와 전용 전원 장치가 필요합니다. Pico가 아닙니다.','holes':[],'source':PI},
   {'id':'BB1','kind':'breadboard','name':'무납땜 브레드보드','model':'2.54 mm, A–E / F–J 분리형','quantity':1,'note':'행 1, 5, 6, 14, 16, 18을 사용합니다.','holes':[],'source':''},
   {'id':'R1','kind':'resistor','name':'저항','model':'1 kΩ, 허용오차 5% 이내, 0.25 W 이상, 축형','quantity':1,'note':'극성이 없습니다. LED 직렬 전류 제한용입니다.','holes':[{'terminal':'1','hole':'B1'},{'terminal':'2','hole':'B5'}],'source':''},
   {'id':'D1','kind':'led','name':'빨간 LED','model':'Kingbright WP7113ID','quantity':1,'note':'양극 A는 긴 다리, 음극 K는 짧은 다리/평평한 면입니다. 실물과 자료를 대조하세요.','holes':[{'terminal':'A','hole':'A5'},{'terminal':'K','hole':'A6'}],'source':LED},
   {'id':'SW1','kind':'button','name':'버튼 모듈','model':'Adafruit STEMMA Wired Tactile Push-Button #4431','quantity':1,'note':'동봉된 JST 3핀 수–헤더 케이블 사용: 흰색=신호, 검정=GND, 빨강=3V3. 버튼 모듈을 빵판 구멍에 억지로 꽂지 않습니다.','holes':[{'terminal':'signal_white','hole':'A14'},{'terminal':'gnd_black','hole':'A16'},{'terminal':'power_red','hole':'A18'}],'source':BUTTON},
   {'id':'WIRE','kind':'jumper_wire','name':'점퍼선','model':'보드 측 암–빵판 측 수 4개와 빵판 수–수 1개','quantity':5,'note':'모듈 케이블은 버튼에 포함된 3핀 케이블입니다.','holes':[],'source':''},
 ],
 'breadboard':{'type':'half_size','rows':30,'columns':'ABCDEFGHIJ','groups':['A-E','F-J'],
   'holes_note':'같은 숫자 행의 A–E 다섯 구멍은 서로 연결됩니다. 중앙 홈 반대쪽 F–J는 분리되어 있습니다. 전원 레일은 사용하지 않습니다.'},
 'connections':[
   {'id':'W1','from':'U1.P11','to':'A1','color':'orange','description':'물리 11번 GPIO17 → A1'},
   {'id':'W2','from':'U1.P6','to':'B6','color':'black','description':'물리 6번 GND → B6'},
   {'id':'W3','from':'U1.P13','to':'B14','color':'blue','description':'물리 13번 GPIO27 → B14'},
   {'id':'W4','from':'B16','to':'C6','color':'black','description':'버튼 GND가 있는 B16 → 공통 접지 C6'},
   {'id':'W5','from':'U1.P1','to':'B18','color':'red','description':'물리 1번 3V3 → B18'},
 ],
 'steps':[
  {'id':'power','title':'전원을 끄고 보드 방향 확인','description':'Raspberry Pi를 종료하고 전원 케이블을 분리하세요. 40핀의 물리 1번과 2번은 끝에 나란히 있으며 홀수 번호가 한쪽 줄입니다. 핀 번호는 GPIO 번호와 다릅니다.','highlight':['U1']},
  {'id':'resistor_led','title':'저항과 LED 꽂기','description':'1 kΩ 저항 양쪽을 B1과 B5에 꽂습니다. LED의 긴 다리 A(양극)는 A5, 짧은 다리 K(음극)는 A6에 꽂습니다. A5와 B5는 같은 행이므로 저항과 LED가 직렬 연결됩니다.','highlight':['R1','D1']},
  {'id':'led_wire','title':'LED 전원과 접지 연결','description':'주황 점퍼선의 양 끝을 Pi 물리 11번 GPIO17과 A1에 연결합니다. 검정 점퍼선의 양 끝을 Pi 물리 6번 GND와 B6에 연결합니다.','highlight':['W1','W2']},
  {'id':'button_module','title':'버튼 모듈 케이블 꽂기','description':'동봉된 3핀 케이블을 버튼 모듈에 연결합니다. 반대쪽 흰색 단자를 A14, 검정 단자를 A16, 빨강 단자를 A18에 꽂습니다. 선 색과 모듈 기능을 제조사 표기와 대조하세요.','highlight':['SW1']},
  {'id':'button_signal','title':'버튼 신호와 접지 연결','description':'파랑 점퍼선의 양 끝을 Pi 물리 13번 GPIO27과 B14에 꽂습니다. 검정 점퍼선의 양 끝을 B16과 C6에 꽂습니다.','highlight':['W3','W4']},
  {'id':'button_power','title':'버튼 모듈에 3.3V 연결','description':'빨강 점퍼선의 양 끝을 Pi 물리 1번 3V3과 B18에 연결합니다. 5V 핀을 사용하지 마세요.','highlight':['W5']},
  {'id':'inspect','title':'배선 확인 후 전원 켜기','description':'전원이 꺼진 상태에서 표시한 구멍, LED 극성, 저항값과 Pi 물리 핀 번호를 대조하세요. 배선 완료 후 전원을 연결합니다.','highlight':['U1','R1','D1','SW1']},
  {'id':'run','title':'코드 실행과 버튼 시험','description':'Raspberry Pi OS에서 아래 Python 파일을 실행하세요. 버튼을 누를 때만 LED가 켜지고 놓으면 꺼지는지 확인합니다. 종료는 Ctrl+C입니다.','highlight':['SW1','D1']},
 ],
 'code':{'filename':'pi_button_led.py','language':'python','source':CODE,'dependencies':'Raspberry Pi OS에 기본 포함된 GPIO Zero가 필요합니다. 없다면 아래 설치 명령을 사용하세요.',
         'install':'sudo apt update && sudo apt install python3-gpiozero',
         'run':'python3 pi_button_led.py'},
 'sources':[{'title':'Raspberry Pi 40핀·GPIO 공식 문서','url':PI},{'title':'Kingbright WP7113ID 데이터시트','url':LED},
            {'title':'Adafruit #4431 버튼 모듈 및 배선','url':BUTTON},{'title':'GPIO Zero Button 입력 문서','url':GPIOZERO}],
 'warnings':['이 회로는 사용자가 선택한 버튼 LED 기능의 새 설계이며 입력 사진의 원본 배선·동작 복원이 아닙니다.',
             '실물 조립 및 Raspberry Pi 하드웨어 동작은 아직 검증하지 않았습니다.',
             'GPIO는 3.3 V만 사용합니다. 모터나 고전류 부하를 GPIO에 직접 연결하지 마세요.'],
 'hardware_tested':False,
}

def pi_button_led_design():
    """Return a private copy so project-specific metadata cannot mutate recipe."""
    return deepcopy(DESIGN)
