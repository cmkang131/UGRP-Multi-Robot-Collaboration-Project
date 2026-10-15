"""One finite task chain; no cron, launch agent, recurring check or credentials."""
import pathlib,time,subprocess,os,json,datetime,platform
assert platform.node().startswith('ugrp-sim-gcp2')
r=pathlib.Path('/home/ugrp/ugrp-sim')
root=r/'src/46dd7ec3048a50a5443b2d61b0dece462e43b763'
py=str(r/'ugrp/.venv-sim/bin/python')
at=time.monotonic()
while not (r/'runs/reloc18-round1/DONE').exists():
    if time.monotonic()-at>3600:raise RuntimeError('round1 wait exhausted; no new batch')
    time.sleep(10)
env=dict(os.environ,PYTHONPATH=str(root),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
subprocess.run([py,str(r/'analysis-tools/reloc18-summarize.py'),'--round','1'],cwd=root,env=env,check=True)
subprocess.run([py,str(root/'experiments/2026-10-16-reloc18/run_round.py'),'--round','2'],cwd=root,env=env,check=True)
subprocess.run([py,str(r/'analysis-tools/reloc18-summarize.py'),'--round','2'],cwd=root,env=env,check=True)
(r/'ops-reviews/reloc18/CHAIN_DONE.json').write_text(json.dumps(dict(completed=datetime.datetime.now(datetime.timezone.utc).isoformat(),rounds=2))+'\n')
