"""Export only admitted local-skill RGB/commands/labels for private training.

Run near VM raw on persistent disk, then transfer this reduced artifact to Mac.
No simulator truth, LLM logs, credentials, top camera, or measured joints are
included. Raw originals remain on VM/ARM. No upload is performed here.
"""
import argparse,hashlib,io,json,subprocess,tarfile
from pathlib import Path
from PIL import Image
from harness.grasp_act_data import read,sha,owned_image,read_episode
from harness.grasp_act_contract import validate_observation


def export_episode(source,target):
    source=Path(source);result=read(source/'result.json');plan=read(source/'plan.json')
    if result.get('data_admitted') is not True or result.get('student_execution') is not False:
        raise ValueError('raw teacher run not admitted')
    manifest=read(source/'manifest.json')
    # Verify every source used, including the success and setup records.
    for rel,row in manifest.items():
        if rel.endswith(('.json','.jsonl','.jsonl.zst','.json.zst')) and sha(source/rel)!=row['sha256']:
            raise ValueError('raw source hash mismatch '+rel)
    target.mkdir(parents=True,exist_ok=False);images={};samples=0
    for rid in plan['roles']:
        obs=read(source/f'student-{rid}.jsonl',lines=True);labels=read(source/f'teacher-{rid}.jsonl',lines=True)
        if len(obs)!=len(labels):raise ValueError('raw observation/label length mismatch')
        accepted=[];ys=[]
        for x,y in zip(obs,labels):
            validate_observation(x)
            if x['sample_id']!=y['sample_id']:raise ValueError('raw target alignment')
            if y['local_skill_sample'] is not True:continue
            for ref in x['rgb']:
                original=owned_image(source,ref)
                if ref['path'] not in images:
                    dest=target/ref['path'];dest.parent.mkdir(parents=True,exist_ok=True)
                    with Image.open(original) as image:image.convert('RGB').resize((224,224),Image.Resampling.BILINEAR).save(dest,format='JPEG',quality=90)
                    images[ref['path']]={'sha256':sha(dest),'original_sha256':ref['sha256']}
                ref['sha256']=images[ref['path']]['sha256']
            accepted.append(x)
            ys.append({k:y[k] for k in ('sample_id','skill','object_kind','done','terminal_reason','clean_teacher_command')})
        (target/f'student-{rid}.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in accepted))
        (target/f'labels-{rid}.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in ys));samples+=len(accepted)
    initial={k:plan[k] for k in ('scenario_id','map_id','beam_pose','spawns','initial_pan','roles')}
    meta={'schema':'ugrp.grasp_act.episode.v1','teacher_admitted':True,'episode_id':plan['episode_id'],
          'start_state_id':plan['episode_id'],'initial_state_sha256':hashlib.sha256(json.dumps(initial,sort_keys=True).encode()).hexdigest(),
          'map_id':plan['map_id'],'split':plan['split'],'robots':list(plan['roles']),
          'source_sha':result['source_sha'],'raw_manifest_sha256':sha(source/'manifest.json'),
          'assignment_source':plan['assignment_source'],'image_size':[224,224],'images':images,'samples':samples,
          'scope':'near grasp only; teacher global navigation samples excluded'}
    (target/'episode.json').write_text(json.dumps(meta,indent=2)+'\n')
    read_episode(target)
    return {'episode_id':plan['episode_id'],'samples':samples,'bytes':sum(p.stat().st_size for p in target.rglob('*') if p.is_file())}


def main():
    p=argparse.ArgumentParser();p.add_argument('--runs',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--teacher-gate',type=Path,required=True);a=p.parse_args()
    gate=read(a.teacher_gate)
    if gate['N']<20 or gate['n']/gate['N']<.95 or gate['object_kind']!='long_beam':
        raise ValueError('teacher cohort gate >=95% and N>=20 required before collection export')
    a.out.mkdir(parents=True,exist_ok=False);report={'exported':[],'rejected':[]}
    for source in a.runs:
        try:report['exported'].append(export_episode(source,a.out/source.name))
        except ValueError as e:report['rejected'].append({'source':str(source),'reason':str(e)})
    (a.out/'export.json').write_text(json.dumps(report,indent=2)+'\n')
    from scripts.run_grasp_act_teacher import compress_logs
    compress_logs(a.out)
    archive=a.out.with_suffix('.tar.gz')
    with tarfile.open(archive,'w:gz') as tar:tar.add(a.out,arcname='data')
    print(json.dumps({'episodes':len(report['exported']),'rejected':len(report['rejected']),'compressed_bytes':archive.stat().st_size,'sha256':sha(archive)}))
if __name__=='__main__':main()
