"""Run libngspice in an isolated process, accepting only internally generated decks."""
import ctypes as C
import ctypes.util
import json,sys
from pathlib import Path
import numpy as np

class Complex(C.Structure):
    _fields_=[('real',C.c_double),('imag',C.c_double)]
class VectorInfo(C.Structure):
    _fields_=[('name',C.c_char_p),('type',C.c_int),('flags',C.c_short),('real',C.POINTER(C.c_double)),('complex',C.POINTER(Complex)),('length',C.c_int)]

def run(path, analysis):
    library=ctypes.util.find_library('ngspice')
    if not library:raise RuntimeError('libngspice가 설치되지 않았습니다. 합성 결과로 대체하지 않습니다.')
    lib=C.CDLL(library);messages=[]
    send=C.CFUNCTYPE(C.c_int,C.c_char_p,C.c_int,C.c_void_p)
    leave=C.CFUNCTYPE(C.c_int,C.c_int,C.c_bool,C.c_bool,C.c_int,C.c_void_p)
    def output(s,i,u):messages.append(s.decode(errors='replace'));return 0
    cb=send(output);exitcb=leave(lambda *args:0)
    lib.ngSpice_Init(cb,None,exitcb,None,None,None,None)
    lib.ngSpice_Command.argtypes=[C.c_char_p];lib.ngGet_Vec_Info.argtypes=[C.c_char_p];lib.ngGet_Vec_Info.restype=C.POINTER(VectorInfo)
    if lib.ngSpice_Command(('source '+str(Path(path).resolve())).encode()):raise RuntimeError('\n'.join(messages[-10:]))
    if lib.ngSpice_Command(analysis.encode()):raise RuntimeError('\n'.join(messages[-10:]))
    def vector(name):
        p=lib.ngGet_Vec_Info(name.encode())
        if not p or not p.contents.length:return None
        v=p.contents
        if v.real:return np.ctypeslib.as_array(v.real,shape=(v.length,)).copy()
        raw=np.ctypeslib.as_array(C.cast(v.complex,C.POINTER(C.c_double)),shape=(v.length*2,)).copy()
        return raw[::2]+1j*raw[1::2]
    result={}
    for name in ['time','frequency','v-sweep','vcc_5v','tp_divider','vsupply#branch','tp_input','tp_filter_out','tp_led_drive','tp_led_anode','tp_button','vdrive#branch','vinput#branch']:
        a=vector(name)
        if a is not None:
            if name in {'time','frequency','v-sweep'}:a=a.real
            indices=np.linspace(0,len(a)-1,min(len(a),1800),dtype=int)
            a=a[indices]
            result[name]={'real':a.real.tolist(),'imag':a.imag.tolist()} if np.iscomplexobj(a) else a.tolist()
    if not result:raise RuntimeError('No ngspice vectors: '+'\n'.join(messages[-15:]))
    return result

if __name__=='__main__':
    try:print(json.dumps(run(sys.argv[1],sys.argv[2]),allow_nan=False))
    except Exception as exc:print(str(exc),file=sys.stderr);sys.exit(1)
