#!/usr/bin/env python3
"""Launchd-managed loopback Whisper Metal with Git policy and an SSH reverse tunnel."""
import json,os,plistlib,signal,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path.home()/'Library/Application Support/knowledge-index-whisper'
LABEL='com.panderosystems.knowledge-index-whisper'
POLICY='https://raw.githubusercontent.com/homeiac/home/codex/photo-enrichment-217/scripts/knowledge-index/audio-story/config.json'
VAD='2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987'

def stop(p):
    if p and p.poll() is None:
        p.terminate()
        try:p.wait(timeout=15)
        except subprocess.TimeoutExpired:p.kill();p.wait()

def run():
    server=tunnel=awake=None;refresh=0;desired=None;current=None
    signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
    try:
        while True:
            if time.monotonic()>refresh:
                try:
                    with urllib.request.urlopen(POLICY,timeout=15) as r:c=json.load(r)
                    candidate=c['model'] if c['enabled'] and 'mac' in c['backends'] else None
                    if candidate not in (None,'base-q5_1','small-q5_1'):raise ValueError('Invalid model')
                    desired=candidate
                except (OSError,ValueError,KeyError):pass
                refresh=time.monotonic()+60
            if current!=desired or (server and server.poll() is not None):
                stop(tunnel);stop(server);stop(awake);server=tunnel=awake=None;current=desired
            if current and not server:
                server=subprocess.Popen([str(ROOT/'v1.9.6/build/bin/whisper-server'),'-m',str(ROOT/('ggml-'+current+'.bin')),'--host','127.0.0.1','--port','19477','-l','auto','-t','2','-bs','1','-bo','1','-sns','--vad','-vm',str(ROOT/'ggml-silero-v6.2.0.bin')],cwd=ROOT)
            if server and (not awake or awake.poll() is not None):awake=subprocess.Popen(['/usr/bin/caffeinate','-s','-w',str(server.pid)])
            if server and (not tunnel or tunnel.poll() is not None):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:19477/health',timeout=2):pass
                    tunnel=subprocess.Popen(['/usr/bin/ssh','-NT','-o','BatchMode=yes','-o','ExitOnForwardFailure=yes','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=2','-R','127.0.0.1:19477:127.0.0.1:19477',os.environ['CB_HOST']])
                except OSError:pass
            time.sleep(5)
    finally:stop(tunnel);stop(server);stop(awake)

def install():
    import hashlib,shutil
    ROOT.mkdir(parents=True,exist_ok=True)
    vad=ROOT/'ggml-silero-v6.2.0.bin'
    if not vad.exists():subprocess.run(['curl','-fLsS','-o',str(vad),'https://huggingface.co/ggml-org/whisper-vad/resolve/main/ggml-silero-v6.2.0.bin'],check=True)
    if hashlib.sha256(vad.read_bytes()).hexdigest()!=VAD:raise ValueError('Invalid VAD model')
    target=ROOT/'mac.py';shutil.copyfile(__file__,target)
    domain=f'gui/{os.getuid()}';plist=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
    if plist.exists():
        plist.with_suffix('.backup').write_bytes(plist.read_bytes())
        subprocess.run(['launchctl','bootout',f'{domain}/{LABEL}'],capture_output=True)
    doc=dict(Label=LABEL,ProgramArguments=[sys.executable,str(target)],RunAtLoad=True,KeepAlive=True,ThrottleInterval=30,WorkingDirectory=str(ROOT),StandardOutPath=str(ROOT/'server.log'),StandardErrorPath=str(ROOT/'server.log'),EnvironmentVariables={'CB_HOST':os.environ['CB_HOST']})
    plist.write_bytes(plistlib.dumps(doc))
    for attempt in range(10):
        result=subprocess.run(['launchctl','bootstrap',domain,str(plist)],capture_output=True)
        if result.returncode==0:break
        time.sleep(2)
    else:raise RuntimeError('Launch agent bootstrap failed')

if __name__=='__main__':
    os.umask(0o077)
    if sys.argv[1:]==['--install']:install()
    else:run()
