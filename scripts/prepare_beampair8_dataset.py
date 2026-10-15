"""Offline pair-recording audit and existing ACT tensor conversion, gcp2 only."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile

import numpy as np
from PIL import Image, ImageDraw
from harness import grasp_act_contract as c
from harness.grasp_act_data import (convert, GraspDataset, INPUT_KEYS, TRAIN_KEYS,
    read_json, read_rows, sha256, write_json, paired_segments)
from harness.beampair_recording import existing, compress_jsons


def audit_run(run):
    run=Path(run);raw=run/'raw';view=run/'training'
    result=read_json(existing(raw,'result.json'));plan=read_json(raw/'plan.json')
    adapter=read_json(existing(run/'adapter','beampair1-result.json'))
    assert result['recording_mode']=='training' and result['student_execution'] is False
    assert result['weld']=='off' and result['self_pose_source']=='issued'
    assert result['observation_sampling']['rgb_size']==[640,480]
    assert result['observation_sampling']['rgb_hz']==10
    assert adapter['held_object_hidden_v1'] and adapter['held_world_reads']==0
    assert all(result['input_audit'][k]==0 for k in ('invisible_measurements','held_world_reads'))
    quality=read_json(raw/'scene-quality.json')
    assert quality['scene_profile']=='walls_floor_contrast_v5_indigo110_s80'
    assert quality['camera_quality']=='no_mip_v1'
    assert all(t['min']==9729 for ctx in quality['contexts'].values() for t in ctx['textures'])
    truths=read_rows(existing(raw,'eval-only.jsonl'))
    totals=[];montage=[]
    for rid in plan['roles']:
        observations=read_rows(existing(view,f'student-{rid}.jsonl'))
        labels=read_rows(existing(view,f'teacher-{rid}.jsonl'))
        commands=read_rows(existing(raw,f'teacher-{rid}.jsonl'))
        assert len(observations)==len(labels)==len(commands)==len(truths)==result['samples_per_robot']
        groups=paired_segments(observations,labels)
        assert groups and sum(l['done'] for l in labels)==1
        frames=sorted((raw/'rgb'/rid).glob('*.jpg'))
        assert len(frames)==len(observations)
        dt=[];vis=Counter();by_phase=defaultdict(Counter);image_refs=[]
        issued_history=list(observations[0]['issued'])
        for i,(o,l,issued,truth) in enumerate(zip(observations,labels,commands,truths)):
            c.validate_observation(o)
            assert o['robot_id']==rid and o['t']==truth['t']==l['clean_teacher_command']['t']
            assert all(ref['path'].startswith(f'rgb/{rid}/') for ref in o['rgb'])
            assert o['issued']==issued_history[-c.HISTORY:]
            issued_history.append(issued['applied_command'])
            if i:
                assert o['issued'][-1]==commands[i-1]['applied_command']
                dt.append(o['t']-observations[i-1]['t'])
            ref=o['rgb'][-1];assert ref['t']==o['t']
            image_refs.append(ref)
            assert o['rgb']==c.image_history(image_refs,o['t'])
            p=raw/ref['path'];assert sha256(p)==ref['sha256']
            with Image.open(p) as image:
                assert image.size==(640,480)
                image.verify()
            # Existing teacher criterion (5 visible probes), evaluation only.
            visible=truth['visibility'][rid]['visible_probes']>=5
            vis['all_N']+=1;vis['all_visible']+=int(visible)
            if l['local_skill_sample']:
                vis['local_N']+=1;vis['local_visible']+=int(visible)
            by_phase[l['teacher_phase']]['N']+=1
            by_phase[l['teacher_phase']]['visible']+=int(visible)
            if i in {0,len(observations)//5,2*len(observations)//5,3*len(observations)//5,4*len(observations)//5,len(observations)-1}:
                montage.append(dict(path=str(p),seed=plan['seed'],rid=rid,t=o['t'],phase=l['teacher_phase'],visible=visible))
        max_error=max((abs(d-c.PERIOD_S) for d in dt),default=0.)
        assert max_error<1e-5  # existing paired_segments continuity tolerance
        totals.append(dict(robot_id=rid,role=plan['roles'][rid],frames=len(frames),
            local_rows=sum(len(g) for g in groups),segments=len(groups),
            perturbation_rows_excluded=sum(l['perturbation_interval'] for l in labels),
            completion_targets=sum(l['done'] for l in labels),max_period_error_s=max_error,
            first_t=observations[0]['t'],last_t=observations[-1]['t'],visibility=dict(vis),
            visibility_by_phase={k:dict(v) for k,v in by_phase.items()}))
    return dict(seed=plan['seed'],path=str(run),actors=totals,success=True),montage


def make_montage(items,path):
    # Derived review image only; no re-rendering and no data/physics changes.
    w,h=320,265;out=Image.new('RGB',(3*w,((len(items)+2)//3)*h),(245,245,245));draw=ImageDraw.Draw(out)
    for i,item in enumerate(items):
        x=(i%3)*w;y=(i//3)*h
        with Image.open(item['path']) as im:out.paste(im.resize((320,240)),(x,y))
        draw.text((x+3,y+241),f"{item['seed']} {item['rid']} t={item['t']:.1f} {item['phase']} vis={int(item['visible'])}",fill=(0,0,0))
    out.save(path,quality=86)


def archive_dataset(folder):
    """Lossless dataset compression; verify every decoded member before removal.

    Existing ACT consumes plain JSON metadata. Archive the complete directory
    rather than silently changing that format to individually compressed JSON.
    The native loader was exercised before archival; decoded bytes are exact.
    """
    expected={str(p.relative_to(folder.parent)):sha256(p) for p in folder.rglob('*') if p.is_file()}
    archive=folder.with_suffix('.tar.zst')
    subprocess.run(['tar','--zstd','-cf',str(archive),'-C',str(folder.parent),folder.name],check=True)
    decoder=subprocess.Popen(['zstd','-qdc',str(archive)],stdout=subprocess.PIPE)
    verified={}
    with tarfile.open(fileobj=decoder.stdout,mode='r|') as tar:
        for member in tar:
            if not member.isfile():continue
            assert member.name in expected
            h=hashlib.sha256()
            with tar.extractfile(member) as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
            verified[member.name]=h.hexdigest()
    assert decoder.wait()==0 and verified==expected
    write_json(folder.parent/'dataset-archive-members.json',verified)
    result=dict(path=str(archive),sha256=sha256(archive),bytes=archive.stat().st_size,
        verified_members=len(verified),every_decoded_file_sha256_verified=True,
        restore=f'tar --zstd -xf {archive} -C NEW_EMPTY_DIRECTORY',
        manifest_sha256=expected['dataset/manifest.json'])
    shutil.rmtree(folder)  # derived copy only, complete verified archive retained
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--batch',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--heldout',type=Path,required=True)
    p.add_argument('--convert',action='store_true');a=p.parse_args()
    assert platform.system()=='Linux','all analysis stays on gcp2'
    done=read_json(a.batch/'DONE.json');a.output.mkdir(exist_ok=False)
    accepted=[r for r in done['completed'] if r['category']=='success' and r['admitted']]
    heldout=read_json(a.heldout);heldseeds={e['seed'] for e in heldout['episodes']}
    seeds={r['seed'] for r in done['completed']};assert not seeds&heldseeds
    report=dict(status='running',source_batch=str(a.batch),N=len(done['completed']),
        n=len(accepted),unstarted_N=len(done['not_started']),heldout_seeds=sorted(heldseeds),
        heldout_recorded_N=0,runs=[],failures=[r for r in done['completed'] if r not in accepted],
        scope='teacher recorded data only; no ACT training/student success')
    visibility=Counter();rows=0;frames=0;montage_runs=0
    for row in accepted:
        checked,samples=audit_run(row['path']);report['runs'].append(checked)
        for actor in checked['actors']:
            visibility.update(actor['visibility']);rows+=actor['local_rows'];frames+=actor['frames']
        if montage_runs<4:
            make_montage(samples,a.output/f"montage-{row['seed']}.jpg");montage_runs+=1
    report.update(frames=frames,local_rows=rows,visibility=dict(visibility),
        visibility_definition='evaluation-only assigned band with >=5 visible probes; existing gate threshold, never used as a dataset filter',
        period_s=c.PERIOD_S,original_image_size=[640,480],teacher_recordings=2*len(accepted))
    report['visibility']['all_ratio']=visibility['all_visible']/max(1,visibility['all_N'])
    report['visibility']['local_ratio']=visibility['local_visible']/max(1,visibility['local_N'])
    write_json(a.output/'data-audit.json',report)
    funnel=[dict(gate='planned',entered=200,passed=len(done['completed']),rejected=len(done['not_started'])),
        dict(gate='teacher_success',entered=len(done['completed']),passed=len(accepted),rejected=len(done['completed'])-len(accepted)),
        dict(gate='input_camera_clock_sha',entered=len(accepted),passed=len(report['runs']),rejected=0)]
    write_json(a.output/'rejection_table.json',dict(funnel=funnel,
        failures=report['failures'],source_batch=str(a.batch),reproduce=' '.join(__import__('sys').argv),
        constants_basis='5 probes and1e-5s from existing teacher/paired_segments; no new eligibility thresholds'))
    if a.convert:
        inputs=a.output/'inputs';inputs.mkdir()
        for row in accepted:
            src=Path(row['path']);dst=inputs/f"run-{row['seed']}";dst.mkdir()
            (dst/'raw').symlink_to(src/'training',target_is_directory=True)
            for name in ('SOURCE_SHA','EXIT'):shutil.copyfile(src/name,dst/name)
        source=(Path(accepted[0]['path'])/'SOURCE_SHA').read_text().strip()
        protocol=dict(teacher_sha=source,run_pattern='run-{seed}',train_seeds=sorted(r['seed'] for r in accepted),
            validation_seeds=[],heldout_reserved_only=sorted(heldseeds),run_class='milestone',
            admission='beampair7 raw40 + exact4 recording identity; successful fresh recordings only',
            done_label='teacher_v1',recording_adapter='beampair8_v1')
        write_json(a.output/'protocol.json',protocol)
        dataset=convert(inputs,protocol,a.output/'dataset')
        loaded=GraspDataset(a.output/'dataset','train')
        assert len(loaded)==rows
        for index in sorted({0,len(loaded)//2,len(loaded)-1}):
            batch=loaded[index];assert set(batch)==TRAIN_KEYS
            assert all(np.isfinite(v).all() for v in batch.values())
        report['dataset']=dict(path=str(a.output/'dataset'),manifest_sha256=sha256(a.output/'dataset/manifest.json'),
            actor_episodes=len(dataset['episodes']),rows=len(loaded),load_verified=True,
            normalization='fresh training seeds only; heldout20 absent',tensor_keys=sorted(TRAIN_KEYS))
        del loaded
        report['dataset']['archive']=archive_dataset(a.output/'dataset')
        report['dataset']['path']=report['dataset']['archive']['path']
    # Unique-inode footprint separates hardlinked images from logical bytes.
    seen=set();physical=0;logical=0;manifest=[]
    roots=[Path(r['path']) for r in done['completed']]
    if a.convert:roots.append(a.output/'dataset.tar.zst')
    for root in roots:
        for file in ([root] if root.is_file() else sorted(root.rglob('*'))):
            if not file.is_file():continue
            st=file.stat();logical+=st.st_size
            inode=(st.st_dev,st.st_ino)
            if inode not in seen:physical+=st.st_size;seen.add(inode)
            manifest.append(dict(path=str(file),bytes=st.st_size,sha256=sha256(file)))
    manifest_path=a.output/'SHA256.jsonl'
    manifest_path.write_text(''.join(json.dumps(v)+'\n' for v in manifest))
    b=manifest_path.read_bytes();subprocess.run(['zstd','-q','-k',str(manifest_path)],check=True)
    z=Path(str(manifest_path)+'.zst');assert subprocess.check_output(['zstd','-qdc',str(z)])==b
    manifest_path.unlink()
    report.update(status='READY' if len(done['completed'])==200 and not done['not_started'] else 'NOT_READY',
        footprint_unique_inode_bytes=physical,logical_bytes=logical,file_count=len(manifest),
        file_sha_manifest=dict(path=str(z),sha256=sha256(z),decoded_sha256=hashlib.sha256(b).hexdigest()),
        disk_free_bytes=shutil.disk_usage(a.output).free)
    write_json(a.output/'RUN_META.json',dict(**{'class':'milestone'},pr=537,branch='claude/beampair8',
        sha=(Path(accepted[0]['path'])/'SOURCE_SHA').read_text().strip(),batch=a.batch.name))
    write_json(a.output/'data-audit.json',report)
    compact={k:v for k,v in report.items() if k not in ('runs','failures')}
    compact['runs']=[dict(seed=r['seed'],path=r['path'],category=r['category'],admitted=r['admitted']) for r in done['completed']]
    compact['failures']=report['failures']
    compact['detailed_audit']=str(a.output/'data-audit.json')
    write_json(a.output/'summary.json',compact)
    compress_jsons(a.output)


if __name__=='__main__':main()
