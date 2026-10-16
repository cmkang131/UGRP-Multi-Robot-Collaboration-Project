"""Audit native MJWarp capture bytes and paired own-input/target provenance.

Read-only CPU analysis on the raw host. Pilot caps remain excluded. In
particular, controller.result training_rgb=false is not rewritten: the external
capture wrapper records the data, with its own source and admission receipt.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path, lines=False):
    raw=path.read_bytes() if path.exists() else subprocess.check_output(['zstd','-dc',str(path)+'.zst'])
    return [json.loads(x) for x in raw.splitlines() if x.strip()] if lines else json.loads(raw)


def audit(root):
    from PIL import Image
    contract_root=Path('/home/ugrp/ugrp-sim/src/warp1-teacher-snapshot-6f057f7e')
    sys.path.insert(0,str(contract_root))
    from harness import grasp_act_contract as contract
    root=Path(root)
    wrapper=read(root/'capture/summary.json')
    controller=read(root/'controller/summary.json')
    rows=[]
    for entry in wrapper['worlds']:
        i=entry['world'];folder=root/'capture'/f'world-{i:03d}'
        original=root/'controller'/f'world-{i:03d}'
        observations=read(folder/'student-r1.jsonl',True)
        labels=read(folder/'teacher-r1.jsonl',True)
        frames=read(folder/'capture-context.json')
        commands=read(original/'teacher-commands.jsonl',True)
        result=read(original/'result.json')
        if not len(observations)==len(labels)==len(frames)==len(commands)>0:
            raise ValueError('unequal/empty native capture/observation/target/command streams')
        camera=read(folder/'student-camera.json')
        if (camera['width'],camera['height'],camera['hz'],camera['period_s'])!=(640,480,10,.1):
            raise ValueError('native student camera changed')
        if controller['camera']['resolution']!=[640,480] or controller['camera']['K']!=camera['K'] or controller['camera']['D']!=camera['fisheye_D'] or controller['camera']['mount_pos']!=camera['position_m'] or controller['camera']['mount_quat']!=camera['quat_wxyz']:
            raise ValueError('recorded and qualified camera differ')
        if camera['sources']['harness/grasp_act_contract.py']!=digest(Path(contract.__file__)):raise ValueError('recorded student input contract drift')
        previous=observations[0]['issued'];unique=set();pwm_transitions=0
        for j,(obs,label,frame,command) in enumerate(zip(observations,labels,frames,commands)):
            contract.validate_observation(obs)
            if not (obs['t']==frame['t']==command['t']==label['clean_teacher_command']['t']
                    and obs['sample_id']==label['sample_id'] and obs['issued']==previous
                    and obs['issued'][-1]==frame['previous'] and obs['skill']==frame['skill']
                    and label['teacher_phase']==frame['phase']
                    and label['clean_teacher_command']==command['command']
                    and label['phase_after']==command['phase']):
                raise ValueError('capture before command / own history / phase pairing mismatch')
            if j and abs(obs['t']-observations[j-1]['t']-.1)>.002:
                raise ValueError('native10Hz clock mismatch')
            saved=root/'capture'/f'world-{i:03d}'/obs['rgb'][-1]['path']
            source=Path(frame['path'])
            if digest(saved)!=digest(source) or digest(saved)!=frame['sha256'] or frame['sha256']!=obs['rgb'][-1]['sha256']:
                raise ValueError('controller JPEG bytes changed')
            with Image.open(saved) as im:
                if im.size!=(640,480) or im.mode!='RGB':raise ValueError('native RGB encoding mismatch')
            unique.add(frame['sha256']);pwm_transitions+=obs['issued'][-1]['pwm']!=label['clean_teacher_command']['pwm']
            previous=(previous+[label['clean_teacher_command']])[-len(previous):]
        for key in ('invisible_measurements','held_world_reads'):
            if result['input_audit'][key]!=0:raise ValueError('teacher input boundary violation')
        rows.append(dict(world=i,seed=entry['seed'],frames=len(frames),paired_targets=len(labels),
                exact_controller_jpegs=len(frames),unique_jpeg_hashes=len(unique),issued_pwm_transitions=pwm_transitions,
                done_targets=sum(x['done'] for x in labels),command_complete=labels[-1]['phase_after']=='complete',done_by_skill={skill:sum(x['done'] for x in labels if x['skill']==skill) for skill in sorted({x['skill'] for x in labels})},physical_success=result['physical_success'],
                lift_success=result['lift_success'],release_success=result['release_success'],cap_end=result['cap_end'],
                input_audit=result['input_audit'],duration_sim_s=len(frames)*.1,
                native_camera=camera,source=str(original),original_result_sha256=digest(original/'result.json') if (original/'result.json').exists() else digest(original/'result.json.zst')))
    return dict(status='complete',passed=True,raw=str(root),controller_source=wrapper['controller_source'],
                adapter_sha256=wrapper['adapter_sha256'],training_include=False,data_admitted=False,worlds=rows,
                summary_sha256=digest(root/'capture/summary.json'),
                scope='exact native JPEG/clock/own issued history and teacher target audit; separate dataset admission required')


def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=audit(a.root);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='worlds'}))

if __name__=='__main__':main()
