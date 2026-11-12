"""Extract drawing data from the manufacturers' bundled Eagle PCB sources.

Coordinates are millimetres about the PCB centre, with Eagle Y inverted for
the web scene. This is presentation data; it does not modify any circuit net.
Adafruit PCB-derived data remains CC BY-SA 3.0; see data/physical-models.
"""
from pathlib import Path
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/physical-models'
OUTPUT = ROOT / 'third_party/velxio/frontend/src/components/circuitiny/physicalBoardData.json'


def extract(filename, width, depth, min_y=0):
    raw = (SOURCE / filename).read_bytes()
    board = ET.fromstring(raw).find('drawing/board')
    packages = {(lib.get('name'), p.get('name')): p
                for lib in board.findall('libraries/library') for p in lib.findall('packages/package')}
    pads, parts, holes = [], [], []
    cx, cy = width / 2, min_y + depth / 2
    def point(x, y):
        return [round(x - cx, 5), round(cy - y, 5)]
    for h in board.findall('plain/hole'):
        holes.append({'at':point(float(h.get('x')), float(h.get('y'))), 'drill':float(h.get('drill'))})
    for el in board.findall('elements/element'):
        pkg = packages[(el.get('library'), el.get('package'))]
        name, package = el.get('name'), el.get('package')
        ex, ey = float(el.get('x')), float(el.get('y'))
        angle = math.radians(float(re.search(r'R([\d.]+)', el.get('rot', 'R0')).group(1)))
        def transform(x, y):
            if 'M' in el.get('rot', ''): x = -x
            return point(ex + x * math.cos(angle) - y * math.sin(angle),
                         ey + x * math.sin(angle) + y * math.cos(angle))
        epads = []
        for pad in pkg.findall('pad'):
            entry = {'element':name, 'pad':pad.get('name'),
                     'at':transform(float(pad.get('x')), float(pad.get('y'))),
                     'drill':float(pad.get('drill', '.9'))}
            pads.append(entry); epads.append(entry)
        for h in pkg.findall('hole'):
            if float(h.get('drill')) >= 2:
                holes.append({'at':transform(float(h.get('x')), float(h.get('y'))), 'drill':float(h.get('drill'))})
        kind = ('terminal' if '3.5MM' in package else
                'header' if package.startswith('1X') or package=='PI_HAT_SLOTS' else
                'capacitor' if package.startswith('PANASONIC') else
                'ic' if package in ('SOIC8_150MIL', 'SSOP24', 'TSSOP28', 'D-PAK_TO252AA') else
                'smd' if package.startswith('0805') or 'CHIPLED' in package else None)
        if kind:
            parts.append({'name':name, 'package':package, 'kind':kind,
                          'at':point(ex, ey), 'rotation':round(math.degrees(angle)), 'pads':epads})
    return {'width':width, 'depth':depth, 'pads':pads, 'parts':parts,
            'holes':holes, 'source':filename, 'source_sha256':hashlib.sha256(raw).hexdigest(),
            'license':'CC-BY-SA-3.0', 'author':'Adafruit Industries / Limor Fried'}


if __name__ == '__main__':
    data = {'hat':extract('hat-rev-a.brd', 65, 56.5, -1.27),
            'shield':extract('shield-v2.3.brd', 68.58, 53.34)}
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(f'Generated {OUTPUT.relative_to(ROOT)}')
