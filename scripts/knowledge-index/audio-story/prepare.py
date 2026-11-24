#!/usr/bin/env python3
"""Build a fixed Whisper.cpp release on Mac and fetch verified multilingual weights."""
import hashlib,json,os,subprocess,urllib.request
from pathlib import Path
ROOT=Path.home()/'Library/Application Support/knowledge-index-whisper'
TAG='v1.9.6'
REV='96ec4d9823e9d0211944172da35f9f29134af990'
MODELS={'ggml-base-q5_1.bin':'422f1ae452ade6f30a004d7e5c6a43195e4433bc370bf23fac9cc591f01a8898','ggml-small-q5_1.bin':'ae85e4a935d7a567bd102fe55afc16bb595bdb618e11b2fc7591bc08120411bb'}

def fetch(name):
    digest=MODELS[name];path=ROOT/name
    if not path.exists():
        subprocess.run(['curl','-fLsS','--retry','2','-o',str(path)+'.partial','https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/'+name],check=True)
        Path(str(path)+'.partial').replace(path)
    with path.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest()!=digest:raise ValueError('Model checksum mismatch')
    print(json.dumps({'file':name,'sha256':digest}),flush=True)

if __name__=='__main__':
    os.umask(0o077);ROOT.mkdir(parents=True,exist_ok=True)
    src=ROOT/TAG
    if not src.exists():subprocess.run(['git','clone','--depth','1','--branch',TAG,'https://github.com/ggml-org/whisper.cpp.git',str(src)],check=True)
    if subprocess.check_output(['git','-C',str(src),'rev-parse','HEAD'],text=True).strip()!=REV:raise ValueError('Whisper source revision mismatch')
    subprocess.run(['cmake','-S',str(src),'-B',str(src/'build'),'-DCMAKE_BUILD_TYPE=Release','-DGGML_METAL=ON','-DWHISPER_BUILD_TESTS=OFF'],check=True)
    subprocess.run(['cmake','--build',str(src/'build'),'-j','4','--target','whisper-cli','whisper-server'],check=True)
    for name in ['ggml-base-q5_1.bin','ggml-small-q5_1.bin']:fetch(name)
