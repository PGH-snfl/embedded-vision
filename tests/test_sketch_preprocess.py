from backend.workbench.arduino_preprocess import prepare_sketch
from backend.workbench.server import compile_edit,CompileRequest

def test_compiles_an_arduino_helper_defined_after_its_first_call():
    source='''void setup(){pinMode(5,OUTPUT);}
void loop(){setOutput(analogRead(A0));}
void setOutput(int value){analogWrite(5,value/4);}
'''
    result=compile_edit(CompileRequest(files=[{'name':'sketch.ino','content':source}]))
    assert result['success'] and result['hex_content'].startswith(':')
    assert source.endswith('void setOutput(int value){analogWrite(5,value/4);}\n')

def test_preserves_class_methods_comments_literals_templates_and_default_arguments():
    source='''// void imaginary(int x) { }
const char* text=R"tag(void notAFunction(int x) { })tag";
class Driver { public: void write(int value){} };
template<class T> void generic(int value){}
void withDefault(int value=3){}
void setup(){Driver d;d.write(3);generic<int>(4);withDefault();}
void loop(){}
'''
    assert prepare_sketch(source)=='#include <Arduino.h>\n'+source
    assert compile_edit(CompileRequest(files=[{'name':'sketch.ino','content':source}]))['success']
