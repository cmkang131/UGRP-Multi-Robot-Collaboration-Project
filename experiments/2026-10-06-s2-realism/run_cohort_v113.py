"""Finite preregistered sequential driver. No restart/monitoring service or model."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time


def main(source):
    root = Path(__file__).resolve().parents[2]
    primary = Path('/Users/changmin/projects/ugrp')
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip() == source
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip()
    plan = json.loads((Path(__file__).parent/'registration-v113.json').read_text())
    output = primary/'outputs'/('s2-realism-'+source[:8]+'-cohort.json')
    if output.exists():
        raise FileExistsError(output)
    record = dict(source_sha=source, execution_bundle_id=plan['execution_bundle_id'], runs=[],
                  driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  started_unix=time.time(), completed=False)
    counts=collections.Counter()
    probe_passed=False
    launch_failed=False
    for row in plan['runs']:
        out=primary/'outputs'/f"s2-realism-{source[:8]}-s{row['seed']}-{row['slot']}-{row['stage']}"
        status=dict(**row,output=str(out))
        if row['role']=='full' and not probe_passed:
            status.update(status='NOT_RUN',reason='probe gate did not pass')
        elif launch_failed:
            status.update(status='NOT_RUN',reason='previous launch produced no result')
        elif counts and max(counts.values()) >= plan['same_failure_stop_count']:
            status.update(status='NOT_RUN',reason='same failure twice')
        else:
            command=[sys.executable,'scripts/ugrp_session.py','run',f"s2-realism-s{row['seed']}",'--',
                     '/bin/zsh','experiments/2026-10-06-s2-realism/launch_v113.zsh',source,str(out),
                     row['stage'],str(row['seed']),row['slot']]
            start=time.monotonic()
            with (primary/'outputs'/f"s2-realism-{source[:8]}-s{row['seed']}-session.log").open('x') as log:
                proc=subprocess.run(command,cwd=root,stdout=log,stderr=subprocess.STDOUT)
            status.update(exit_code=proc.returncode,managed_wall_s=time.monotonic()-start)
            if (out/'result.json').exists():
                result=json.loads((out/'result.json').read_text())
                status['status']=result['status']
                status['result_sha256']=hashlib.sha256((out/'result.json').read_bytes()).hexdigest()
                if row['role']=='probe':
                    lines=(out/'eval_only/trajectory.jsonl').read_text().splitlines() if (out/'eval_only/trajectory.jsonl').exists() else []
                    last=json.loads(lines[-1]) if lines else {}
                    probe_passed=(result.get('stage_reached') is True and result.get('evaluation',{}).get('lifted') is True
                        and result.get('pickup_site_status')=='confirmed_by_site_disappearance'
                        and last.get('cyan_xyz_m',[0,0,0])[2]>.06)
                    status['probe_gate_passed']=probe_passed
                failure=result.get('failure')
                if isinstance(failure,dict):failure=failure.get('message') or failure.get('class')
                if not failure and row['role']=='probe' and not probe_passed:
                    failure='PROBE_SITE_OR_LIFT_GATE_FAILED'
                if not failure and not result.get('evaluation',{}).get('lifted'):
                    failure='NOT_LIFTED'
                if not failure and row['stage']=='place' and not result.get('evaluation',{}).get('success'):
                    failure='GEOMETRIC_DELIVERY_FAILED'
                if failure:
                    counts[failure]+=1
                    status['failure']=failure
            else:
                status.update(status='LAUNCH_FAILED',failure='NO_RESULT')
                counts['NO_RESULT']+=1
                launch_failed=True  # preserve the actual count; never invent a second failure
        record['runs'].append(status)
        output.write_text(json.dumps(record,indent=2)+'\n')
    record.update(completed=True,ended_unix=time.time(),failure_counts=dict(counts))
    output.write_text(json.dumps(record,indent=2)+'\n')


if __name__=='__main__':
    main(sys.argv[1])
