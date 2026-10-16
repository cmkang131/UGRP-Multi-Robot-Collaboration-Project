"""One finite recording's postprocessing; no host lifecycle or behavior timer.

Waits for the explicitly owned recorder, then runs pinned replay and playback.
Never starts another simulation or retries a failed recording/analysis.
"""
import argparse
import datetime
import json
from pathlib import Path
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('input','source','vision','calibration','queue','output','status'):
        p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--recorder-pid',type=int,required=True);a=p.parse_args()
    def status(phase,**more):
        a.status.write_text(json.dumps(dict(phase=phase,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**more),indent=2)+'\n')
    status('WAITING_FOR_FINITE_RECORDING')
    while not (a.input/'summary.json').is_file():
        if not Path(f'/proc/{a.recorder_pid}').exists():
            status('HOST_ERROR',reason='owned recorder ended without completed summary');return 1
        time.sleep(5)  # orchestration polling only; no execution deadline
    raw=json.loads((a.input/'summary.json').read_text())
    if raw.get('status')!='cap_end' or raw.get('frames')!=401:
        status('HOST_ERROR',reason='incomplete recording',recording=raw);return 1
    commands=[
        [sys.executable,a.source/'scripts/mapbuild5_manifest.py','--input',a.input,'--vision',a.vision,'--output',a.input/'manifest.json'],
        [sys.executable,a.source/'scripts/mapbuild5_replay.py','--mapbuild-rbpf-v1','--input',a.input,
         '--vision',a.vision,'--calibration',a.calibration,'--queue',a.queue,'--output',a.output],
        [sys.executable,a.source/'scripts/mapbuild5_playback.py','--input',a.input/'roundtrip','--output',a.output/'playback']]
    try:
        for phase,cmd in zip(('SHARING_MANIFEST','PAIRED_REPLAY','HEADLESS_PLAYBACK'),commands):
            status(phase,command=list(map(str,cmd)))
            subprocess.run(list(map(str,cmd)),cwd=a.source,check=True)
    except subprocess.CalledProcessError as e:
        status('HOST_ERROR',reason=repr(e),command=e.cmd);return 1
    status('POSTPROCESSING_COMPLETE',summary=str(a.output/'evaluation/summary.json'),manifest=str(a.input/'manifest.json'))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
