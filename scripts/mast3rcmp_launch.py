"""Launch one finite recording with no wall cap; stop own group on traceback.

No simulator/model credentials, no truth. GPU samples measure the exclusive VM
total (contexts/allocator overhead included); torch peaks are reported separately.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time


def launch(repo,entry,prepared,output):
    repo,prepared,output=map(lambda p:Path(p).resolve(),(repo,prepared,output))
    output.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy()
    env.update(MAST3RCMP_OUTPUT=str(output/'probe'),MAST3RCMP_INPUT_RECEIPT=str(prepared/'input-receipt.json'),
               PYTHONUNBUFFERED='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    import sys
    command=[sys.executable,str(entry),'--dataset',str(prepared/'rgb'),'--config',str(prepared/'config.yaml'),
             '--calib',str(prepared/'intrinsics.yaml'),'--no-viz','--save-as','mast3rcmp-unused']
    process=subprocess.Popen(command,cwd=repo,env=env,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    fatal=threading.Event()

    def log_output():
        with (output/'run.log').open('w') as log:
            for line in process.stdout:
                log.write(line);log.flush()
                # A crashed backend can otherwise leave upstream waiting on a
                # queue forever. This is an error stop, never a time budget.
                if line.startswith('Traceback (most recent call last):'):
                    fatal.set()

    reader=threading.Thread(target=log_output,daemon=True);reader.start()
    samples=[];start=time.perf_counter()
    while process.poll() is None:
        r=subprocess.run(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],capture_output=True,text=True)
        if r.returncode==0:
            samples.append(dict(elapsed_s=time.perf_counter()-start,memory_used_mib=int(r.stdout.strip())))
        if fatal.is_set():
            os.killpg(process.pid,signal.SIGTERM)
        time.sleep(.5)  # observation sampling interval, not an execution cap
    rc=process.wait();reader.join()
    receipt=json.loads((prepared/'input-receipt.json').read_text())
    summary=dict(returncode=rc,traceback_detected=fatal.is_set(),wall_seconds=time.perf_counter()-start,
                 expected_frames=receipt['all_frames'],gpu_memory_samples=samples,
                 sampled_peak_gpu_total_mib=max((r['memory_used_mib'] for r in samples),default=None),
                 resource_scope='exclusive_gcp4_whole_gpu_including_all_SLAM_children',command=command,
                 source_sha=os.environ['MAST3RCMP_SOURCE_SHA'],
                 entry_sha256=hashlib.sha256(Path(entry).read_bytes()).hexdigest(),
                 input_receipt_sha256=hashlib.sha256((prepared/'input-receipt.json').read_bytes()).hexdigest())
    if rc or fatal.is_set():
        rows=[]
        ledger=output/'probe/frames-online.jsonl'
        if ledger.exists(): rows=[json.loads(line) for line in ledger.read_text().splitlines()]
        for i in range(len(rows),receipt['all_frames']):
            rows.append(dict(index=i,t_sim_s=receipt['frames'][i]['t_sim_s'],success=False,status='HOST_ERROR_unprocessed',
                reason_category='upstream_traceback_or_nonzero_exit',blocking_object='not_observed_offline_rgb',minimum_gap='not_measured_offline_rgb'))
        summary.update(status='HOST_ERROR',frames=rows)
    (output/'launch.json').write_text(json.dumps(summary,indent=2)+'\n')
    return rc or int(fatal.is_set())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('repo','entry','prepared','output'):p.add_argument('--'+key,required=True)
    a=p.parse_args();raise SystemExit(launch(a.repo,a.entry,a.prepared,a.output))
