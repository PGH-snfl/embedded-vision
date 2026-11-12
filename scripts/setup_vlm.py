"""Download pinned official runtime/model artifacts into the project; no system install."""
import hashlib
from pathlib import Path
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[1]/".runtime/vlm"
REV="ea6a11058182570be6436b9a2e4ee7f7b49f908d"
FILES=[
    ("runtime.tar.gz","https://github.com/ggml-org/llama.cpp/releases/download/b11669/llama-b11669-bin-ubuntu-x64.tar.gz",
     "cf07c1c112d709bd67e522017471de57ed0ec8bea031d732c5422351c07f65ac"),
    ("models/Qwen3-VL-2B-Instruct-Q8_0.gguf",f"https://huggingface.co/ggml-org/Qwen3-VL-2B-Instruct-GGUF/resolve/{REV}/Qwen3-VL-2B-Instruct-Q8_0.gguf",
     "b7802e29f71a9e5b5e3f83f613df898a2204342dcea71a231ea501d481813c39"),
    ("models/mmproj-Qwen3-VL-2B-Instruct-Q8_0.gguf",f"https://huggingface.co/ggml-org/Qwen3-VL-2B-Instruct-GGUF/resolve/{REV}/mmproj-Qwen3-VL-2B-Instruct-Q8_0.gguf",
     "69066c8f279ec85ff48ab4059f6ebba0d2932ca57667f2bbdac7d9805bca9e7b"),
]

if __name__=="__main__":
    for relative,url,expected in FILES:
        target=ROOT/relative;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            temp=target.with_suffix(".partial")
            print("Download:",relative,flush=True);urllib.request.urlretrieve(url,temp);temp.replace(target)
        with target.open("rb") as f:actual=hashlib.file_digest(f,"sha256").hexdigest()
        if actual!=expected:raise SystemExit(f"Checksum mismatch: {target}")
        print("Verified:",relative,flush=True)
    with tarfile.open(ROOT/"runtime.tar.gz") as archive:
        archive.extractall(ROOT/"runtime",filter="data")
    print("Ready: bash run_vlm.sh")
