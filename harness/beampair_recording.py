"""Recording and offline admission only; no teacher decisions or simulator reads."""
from copy import deepcopy
import hashlib
import json
import os
import subprocess
from pathlib import Path

from harness import grasp_act_contract as c
from harness.grasp_act_data import read_json, read_rows, sha256, write_json, paired_segments

GATE_SHA = '835ccef26aa84b08cc8f7e256fd0f43aa1583ef9'
DEPENDENCY_SHA = '26f84d0f0ada1c33473c83cca2d3415ce51bd247'
SCENE = 'walls_floor_contrast_v5_indigo110_s80'


def install_capture_cache(world):
    """Share bytes among recording sinks at the same pre-command SIM tick.

    This finite runner captures the tail, review and training image before
    each robot's command. No physics, material, camera or renderer option is
    changed between those captures. Invalidate at every SIM-time change and
    keep robot/camera/JPEG quality distinct. Never used for action selection.
    See MuJoCo visualization scene-update contract and the pinned runner order.
    """
    original=world.render_jpeg;cache={};stamp=None
    stats=dict(mode='recording_capture_cache_v1',recording_only=True,hits=0,misses=0)
    def render_jpeg(*,robot_id='r1',camera='robot_cam',quality=82):
        nonlocal stamp
        now=float(world.data.time)
        if now!=stamp:cache.clear();stamp=now
        key=(robot_id,camera,quality)
        if key not in cache:
            cache[key]=bytes(original(robot_id=robot_id,camera=camera,quality=quality));stats['misses']+=1
        else:stats['hits']+=1
        return cache[key]
    world.render_jpeg=render_jpeg
    return stats


def existing(root, name):
    path = Path(root)/name
    return path if path.exists() else Path(str(path)+'.zst')


def compress_jsons(root):
    """Existing64KiB policy, decoded SHA verification before removing text."""
    records=[]
    for p in sorted(Path(root).rglob('*')):
        if p.suffix not in ('.json','.jsonl') or p.stat().st_size<=65536:continue
        data=p.read_bytes();z=Path(str(p)+'.zst')
        assert not z.exists()
        z.write_bytes(subprocess.check_output(['zstd','-q','-c'],input=data))
        assert subprocess.check_output(['zstd','-qdc',str(z)])==data
        records.append(dict(path=str(z),sha256=sha256(z),decoded_sha256=hashlib.sha256(data).hexdigest()))
        p.unlink()
    if records:write_json(Path(root)/'compression.json',records)


def gate_proof(root):
    """Recount all forty original raw outcomes, separately from recording pilots."""
    root = Path(root)
    plan_path = root/'ops-reviews/beampair7/gate-plan.json'
    plan = read_json(plan_path)
    rows, host = [], None
    assert len(plan['episodes']) == 40
    for e in plan['episodes']:
        run = root/'runs'/f"beampair7-gate-r2-{e['seed']}-{GATE_SHA[:8]}"
        rp = existing(run/'raw', 'result.json')
        ap = existing(run/'adapter', 'beampair1-result.json')
        r, a = read_json(rp), read_json(ap)
        assert read_json(run/'raw/plan.json') == e
        assert e['scene_profile'] == SCENE
        assert r['status'] == 'complete' and r['physical_success'] is True
        assert r['joint_held'] is True and r['max_stable_hold_s'] >= 3.
        assert r['source_sha'] == DEPENDENCY_SHA and a['source_sha'] == GATE_SHA
        assert a['dependency_sha'] == DEPENDENCY_SHA
        assert not r['cap_end'] and r['weld'] == 'off'
        assert r['recording_mode'] == 'success_measurement'
        assert a['peer_yield'] == 'beampair_peer_yield_v1' and not a['training_rgb']
        assert a['held_object_hidden_v1'] and a['hidden_measurement_ticks'] > 0
        for audit in (r['input_audit'], a['input_audit']):
            assert audit['enabled'] and audit['invisible_measurements'] == audit['held_world_reads'] == 0
        assert a['held_world_reads'] == 0
        if host is None: host = r['execution_host']
        assert host == r['execution_host']
        rows.append(dict(seed=e['seed'],raw=str(run/'raw'),result_sha256=sha256(rp),adapter_sha256=sha256(ap)))
    assert len({r['seed'] for r in rows}) == 40
    return dict(qualified=True,n=40,N=40,execution_host=host,source_sha=GATE_SHA,
        dependency_sha=DEPENDENCY_SHA,scene=SCENE,plan_sha256=sha256(plan_path),runs=rows,
        criteria='user: >=95% of >=40, actual40/40, joint hold>=3s, audits0, weld off')


def camera_config():
    # Same native camera as ACT15/16 SoloRecorder.camera_config; no FOV edits.
    from sim import masterpi_camera_profile as camera
    from sim import masterpi_camera_review_v3 as mount
    sources = ('sim/masterpi_camera_profile.py','sim/masterpi_camera_review_v3.py',
               'sim/s2_realism_camera_binding.py','harness/grasp_act_contract.py')
    root = Path(__file__).resolve().parents[1]
    return dict(width=camera.CAMERA_NATIVE_WIDTH,height=camera.CAMERA_NATIVE_HEIGHT,
        period_s=c.PERIOD_S,hz=1/c.PERIOD_S,camera='robot_cam',schema=c.SCHEMA,
        pinhole_hfov_deg=camera.CAMERA_PINHOLE_HFOV_DEG,pinhole_vfov_deg=camera.CAMERA_PINHOLE_VFOV_DEG,
        raw_fisheye_fov='nonlinear K/D; no single angular FOV',
        K=camera.scaled_camera_matrix(640,480).tolist(),fisheye_D=list(camera.CAMERA_FISHEYE_D),
        mount=mount.PROFILE_ID,position_m=list(mount.POSITION_M),quat_wxyz=list(mount.QUAT_WXYZ),
        sources={p:sha256(root/p) for p in sources})


def command_identity(before, after):
    """Exact float/JSON values at every tick; no tolerance or wall-time columns."""
    checks = []
    for rid in ('r1','r2'):
        old = read_rows(existing(Path(before)/'raw',f'teacher-{rid}.jsonl'))
        new = read_rows(existing(Path(after)/'raw',f'teacher-{rid}.jsonl'))
        keys = ('sample_id','clean_teacher_command','applied_command','done','teacher_phase','skill')
        a, b = [[{k:r[k] for k in keys} for r in records] for records in (old,new)]
        checks.append(dict(robot_id=rid,before_rows=len(a),after_rows=len(b),equal=a==b,
            before_sha256=hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest(),
            after_sha256=hashlib.sha256(json.dumps(b,sort_keys=True).encode()).hexdigest(),
            first_difference=next((i for i,(x,y) in enumerate(zip(a,b)) if x!=y),None)))
    old = read_rows(existing(Path(before)/'adapter','beampair1-commands.jsonl'))
    new = read_rows(existing(Path(after)/'adapter','beampair1-commands.jsonl'))
    r = read_json(existing(Path(after)/'raw','result.json'))
    return dict(passed=all(v['equal'] for v in checks) and old==new and r['physical_success'] is True,
        before=str(before),after=str(after),robots=checks,adapter_rows_equal=old==new,
        physical_success=r['physical_success'],tolerance=0,
        scope='all ticks, SIM timestamps/PWM/wheels/pulse widths/phase/done and complete adapter command rows; wall timings excluded')


def make_training_view(run):
    """Preserve pinned v5 raw; make explicit v6 records, no peer/GT/text tensors.

    v5->v6 adds pickup_site to the enum; these grasp rows retain destination
    none. Only schema changes. The near-skill latch uses the existing visible
    handoff label and issued phase progression, never held beam coordinates.
    """
    run=Path(run);raw=run/'raw';adapter=run/'adapter'
    result=read_json(existing(raw,'result.json'));a=read_json(existing(adapter,'beampair1-result.json'))
    if not (result['status']=='complete' and result['physical_success'] and not result['cap_end']):
        return dict(admitted=False,reason_category='unsuccessful_teacher',raw=str(raw))
    assert a['training_rgb'] and a['held_world_reads']==0
    assert all(result['input_audit'][k]==0 for k in ('invisible_measurements','held_world_reads'))
    view=run/'training';view.mkdir(exist_ok=False)
    plan=read_json(raw/'plan.json');write_json(view/'plan.json',plan)
    write_json(view/'student-camera.json',camera_config())
    probes=read_rows(existing(adapter,'beampair1-commands.jsonl'))
    summaries=[]
    for rid in plan['roles']:
        observations=read_rows(existing(raw,f'student-{rid}.jsonl'))
        original_labels=read_rows(existing(raw,f'teacher-{rid}.jsonl'))
        own=[p for p in probes if p['robot_id']==rid]
        assert len(observations)==len(original_labels)==len(own)>0
        started=False;finished=False;labels=[];rows=[];excluded=0
        for obs,label,probe in zip(observations,original_labels,own):
            assert obs['schema']=='ugrp.grasp_act.student.v5'
            obs=deepcopy(obs);obs['schema']=c.SCHEMA;c.validate_observation(obs)
            assert obs['robot_id']==rid and obs['t']==probe['t']
            assert label['sample_id']==obs['sample_id']
            assert label['applied_command']==probe['issued_command']
            if rows:
                assert obs['issued'][-1]==own[len(rows)-1]['issued_command']
            if label['local_skill_sample']:started=True
            perturb=probe['disturbance'] is not None
            # Original .8m visible handoff, then finite command phases through
            # completion. This avoids asking the held-cargo guard for a pose.
            local=started and not finished and obs['skill']!='wait' and not perturb
            done=bool(label['done'] and local)
            target=deepcopy(label)
            target.update(clean_teacher_command=probe['clean_teacher_command'],
                applied_command=probe['issued_command'],perturbation_interval=perturb,
                local_skill_sample=bool(local),done=done,
                terminal_reason='command_sequence_complete' if done else None,
                local_selection_source='existing visible handoff latch + own issued phase sequence',
                exclusion_reason_category='disturbance' if perturb else 'after_completion' if finished else
                    'wait_instruction' if obs['skill']=='wait' else 'navigation_before_visible_handoff' if not started else None)
            if perturb:excluded+=1
            finished=finished or done
            rows.append(obs);labels.append(target)
        assert finished, 'no own command completion target'
        groups=paired_segments(rows,labels)
        assert groups
        (view/'rgb'/rid).mkdir(parents=True)
        for path in (raw/'rgb'/rid).glob('*.jpg'):
            os.link(path,view/'rgb'/rid/path.name)  # same persistent inode, no duplicate RGB bytes
        for name,data in ((f'student-{rid}.jsonl',rows),(f'teacher-{rid}.jsonl',labels)):
            (view/name).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in data))
        summaries.append(dict(robot_id=rid,rows=len(rows),local_rows=sum(len(g) for g in groups),
            segments=len(groups),perturbation_rows_excluded=excluded,completion_targets=sum(r['done'] for r in labels)))
    effective={**result,'source_sha':a['source_sha'],'dependency_sha':a['dependency_sha'],
        'training_rgb':True,'student_execution':False,'recording_mode':'training',
        'recording_adapter':'beampair8_v1','native_result':str(existing(raw,'result.json')),
        'native_result_sha256':sha256(existing(raw,'result.json'))}
    write_json(view/'result.json',effective)
    write_json(view/'recording-provenance.json',dict(schema='ugrp.beampair8.recording.v1',
        raw=str(raw),adapter=str(adapter),migration='student.v5->v6 schema token only; all observations revalidated',
        actors=summaries,camera=camera_config(),hardlinked_rgb=True,
        input_fields=sorted(c.FIELDS),tensor_keys=['observation.images.own_history','observation.state']))
    return dict(admitted=True,path=str(view),actors=summaries)
