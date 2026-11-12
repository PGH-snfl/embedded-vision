import subprocess
from pathlib import Path

import pytest

from backend.design.robot_physical import CODE
from backend.translation.rover import UnsupportedTranslation, translate_rover_code


@pytest.mark.parametrize('target,filename', [('raspberry_pi_c','pi_rover.c'),('arduino_cpp','arduino_rover.ino')])
def test_translates_rover_and_preserves_edited_command_values(target, filename):
    source=CODE.replace('"forward": (0.5, 0.5)', '"forward": (0.75, -0.25)')+'\n# comment retained in source\n'
    result=translate_rover_code(source,target)
    assert result['filename']==filename
    assert '{"forward", 0.75, -0.25}' in result['code']
    assert len(result['source_sha256'])==64
    assert result['details'] and '미검증' in result['notice']


@pytest.mark.parametrize('source', [
    CODE+'\nprint("additional behavior")\n',
    CODE.replace('time.sleep(seconds)', 'time.sleep(seconds * 2)'),
    CODE.replace('"stop": (0.0, 0.0)', '"stop": (1.0, 0.0)'),
    CODE.replace('"forward": (0.5, 0.5)', '"forward": (2.0, 0.5)'),
    CODE.replace('"forward": (0.5, 0.5)', '"forward": (float("nan"), 0.5)'),
    CODE.replace('"forward": (0.5, 0.5)', '"forward": (__import__("os").system("false"), 0.5)'),
    CODE.replace('"forward": (0.5, 0.5)', '"forward": (True, 0.5)'),
    CODE.replace('"forward": (0.5, 0.5)', '"forward": (0.5, 0.5), "forward": (0.4, 0.4)'),
    CODE.replace('"forward": (0.5, 0.5)', '"forward": (0.5, 0.5), "new": (0, 0)'),
    CODE+'#'+'a'*50000,
    'not valid python =',
])
def test_refuses_unsupported_semantics(source):
    with pytest.raises(UnsupportedTranslation): translate_rover_code(source,'arduino_cpp')


def test_refuses_unsupported_target():
    with pytest.raises(UnsupportedTranslation): translate_rover_code(CODE,'other')


def test_c_compiles_and_motor_i2c_matches_motor_kit(tmp_path):
    src=tmp_path/'rover.c';src.write_text(translate_rover_code(CODE,'raspberry_pi_c')['code'])
    mock=tmp_path/'mock.c';mock.write_text(r'''
#include <stdarg.h>
#include <stdio.h>
#include <sys/types.h>
#include <time.h>
int __wrap_open(const char *p,int f,...) {(void)p;(void)f;return 17;}
int __wrap_ioctl(int fd,unsigned long op,...) {(void)fd;(void)op;return 0;}
ssize_t __wrap_write(int fd,const void *data,size_t n) {
  (void)fd;const unsigned char *p=data;
  if(n==5) printf("%u:%u:%u:%u:%u\n",p[0],p[1],p[2],p[3],p[4]);
  return (ssize_t)n;
}
int __wrap_nanosleep(const struct timespec *a,struct timespec *b) {(void)a;(void)b;return 0;}
int __wrap_close(int fd) {(void)fd;return 0;}
''')
    exe=tmp_path/'rover'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(src),str(mock),'-Wl,--wrap=open','-Wl,--wrap=ioctl','-Wl,--wrap=write','-Wl,--wrap=nanosleep','-Wl,--wrap=close','-lm','-o',str(exe)],check=True)
    def output(command):
        p=subprocess.run([str(exe),command,'--seconds','0'],capture_output=True,text=True,check=True)
        return [tuple(map(int,line.split(':'))) for line in p.stdout.splitlines()]
    lines=output('forward')
    # Forward: positive channels 9 and 11 use the 2047/4096 duty.
    assert (42,0,0,255,7) in lines and (50,0,0,255,7) in lines
    # At stop both direction channels are fully on: braking, not release.
    assert lines[-6:]==[(42,0,16,0,0),(46,0,16,0,0),(38,0,16,0,0),
                        (50,0,16,0,0),(54,0,16,0,0),(58,0,16,0,0)]
    left=output('left')
    assert left[6:9]==[(42,0,16,0,0),(46,0,16,0,0),(38,0,16,0,0)]
    assert subprocess.run([str(exe),'forward','--seconds','3'],capture_output=True).returncode==2
    assert subprocess.run([str(exe),'forward','--seconds','nan'],capture_output=True).returncode==2


def test_arduino_cpp_compiles_with_mock_wire_and_brakes(tmp_path):
    source=CODE.replace('"forward": (0.5, 0.5)','"forward": (1.0, -0.5)')
    (tmp_path/'rover.ino').write_text(translate_rover_code(source,'arduino_cpp')['code'])
    (tmp_path/'Wire.h').write_text(r'''
#include <cstdio>
#include <cstdint>
using byte=uint8_t;
struct FakeWire { unsigned char bytes[8];int count=0;void begin(){} void beginTransmission(byte){count=0;} void write(byte b){bytes[count++]=b;} int endTransmission(){if(count==5)printf("%u:%u:%u:%u:%u\n",bytes[0],bytes[1],bytes[2],bytes[3],bytes[4]);return 0;} };
extern FakeWire Wire;
struct FakeSerial {void begin(int){} void println(const char*){} int available(){return 0;} int read(){return 0;}};
extern FakeSerial Serial;
inline void delay(unsigned long){}
''')
    harness=tmp_path/'harness.cpp';harness.write_text(r'''
#include "Wire.h"
FakeWire Wire; FakeSerial Serial;
#include "rover.ino"
int main(){setup(); char line[]="forward 0";runLine(line);}
''')
    # pragma once equivalent to avoid fake header duplicate declarations
    header=tmp_path/'Wire.h';header.write_text('#pragma once\n'+header.read_text())
    exe=tmp_path/'arduino'
    subprocess.run(['c++','-std=c++11','-Wall','-Wextra','-Werror','-I',str(tmp_path),str(harness),'-o',str(exe)],check=True)
    lines=[tuple(map(int,line.split(':'))) for line in subprocess.check_output([str(exe)],text=True).splitlines()]
    # 100% is fully on, reverse 50% maps to motor 2 negative channel.
    assert (42,0,16,0,0) in lines and (54,0,0,255,7) in lines
    assert lines[-6:]==[(42,0,16,0,0),(46,0,16,0,0),(38,0,16,0,0),
                        (50,0,16,0,0),(54,0,16,0,0),(58,0,16,0,0)]


def test_arduino_compiles_for_uno_avr_when_toolchain_available(tmp_path):
    root=Path(__file__).resolve().parents[1]
    compiler=root/'.tools/avr/root/usr/bin/avr-g++'
    core=root/'.tools/avr/root/usr/share/arduino/hardware/arduino/avr'
    if not compiler.exists() or not (core/'cores/arduino/Arduino.h').exists():
        pytest.skip('로컬 Arduino Uno AVR 컴파일러 없음')
    src=tmp_path/'arduino_rover.ino';src.write_text(translate_rover_code(CODE,'arduino_cpp')['code'])
    subprocess.run([str(compiler),'-std=gnu++11','-Os','-mmcu=atmega328p','-DF_CPU=16000000L',
        '-DARDUINO=10819','-I',str(core/'cores/arduino'),'-I',str(core/'variants/standard'),
        '-I',str(core/'libraries/Wire/src'),'-include','Arduino.h','-x','c++','-c',str(src),
        '-o',str(tmp_path/'arduino_rover.o')],check=True,capture_output=True,text=True)
