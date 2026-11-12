"""Conservative Arduino-style prototypes for ordinary top-level sketch helpers."""
import re

TYPE=r'(?:unsigned\s+long\s+long|unsigned\s+long|unsigned\s+int|unsigned\s+char|long\s+long|void|bool|boolean|byte|char|int|long|short|float|double|size_t|u?int(?:8|16|32|64)_t)'
HEADER=re.compile(r'^\s*((?:(?:static|inline)\s+)*'+TYPE+r')\s+([A-Za-z_]\w*)\s*\(([^;{}()]*)\)\s*\{',re.M)
PARAM=re.compile(r'(?:(?:const|volatile)\s+)*'+TYPE+r'(?:\s*[*&]\s*)*(?:\s+[A-Za-z_]\w*)?\s*(?:\[\d*\])?')
LITERALS=re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|R"(?P<delimiter>[^\s()\\]{0,16})\([\s\S]*?\)(?P=delimiter)"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')

def prepare_sketch(source):
    # Keep offsets and newlines: comments and string contents cannot supply
    # function signatures or change the top-level brace count.
    clean=LITERALS.sub(lambda m:re.sub(r'[^\n]',' ',m.group()),source)
    declarations=[]
    for match in HEADER.finditer(clean):
        result,name,args=match.groups()
        if name in {'setup','loop'} or clean[:match.start()].count('{')!=clean[:match.start()].count('}'):continue
        if re.search(r'template\s*<[^>]*>\s*$',clean[:match.start()]):continue
        parameters=[p.strip() for p in args.split(',') if p.strip()]
        if any(not PARAM.fullmatch(p) for p in parameters):continue
        declarations.append(result+' '+name+'('+args.strip()+');')
    prefix='#include <Arduino.h>\n'
    if declarations:prefix+='// Arduino sketch helper declarations\n'+'\n'.join(dict.fromkeys(declarations))+'\n'
    return prefix+source
