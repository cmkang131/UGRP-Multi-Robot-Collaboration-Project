"""On-host ACT12 pair audit and exact off/on command/result equivalence.

No simulator/model imports or Mac media retrieval. The JSON is fetch-lite.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from PIL import Image
from harness.grasp_act_contract import validate_observation, command
from harness.grasp_act_solo_recording import camera_config


def raw(root, name):
    p = Path(root)/name
    if p.exists():return p.read_bytes()
    return subprocess.check_output(['zstd','-qdc',str(p)+'.zst'])


def digest(value):return hashlib.sha256(value).hexdigest()
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def rows(root,name):return [json.loads(x) for x in raw(root,name).splitlines() if x.strip()]


def audit(root):
    root = Path(root)
    result = json.loads(raw(root,'result.json'))
    assert result['training_rgb'] is True and result['recording_mode']=='training'
    assert result['student_execution'] is False and result['training_include'] is False
    boundary = result['input_audit']
    assert all(boundary.get(k)==0 for k in ('invisible_measurements','held_world_reads'))
    camera = json.loads(raw(root,'student-camera.json'))
    assert camera == camera_config()
    plan = json.loads(raw(root,'plan.json'))
    actors = {}
    for rid, role in plan['roles'].items():
        obs, labels = rows(root,f'student-{rid}.jsonl'), rows(root,f'teacher-{rid}.jsonl')
        assert obs and len(obs)==len(labels)
        frames = {}
        for row,label in zip(obs,labels):
            validate_observation(row)
            assert row['robot_id']==rid and row['role']==role and row['skill']=='release'
            assert row['destination_zone']==plan['destination_region'].removeprefix('zone_')
            assert row['sample_id']==label['sample_id'] and row['t']==label['clean_teacher_command']['t']
            command(label['clean_teacher_command'])
            for ref in row['rgb']:
                assert ref['robot_id']==rid and ref['path'].startswith(f'rgb/{rid}/')
                path = (root/ref['path']).resolve()
                assert path.is_relative_to(root.resolve()) and not (root/ref['path']).is_symlink()
                if ref['path'] not in frames:
                    assert digest(path.read_bytes())==ref['sha256']
                    with Image.open(path) as im:
                        assert im.format=='JPEG' and im.size==(640,480)
                        im.verify()
                    frames[ref['path']]=ref['sha256']
                assert frames[ref['path']]==ref['sha256']
        periods=[b['t']-a['t'] for a,b in zip(obs,obs[1:])]
        assert periods and all(abs(p-.1)<=.002 for p in periods)  # inherited ACT12 clock check
        assert set(frames)=={str(p.relative_to(root)) for p in (root/'rgb'/rid).glob('*.jpg')}
        assert len(frames)==len(obs)
        assert sum(x['done'] for x in labels)==int(result.get('release_outcome')=='teacher_done')
        for prev,row in zip(labels,obs[1:]):assert prev['clean_teacher_command']==row['issued'][-1]
        actors[rid]=dict(rows=len(obs),frames=len(frames),period_min_s=min(periods),period_max_s=max(periods),
                         first_t=obs[0]['t'],last_t=obs[-1]['t'],rgb_sha256=digest(canonical(frames)))
    guard=result['recording']['render_audit']
    assert guard['integration_or_rng_changes']==0 and guard['calls']>=sum(v['frames'] for v in actors.values())
    assert not list((root/'eval-overview').glob('*'))
    return dict(passed=True,raw=str(root),source_sha=result['source_sha'],actors=actors,camera=camera,
                input_audit=boundary,render_audit=guard,result_sha256=digest(raw(root,'result.json')),
                logical_bytes=sum(p.stat().st_size for p in root.parent.rglob('*') if p.is_file()),
                training_include=False)


def compare(off,on):
    off,on=Path(off),Path(on)
    a,b=(json.loads(raw(r,'result.json')) for r in (off,on))
    ignored={'source_sha','wall_s','loadavg_at_start','loadavg_at_end','timings_s',
             'training_rgb','recording_mode','training_include','recording'}
    hashes={}
    for rid in ('r1','r2'):
        hashes[f'commands_{rid}']=[digest(raw(off,f'teacher-{rid}.jsonl')),
                                   digest(raw(on,f'teacher-raw/teacher-{rid}.jsonl'))]
    for name in ('eval-only.jsonl','scene.xml','plan.json'):
        hashes[name]=[digest(raw(r,name)) for r in (off,on)]
    hashes['result_control_evaluation']=[digest(canonical({k:v for k,v in r.items() if k not in ignored})) for r in (a,b)]
    return dict(passed=all(x==y for x,y in hashes.values()) and a.get('release_success') is True
                and b.get('release_success') is True,off=str(off),on=str(on),hashes=hashes,
                result_ignored_fields=sorted(ignored),off_source_sha=a['source_sha'],on_source_sha=b['source_sha'],
                success=[a.get('release_success'),b.get('release_success')],recording=audit(on))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pair',nargs=2,action='append',required=True,metavar=('OFF','ON'))
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();pairs=[]
    for off,on in a.pair:
        try:pairs.append(compare(off,on))
        except Exception as e:pairs.append(dict(passed=False,off=off,on=on,error=f'{type(e).__name__}: {e}'))
    report=dict(schema='ugrp.rel22adapt.equivalence.v1',pairs=pairs,passed=all(p['passed'] for p in pairs),
                scope='two-seed observer equivalence; no gate promotion or data admission')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(passed=report['passed'],pairs=len(pairs))))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
