"""Small reviewed catalog. Catalog facts never identify an uploaded object by themselves."""
ESP_URL="https://documentation.espressif.com/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html"
LED_URL="https://www.kingbrightusa.com/images/catalog/SPEC/WP7113ID.pdf"
SW_URL="https://components.omron.com/sites/default/files/datasheet_pdf/A070-E1.pdf"
CATALOG={
 "esp32_devkitc_v4": {"name":"ESP32-DevKitC V4", "kind":"board", "source":ESP_URL,
    "pins":{"3V3":"J2.1","GND":"J3.1","GPIO23":"J3.2","GPIO18":"J3.9"},
    "voltage":"3.3 V logic", "note":"ESP32-WROOM 표식만으로 DevKitC V4 보드를 특정할 수 없습니다. USB·5V·3V3 중 전원 공급 방식은 하나만 사용합니다."},
 "resistor_axial": {"name":"축형 저항 (설계 규격)","kind":"resistor","source":"https://gitlab.com/kicad/libraries/kicad-footprints/-/tree/master/Resistor_THT.pretty",
    "pins":{"1":"1","2":"2"},"symbol":"Device:R","footprint":"Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", "note":"값은 사용자가 확인해야 합니다. PCB는 몸체 6.3×2.5 mm, 리드 간격 7.62 mm 설계 규격입니다."},
 "wp7113id": {"name":"Kingbright WP7113ID","kind":"led","source":LED_URL,"pins":{"A":"2","K":"1"},"symbol":"Device:LED","footprint":"LED_THT:LED_D5.0mm",
    "note":"5 mm 적색 LED. K는 캐소드(음극), A는 애노드(양극). 실제 극성을 확인해야 합니다. Vf typ 1.9 V at 10 mA; 전형값은 보장 최소값이 아닙니다."},
 "b3f1000": {"name":"OMRON B3F-1000","kind":"button","source":SW_URL,"pins":{"1":"1","2":"2"},"symbol":"Switch:SW_Push","footprint":"Button_Switch_THT:SW_TH_Tactile_Omron_B3F-100x",
    "note":"2개의 전기 접점군을 가진 4리드 버튼. KiCad 패드는 내부 공통 접점군을 1/2로 표현합니다. 6.5×4.5 mm 리드 간격을 실제 부품과 대조하세요."},
 "capacitor_disc": {"name":"무극성 5 mm 피치 커패시터 (설계 규격)","kind":"capacitor","source":"https://gitlab.com/kicad/libraries/kicad-footprints/-/tree/master/Capacitor_THT.pretty","pins":{"1":"1","2":"2"},"symbol":"Device:C","footprint":"Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm","note":"무극성, 5 mm 리드 간격. 실제 제품 크기·정격은 별도 확인합니다."},
 "input_connector": {"name":"외부 입력 2핀 헤더 (설계 규격)","kind":"source","source":"https://gitlab.com/kicad/libraries/kicad-footprints/-/tree/master/Connector_PinHeader_2.54mm.pretty","pins":{"OUT":"1","GND":"2"},"symbol":"Connector_Generic:Conn_01x02","footprint":"Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical","note":"핀1=신호 입력, 핀2=GND로 정의한 새 설계입니다."}
}


def search_catalog(query):
    q=query.casefold().replace(" ","")
    return [{"id":key,**value} for key,value in CATALOG.items() if q in (key+value["name"]+value["kind"]).casefold().replace(" ","")]

# Schematic-only interfaces. These connector symbols are NOT module mounting footprints.
ARDUINO_LCD_SOURCE='https://github.com/arduino/docs-content/blob/main/content/learn/04.electronics/03.lcd-displays/lcd-displays.md'
CATALOG.update({
 'arduino_uno_analog_interface':{'name':'Arduino UNO R3 · A0 전압 입력','kind':'board',
   'source':'https://docs.arduino.cc/resources/pinouts/A000066-full-pinout.pdf',
   'pins':{'5V':'POWER +5V','GND':'POWER GND','A0':'ANALOG IN A0'},
   'symbol':'Connector_Generic:Conn_01x03','schematic_pins':{'5V':'1','GND':'2','A0':'3'},'footprint':'',
   'note':'UNO R3의 5V/GND/A0 라벨을 대조하세요. A0에는 이 보드의 5V를 저항으로 나눈 전압만 연결합니다. 외부 전원 측정용이 아닙니다. 표시용 포트 1~3은 실제 보드 핀 번호가 아닙니다. R4·3.3V 보드로 대체하지 마세요.'},
 'arduino_uno_r3_interface':{'name':'Arduino UNO R3 · 5V 인터페이스','kind':'board',
   'source':'https://docs.arduino.cc/resources/pinouts/A000066-full-pinout.pdf',
   'pins':{'5V':'POWER +5V','GND':'POWER GND','D12':'DIGITAL 12','D11':'DIGITAL 11','D5':'DIGITAL 5','D4':'DIGITAL 4','D3':'DIGITAL 3','D2':'DIGITAL 2'},
   'symbol':'Connector_Generic:Conn_01x08','schematic_pins':{'5V':'1','GND':'2','D12':'3','D11':'4','D5':'5','D4':'6','D3':'7','D2':'8'},'footprint':'',
   'note':'UNO R3/5V 헤더 라벨을 확인하세요. 회로도 1~8번은 표시용 포트 번호이며 실제 Arduino 핀 번호가 아닙니다. 모듈 장착 풋프린트는 미지정입니다.'},
 'hd44780_parallel_interface':{'name':'HD44780 호환 16×2 LCD · 5V 병렬 인터페이스','kind':'display','source':ARDUINO_LCD_SOURCE,
   'pins':{p:'LCD '+p+' 라벨' for p in ['VSS','VDD','VO','RS','RW','E','D4','D5','D6','D7','A','K']},
   'symbol':'Connector_Generic:Conn_01x12','schematic_pins':{p:str(i+1) for i,p in enumerate(['VSS','VDD','VO','RS','RW','E','D4','D5','D6','D7','A','K'])},'footprint':'',
   'note':'실물의 5V/HD44780 호환·16×2·병렬 핀 라벨을 확인해야 합니다. I2C 백팩 모듈은 해당하지 않습니다. 사용하지 않는 D0~D3은 연결하지 않습니다. 회로도 1~12번은 표시용 포트 번호이며 실제 16핀 번호가 아닙니다. A/K 백라이트 극성·정격은 모듈 데이터시트로 확인하세요.'},
 'potentiometer_interface':{'name':'10kΩ 가변저항 · 3단자 인터페이스','kind':'potentiometer','source':ARDUINO_LCD_SOURCE,
   'pins':{'END1':'저항 끝단 1','WIPER':'측정으로 확인한 가운데 접점','END2':'저항 끝단 2'},
   'symbol':'Device:R_Potentiometer','schematic_pins':{'END1':'1','WIPER':'2','END2':'3'},'footprint':'',
   'note':'총 저항 10kΩ, 와이퍼 접점을 실물에서 측정하세요. 외형상의 가운데 다리가 항상 와이퍼라고 가정하지 않습니다. 풋프린트는 미지정입니다.'}
})

# Simulation interface, not a manufacturer datasheet or a validated real module.
CATALOG.update({
 'arduino_uno_light_interface':{'name':'Arduino UNO R3 · 조도 입력/LED 출력','kind':'board',
  'source':'https://docs.arduino.cc/resources/pinouts/A000066-full-pinout.pdf',
  'pins':{'5V':'POWER +5V','GND':'POWER GND','A0':'ANALOG IN A0','D5':'DIGITAL 5'},
  'symbol':'Connector_Generic:Conn_01x04','schematic_pins':{'5V':'1','GND':'2','A0':'3','D5':'4'},'footprint':'',
  'note':'UNO R3 헤더 라벨을 확인하세요. 회로도 포트 번호는 실제 보드 핀 번호가 아닙니다.'},
 'sim_photoresistor_module':{'name':'조도 센서 모듈 · 가상 인터페이스','kind':'sensor',
  'source':'https://docs.wokwi.com/parts/wokwi-photoresistor-sensor',
  'pins':{'VCC':'VCC 라벨','GND':'GND 라벨','AO':'AO 라벨'},
  'symbol':'Connector_Generic:Conn_01x03','schematic_pins':{'VCC':'1','GND':'2','AO':'3'},'footprint':'',
  'note':'가상 모델의 5V VCC/GND/AO 인터페이스입니다. 제조사 데이터시트가 아니며 실물 모듈의 핀 배열·전압·AO 극성과 임계값은 확인·측정해야 합니다.'}
})

# Source provenance is distinct from physical part identification. A tutorial,
# simulator part description or KiCad footprint is never a manufacturer datasheet.
_SOURCE_TYPES = {
 'esp32_devkitc_v4':'manufacturer_guide',
 'wp7113id':'manufacturer_datasheet',
 'b3f1000':'manufacturer_datasheet',
 'resistor_axial':'footprint_library',
 'capacitor_disc':'footprint_library',
 'input_connector':'footprint_library',
 'arduino_uno_analog_interface':'manufacturer_pinout',
 'arduino_uno_r3_interface':'manufacturer_pinout',
 'arduino_uno_light_interface':'manufacturer_pinout',
 'hd44780_parallel_interface':'manufacturer_tutorial',
 'potentiometer_interface':'manufacturer_tutorial',
 'sim_photoresistor_module':'simulation_reference',
}
for _catalog_id, _source_type in _SOURCE_TYPES.items():
    CATALOG[_catalog_id]['source_type'] = _source_type
