"""Six frozen v199 cells on the verified second Azure VM; no VM1 operations."""
from pathlib import Path
import argparse, json, os, shlex, subprocess, time


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True)
    p.add_argument('--source-sha',required=True);a=p.parse_args();out=a.state;sha=a.source_sha
    assert len(sha)==40 and all(c in '0123456789abcdef' for c in sha)
    remote='/home/ugrp/ugrp-sim'
    def ssh(code):
        return subprocess.run(['ssh','-o','BatchMode=yes','azure2','python3 -c '+shlex.quote(code)],
            check=True,capture_output=True,text=True).stdout
    subprocess.run(['ssh','azure2','mkdir -p ~/ugrp-sim/relays/e2e13-long'],check=True)
    subprocess.run(['scp','-q',str(out/'relay/identity.json'),f'azure2:ugrp-sim/relays/e2e13-long/gemma.json'],check=True)
    pre=ssh('''import json,os,shutil,subprocess
from pathlib import Path
mem=int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
free=shutil.disk_usage(Path.home()/'ugrp-sim').free
assert mem>=6*2**30 and os.getloadavg()[0]<12.8
assert free-6*4096*2**20-8192*2**20>=8*2**30
subprocess.run(['python3','/usr/local/lib/ugrp-storage/scripts/azure_shutdown.py','admit'],check=True)
print(json.dumps(dict(memory_available_bytes=mem,free_bytes=free,loadavg=os.getloadavg(),runs=6,per_run_bytes=4096*2**20,reserved_bytes=8192*2**20)))
''')
    (out/'submission-resources.json').write_text(pre)
    submissions=[]
    cells=[(b,s) for b,seeds in [('a',(61001,61002,61003,61004)),('b',(61001,61002))] for s in seeds]
    for condition,seed in cells:
        name=f'e2e13-long-{condition}-s{seed}';root=f'{remote}/runs/{name}'
        command=['.venv-sim/bin/python','-m','scripts.sim_cli','workflow','run','e2e-stall-budget-v199',
            '--timeout','25320','--','--expected-source-sha',sha,'--output',root+'/raw','--seed',str(seed),
            '--driver-profile','study_gemma4_31b_v1','--relay-receipt',f'{remote}/relays/e2e13-long/gemma.json',
            '--e2e-live','--event-driven-llm','--compact-prompt','--setdown-only-when-relook','on_v1',
            '--decider','off','--exploration-progress','frontier_progress_v1','--pose-fix','innovation',
            '--path-follow','rpp_v1','--dev-light','--stall-bundle','--mapping-budget','case_cap_v1',
            '--stall-odometry','rgb_pulse_gate_v1' if condition=='a' else 'off',
            '--stall-recovery','backup_replan_v1' if condition=='a' else 'off',
            '--stall-noise','amcl_alpha_v1' if condition=='a' else 'off','--wall-cap-s','25200','--execute']
        meta=dict(pr=433,branch='codex/e2e13-long',sha=sha,batch='2026-10-12-e2e13-long',condition=condition.upper(),
            seed=seed,dev_light=True,wall_cap_s=25200,started_unix=time.time(),exact_speedups='all_off',vm='ugrp-sim-azure2')
        meta['class']='dev'
        code=r'''import json,subprocess,os,hashlib,time
from pathlib import Path
root=Path(ROOT_VALUE);source=Path(SOURCE_VALUE);meta=META_VALUE;command=COMMAND_VALUE
assert not root.exists()
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==meta['sha']
assert int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))>=6*1024**2
assert os.getloadavg()[0]<12.8
root.mkdir();(root.parent.parent/'leases'/root.name).touch()
meta['started_unix']=time.time()
meta['runner_assets']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path('/usr/local/lib/ugrp-storage/scripts')/x for x in ('remote_run_finish.py','azure_shutdown.py','azure_archive_native.py')]}
(root/'RUN_META.json').write_text(json.dumps(meta,indent=2)+'\n');(root/'SOURCE_SHA').write_text(meta['sha']+'\n')
(root/'COMMAND').write_text(json.dumps(command)+'\n');(root/'LOADAVG').write_text(str(os.getloadavg())+'\n')
env={**os.environ,'MUJOCO_GL':'osmesa','OMP_NUM_THREADS':'1','LP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
proc=subprocess.Popen(['python3','/usr/local/lib/ugrp-storage/scripts/remote_run_finish.py','--source',str(source),'--run',str(root),'--',*command],cwd=source,env=env,start_new_session=True,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print(json.dumps(dict(run=root.name,pid=proc.pid,submitted_unix=meta['started_unix'],source_sha=meta['sha'])))
'''.replace('ROOT_VALUE',repr(root)).replace('SOURCE_VALUE',repr(remote+'/src/'+sha)).replace('META_VALUE',repr(meta)).replace('COMMAND_VALUE',repr(command))
        result=json.loads(ssh(code));submissions.append(result)
        (out/'submissions.json').write_text(json.dumps(submissions,indent=2)+'\n')
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
