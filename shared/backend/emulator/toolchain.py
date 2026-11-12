"""Project-local Ubuntu AVR packages; no global installs or remote compilation."""
from shared.paths import PROJECT_ROOT, EDITOR_ROOT
import hashlib,json,subprocess,threading
from pathlib import Path

PROJECT=PROJECT_ROOT
TOOLS=EDITOR_ROOT/'.tools/avr'
ROOT=TOOLS/'root/usr'
BUILD_LOCK=threading.Lock()


def command(args,timeout=30):
    try:r=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as e:raise ValueError('AVR 도구 실행 실패: '+str(e)) from e
    if r.returncode:raise ValueError('AVR 컴파일/실행 실패: '+r.stderr[-2500:]+r.stdout[-1000:])
    return r.stdout


def fingerprint():
    manifest=TOOLS/'manifest.json'
    if not manifest.exists():raise ValueError('AVR 도구가 없습니다. bash scripts/setup_avr.sh를 실행하세요.')
    runner=Path(__file__).with_name('uno_runner.c')
    return hashlib.sha256(manifest.read_bytes()+runner.read_bytes()+Path(__file__).read_bytes()).hexdigest()


def prepare():
    with BUILD_LOCK:
        key=fingerprint();cache=TOOLS/'build'/key[:20];cache.mkdir(parents=True,exist_ok=True)
        library=cache/'core.a';runner=cache/'uno-runner'
        core=ROOT/'share/arduino/hardware/arduino/avr/cores/arduino'
        variant=ROOT/'share/arduino/hardware/arduino/avr/variants/standard'
        common=['-mmcu=atmega328p','-DF_CPU=16000000L','-DARDUINO=10819','-DARDUINO_AVR_UNO','-DARDUINO_ARCH_AVR','-Os','-ffunction-sections','-fdata-sections','-I'+str(core),'-I'+str(variant)]
        if not library.exists():
            objects=[]
            for source in sorted(core.iterdir()):
                if source.suffix not in {'.c','.cpp','.S'}:continue
                obj=cache/(source.name+'.o');cpp=source.suffix=='.cpp'
                flags=['-std=gnu++11','-fno-exceptions','-fno-threadsafe-statics'] if cpp else ['-std=gnu11'] if source.suffix=='.c' else ['-x','assembler-with-cpp']
                command([ROOT/'bin'/('avr-g++' if cpp else 'avr-gcc'),*common,*flags,'-c',source,'-o',obj]);objects.append(obj)
            command([ROOT/'bin/avr-ar','rcs',library,*objects])
        if not runner.exists():
            lib=ROOT/'lib/x86_64-linux-gnu'
            command(['cc','-O2','-Wall','-Wextra','-I'+str(ROOT/'include/simavr'),Path(__file__).with_name('uno_runner.c'),'-L'+str(lib),'-Wl,-rpath,'+str(lib),'-lsimavr','-o',runner])
        return common,library,runner,key


def compile_firmware(source,folder):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    common,library,runner,key=prepare()
    sketch=folder/'firmware.cpp';sketch.write_text(source)
    obj=folder/'firmware.o';elf=folder/'firmware.elf';hexfile=folder/'firmware.hex'
    command([ROOT/'bin/avr-g++',*common,'-std=gnu++11','-fno-exceptions','-fno-threadsafe-statics','-c',sketch,'-o',obj])
    command([ROOT/'bin/avr-g++','-mmcu=atmega328p','-Os','-Wl,--gc-sections',obj,library,'-lm','-o',elf])
    command([ROOT/'bin/avr-objcopy','-O','ihex','-R','.eeprom',elf,hexfile])
    return {'runner':runner,'elf':elf,'toolchain_sha256':key,
      'firmware_sha256':hashlib.sha256(source.encode()).hexdigest(),'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),
      'size_report':command([ROOT/'bin/avr-size',elf]).strip()}
