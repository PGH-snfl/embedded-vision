#!/usr/bin/env python3
"""Standalone original crop helper; service calls the same crop_image function.

For direct development use pass --input and --output. The API's virtual shell
binds --asset to a registered input internally and never accepts arbitrary paths.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[4]))
from backend.vision.component_crops import crop_image
from backend.planner.models import Region


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--asset',default='image')
    parser.add_argument('--box',type=float,nargs=4,required=True)
    args=parser.parse_args()
    region=Region(asset_id=args.asset,**dict(zip(['x0','y0','x1','y1'],args.box)))
    data,metadata=crop_image(args.input,region)
    args.output.write_bytes(data)
    print(json.dumps(metadata))


if __name__=='__main__':main()
