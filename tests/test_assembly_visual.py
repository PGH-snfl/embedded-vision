import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def test_assembly_visual_accepts_local_procedural_meshes_and_rejects_external_images(tmp_path):
    target=tmp_path/'assembly-visual.cjs'
    subprocess.run([str(ROOT/'third_party/velxio/frontend/node_modules/.bin/esbuild'),str(ROOT/'frontend/rover-src/assembly-visual.js'),
                    '--bundle','--platform=node','--format=cjs','--target=node12',f'--outfile={target}'],check=True,capture_output=True)
    code=r'''
const assert=require('assert'),{validAssemblyVisual}=require(process.argv[1]);
const scene={metadata:{type:'Object'},object:{type:'Group',children:[{type:'Mesh'}]},materials:[{type:'MeshStandardMaterial'}],images:[]};
assert(validAssemblyVisual(scene));assert(!validAssemblyVisual(null));
assert(!validAssemblyVisual({...scene,images:[{url:'https://external.invalid/collect'}]}));
assert(validAssemblyVisual({...scene,images:[{url:'data:image/png;base64,AAAA'}]}));
assert(!validAssemblyVisual({...scene,materials:[{type:'ShaderMaterial'}]}));
assert(!validAssemblyVisual({...scene,object:{type:'Camera'}}));
assert(!validAssemblyVisual({...scene,geometries:Array.from({length:3001},()=>({}))}));
'''
    subprocess.run(['node','-e',code,str(target)],check=True,capture_output=True)
