"""Verify own RGB hashes, issued history and fixed scoring on GCP2 outputs."""
import argparse
from pathlib import Path

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_json,read_rows,sha256,write_json
from scripts.analyze_grasp_act_act16a import require_cpu


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();host=require_cpu();runs=read_json(a.report/'runs.json');verified=[]
    for run in runs:
        raw=Path(run['raw']);obs=read_rows(raw/'student-inputs.jsonl');commands=read_rows(raw/'commands.jsonl')
        assert len(obs)==len(commands)
        history=obs[0]['issued'];clock=c.IssuedClock();cache={}
        for o,u in zip(obs,commands):
            c.validate_observation(o);assert o['issued']==history
            expected=clock.observe(o['skill'],o['t'],history[-1]['pwm'])
            assert all(abs(o[k]-v)<1e-8 for k,v in expected.items())
            history=(history+[c.command(u['command'])])[-c.HISTORY:]
            for ref in o['rgb']:
                key=ref['path']
                if key not in cache:cache[key]=sha256(raw/key)
                assert cache[key]==ref['sha256']
        assert all(run['input_audit'][k]==0 for k in ('forbidden_input_fields','teacher_input_fields','invisible_measurements','held_world_reads','top'))
        assert run['teacher_actions_executed']==0
        assert all(run['shadow_input_audit'][k]==0 for k in ('invisible_measurements','held_world_reads'))
        integrity=a.report/f'run-{run["seed"]}-integrity.json'
        verified.append(dict(seed=run['seed'],raw=str(raw),rows=len(obs),own_rgb_files=len(cache),
            hash_mismatch=0,issued_history_mismatch=0,clock_mismatch=0,
            full_raw_integrity_map=str(integrity),full_raw_integrity_map_sha256=sha256(integrity)))
    assert len(verified)==40
    write_json(a.report/'raw-verification.json',dict(host=host,complete=True,runs=verified,
        rows=sum(r['rows'] for r in verified),own_rgb_files=sum(r['own_rgb_files'] for r in verified),
        input_and_shadow_audit_violations=0,teacher_actions_executed=0,
        all_original_outcome_summaries_match=all(r['outcome_matches_original_summary'] for r in runs),
        scope='Validates GCP2 raw; saved original GCP1 six-slot fingerprints/outcome summaries are separate, not full trajectory equivalence.'))


if __name__=='__main__':main()
