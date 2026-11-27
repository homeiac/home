#!/usr/bin/env python3
"""Publish aggregate experiment evidence with explicit unresolved operator gates."""
import argparse,json,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
subprocess.run([sys.executable,str(Path(__file__).with_name('report.py')),str(a.directory),'--output',str(a.directory/'aggregate.json')],check=True,stdout=subprocess.DEVNULL)
report=json.loads((a.directory/'aggregate.json').read_text());report['at']=datetime.now(timezone.utc).isoformat();report['status']='matched comparisons complete; GPU contention intervention awaiting owner approval'
report['runtime_audit']=json.loads((a.directory/'runtime-audit.json').read_text())
report['trace_status']={'native_mac_sample':'successful actual model-process native stacks','python_all_thread_samples':'successful','linux_ebpf':'successful 20-second syscall capture of actual model process','mac_sudo':'not collected: sudo password required; diagnostic worker readiness deadline expired'}
report['limitations']=['26 frozen holdouts, not a representative library throughput sample','13 negative controls do not establish population precision','No timed production workers restarted; independent caption/LLM workloads remained active','Mac GPU contention pause/resume A/B requires owner approval','Measured stages include preprocessing, postprocessing and synchronization; not GPU kernel time','A serial variant temporarily used one ThreadPool caller; main-thread repeats explicitly recorded','Idle Metal diagnostic model was resident during early CPU tests while awaiting sudo; later main-thread repeats had no waiting test model','Short batching variant includes new batch-shape warmup costs; no stable throughput win claimed']
a.output.write_text(json.dumps(report,indent=2)+'\n');print(report['status'])
