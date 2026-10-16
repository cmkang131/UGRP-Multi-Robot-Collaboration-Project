"""Default-off, GCP2 CPU pair ACT closed loop; teacher actions/corrections zero."""
import argparse
import base64
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

import numpy as np

from harness import grasp_act_contract as c
from harness.grasp_act_data import sha256, write_json
from harness.grasp_act_policy import ChunkExecutor
from harness.grasp_act_rollout import OwnHistory, InputAudit, LiftScore, SoloSequence
from harness.beamact_pair_student import MODE, StudentBarrier, Funnel
from harness.beamact_pair_score import assigned_forces
from harness.beampair_teacher import DEPENDENCY_SHA, validate_plan
from harness.failure_rgb_tail import FailureRGBTail
from harness.beampair_recording import install_capture_cache
from sim.gatesv5_scene import scene_bindings
from scripts.beamact1_runtime import require_gcp2
from scripts.grasp_act_training_guard import ROOT, source_sha
from scripts.run_grasp_act_student import response
from scripts.run_beampair1 import dependency_modules, setup_admission


def run(plan, output, dependency, model, actor_python, *, mode='off', cap_s=60.):
    host = require_gcp2(training=False)
    if mode != MODE:
        raise ValueError('explicit student opt-in required')
    validate_plan(plan)
    if plan['seed'] not in range(8329000, 8329020):
        raise ValueError('exact reserved20 plan required')
    source = source_sha()
    model_meta = json.loads((model/'adapter.json').read_text())
    candidate_arm = model_meta.get('beamact3_v1', 'off')
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = dict(status='running', complete=False, seed=plan['seed'], mode=mode,
        source_sha=source, dependency_sha=DEPENDENCY_SHA, execution_host=host,
        teacher_actions=0, truth_corrections=0, student_execution=True,
        held_object_hidden_v1=True, weld='off', physical_success=False,
        contact_assignment='nearest authored colored end; ties ambiguous; evaluation only',
        model_sha256=sha256(model/'model.safetensors'), cap_end=False,
        loadavg_at_start=os.getloadavg())
    if candidate_arm != 'off':
        report.update(beamact3_v1=candidate_arm,compact_history=model_meta['compact_history'])
    write_json(output/'RUN_META.json', dict(**{'class':'milestone'}, pr=545 if candidate_arm!='off' else 540,
        branch='codex/beamact3' if candidate_arm!='off' else 'codex/beamact1', sha=source,
        batch='beamact3-'+candidate_arm+'-heldout20' if candidate_arm!='off' else 'beamact2-heldout20',
        keep=['commands.jsonl', 'student-inputs.jsonl', 'eval-only.jsonl', 'review']))
    write_json(output/'plan.json', plan)
    write_json(output/'result.json', report)
    scenario_path = ROOT/'experiments/2026-10-15-beampair1/scenario-v7.json'
    if sha256(scenario_path) != plan['scenario_source_sha256']:
        raise ValueError('scenario mismatch')
    scenario = json.loads(scenario_path.read_text())
    # The scene profile postdates the pinned physics dependency. Resolve its
    # closure before package isolation, exactly as run_beampair1 does.
    binding = scene_bindings(plan['scene_profile'])
    # All controller objects are constructed outside dependency isolation and
    # retain the frozen v6 own-input contract. Only physics/scene/protocol are
    # imported from the clean dependency; no teacher instance is constructed.
    worker = world = None
    streams = []
    tail = FailureRGBTail()
    audits = {r:InputAudit() for r in plan['roles']}
    barriers = {r:StudentBarrier() for r in plan['roles']}
    funnel, score, unrestricted_score = Funnel(), LiftScore(), LiftScore()
    done_times = {}
    target_gap = None
    latencies = []
    report['input_audit'] = {r:a.record for r,a in audits.items()}
    try:
        worker = subprocess.Popen([str(actor_python), '-m', 'scripts.beamact2_worker', '--model', str(model)],
            cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        if response(worker) != {'ready':True}:
            raise RuntimeError('ACT worker startup mismatch')
        predictions = (output/'chunk-predictions.jsonl').open('x');streams.append(predictions)
        def predict(observation, jpegs):
            audits[observation['robot_id']].accept(observation)
            request = dict(observation=observation, jpegs=[base64.b64encode(x).decode() for x in jpegs])
            at = time.monotonic()
            worker.stdin.write(json.dumps(request, allow_nan=False)+'\n');worker.stdin.flush()
            result = response(worker)
            latencies.append(time.monotonic()-at)
            if set(result) != {'chunk'}:
                raise ValueError('ACT response allowlist mismatch')
            predictions.write(json.dumps(dict(t=observation['t'], robot=observation['robot_id'], **result),allow_nan=False)+'\n')
            return result['chunk']
        executors = {r:ChunkExecutor(predict) for r in plan['roles']}
        with dependency_modules(dependency):
            from sim.zone_scenario_scene import ScenarioFinalV3Scene
            from sim.final_pair_highpose_nearclip import wrap
            from sim import masterpi_camera_review_v3 as camera
            from sim.s2_servo_stiffness import transform_xml as stiffness
            from sim.s2_realism_camera_binding import bind_camera
            from sim.grasp_act_scene import colors
            from sim.masterpi_drive_friction_v7 import build_world, PROFILE
            from sim.zone_cargo import place, CargoInstance
            from sim.grasp_act_port import DutyActPort
            from harness.grasp_act_start_sync import GraspStartSync
            from scripts.run_grasp_act_teacher import apply, snapshot
            import mujoco
            scene = wrap(binding[0](ScenarioFinalV3Scene.from_scenario(scenario,plan['seed'])))
            scene.config['setup_only']['spawns'] = deepcopy(plan['spawns'])
            original = scene.robot_transform
            def transform(xml, **kw):
                value = camera.transform_xml(original(xml,**kw), profile_id=camera.PROFILE_ID)
                for rid in ('r1','r2','r3'):
                    value = stiffness(value, servo_stiffness='real_v1', robot_id=rid)
                return colors(value, plan['end_color_scene'])
            scene.robot_transform = transform
            report['setup_admission'] = setup_admission(plan,scenario)
            os.environ['UGRP_SIM_OBSERVER_WIDTH']='320'
            os.environ['UGRP_SIM_OBSERVER_HEIGHT']='240'
            world = build_world(scene, drive_profile=PROFILE, seed=plan['seed'], width=640,height=480,
                render=True,warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,
                roller_collision='mesh',idle_robot_contacts='off')
            binding[1](world,output)
            # Cache only repeated same-SIM-time captures; byte-identical inputs.
            capture_stats = install_capture_cache(world)
            for controller in world.controllers.values():bind_camera(controller)
            scene.setup(world)
            place(world,[CargoInstance('beam_1','long_beam',tuple(plan['beam_pose']))])
            (output/'scene.xml').write_text(world.scene_xml)
            write_json(output/'scene.json',scene.manifest)
            ports={r:DutyActPort(world,r,allow_reverse=True,allow_mecanum=True) for r in plan['roles']}
            write_json(output/'camera-runtime.json',dict(scope='evaluation-only runtime camera verification',
                cameras={rid:{key:getattr(world.model,'cam_'+key)[world.controllers[rid].robot_cam_cid].tolist()
                    for key in ('pos','quat','intrinsic','resolution')} for rid in ports},
                own_rgb_size=[640,480],control_hz=10,review_hz=2,failure_tail_hz=10))
            for rid,port in ports.items():
                port.apply(dict(kind='look',pan_pulse=plan['initial_pan'][rid]),float(world.data.time))
            def advance(until):
                while float(world.data.time)<until-1e-8:
                    if world.data.eq_active.any():raise RuntimeError('WELD_ACTIVE')
                    for port in ports.values():port.tick(float(world.data.time))
                    world._physics_step_for(world.robot('r1'))
            advance(float(world.data.time)+.5)
            origin=float(world.data.time)
            previous={r:dict(t=origin,wheels=[0.]*4,duration_s=[0.]*4,
                pwm={str(s):int(ports[r]._servo_pulses[s]) for s in c.SERVOS}) for r in ports}
            histories={r:OwnHistory(r,plan['episode_id'],previous[r]) for r in ports}
            for r in ports:(output/'rgb'/r).mkdir(parents=True)
            write_json(output/'initial-issued.json',previous)
            # Same RNG and 0..1.5s start-delay construction as beampair7 runner.
            rng=np.random.default_rng(plan['seed'])
            delays={r:(0. if k==0 else float(rng.uniform(0,1.5))) for k,r in enumerate(ports)}
            sync=GraspStartSync(ports,delays)
            inst=next(x for x in scene.cargo if x.item_id=='beam_1')
            target_geoms=[world.model.geom(inst.geom(p.name)).id for p in inst.spec().parts if p.collision]
            finger_geoms=[world.model.geom(rid+'__'+side+'_finger').id
                for rid in ports for side in ('left','right')]
            finger_ids={world.model.geom(rid+'__'+side+'_finger').id:(rid,i)
                for rid in ports for i,side in enumerate(('left','right'))}
            inputs=(output/'student-inputs.jsonl').open('x')
            commands=(output/'commands.jsonl').open('x')
            evaluations=(output/'eval-only.jsonl').open('x')
            streams.extend([inputs,commands,evaluations])
            review=output/'review';review.mkdir()
            review_rows=[]
            tick=0
            while float(world.data.time)-origin<cap_s-1e-8:
                if (output/'SUPERVISOR_STOP.json').exists():raise KeyboardInterrupt('supervisor stop')
                now=float(world.data.time)
                tail.capture(world,ports,now)  # recording only, 10Hz, last10 SIMs
                permits=sync.tick({r:b.ready for r,b in barriers.items()},now)
                for rid,port in ports.items():
                    barrier=barriers[rid]
                    waiting=barrier.pending is not None and not permits[rid]
                    jpeg=base64.b64decode(port.capture()['image'])
                    obs,jpegs,path=histories[rid].observe(now,jpeg,skill='wait' if waiting else 'grasp',
                        object_kind='long_beam',role=plan['roles'][rid])
                    (output/path).write_bytes(jpeg)
                    inputs.write(json.dumps(obs,allow_nan=False)+'\n')
                    proposal=None;done=False
                    if barrier.pending is None:
                        proposal,done=executors[rid].step(obs,jpegs)
                        barrier.propose(proposal,done,previous[rid])
                    value,done=barrier.issue(now,previous[rid],proposal,done,permits[rid])
                    if done:done_times.setdefault(rid,now)
                    apply(port,value,now,previous[rid])
                    histories[rid].issue(value);previous[rid]=value
                    commands.write(json.dumps(dict(t=now,robot=rid,command=value,done=done,
                        ready=barrier.ready,permit=permits[rid],waiting=waiting),allow_nan=False)+'\n')
                # Private evaluation truth is created AFTER commands, and never
                # passed into histories, executor, barrier, worker or sync.
                truth=snapshot(world,inst,plan['roles'],scene)
                contacts=[];force_buffer=np.zeros(6)
                for contact_index in range(world.data.ncon):
                    contact=world.data.contact[contact_index]
                    a,b=int(contact.geom1),int(contact.geom2)
                    finger=a if b in target_geoms else b if a in target_geoms else None
                    if finger in finger_ids:
                        rid,index=finger_ids[finger]
                        mujoco.mj_contactForce(world.model,world.data,contact_index,force_buffer)
                        contacts.append(dict(robot=rid,finger=index,position_xyz=contact.pos.tolist(),
                            normal_force_n=abs(float(force_buffer[0]))))
                assigned=assigned_forces(contacts,truth['beam']['ends'],plan['roles'])
                forces=[f for rid in ports for f in assigned[rid]]
                score.add(now,clearance=truth['beam']['min_z'],tilt=truth['beam']['tilt_deg'],
                    forces=forces,weld=bool(world.data.eq_active.any()))
                unrestricted_score.add(now,clearance=truth['beam']['min_z'],tilt=truth['beam']['tilt_deg'],
                    forces=[f for rid in ports for f in truth['contacts'][rid]],weld=bool(world.data.eq_active.any()))
                geometry={}
                for rid,role in plan['roles'].items():
                    pose=truth['robots'][rid]['pose'];end=truth['beam']['ends'][role]
                    yaw=truth['beam']['pose'][2]+(math.pi if role=='blue' else 0.)
                    # Pinned teacher STATION_M=.203, XY_TOL=.03, YAW_TOL=.06;
                    # .8m is its existing visible local handoff envelope. These
                    # are evaluator diagnostics, never correction/READY inputs.
                    goal=(end[0]-.203*math.cos(yaw),end[1]-.203*math.sin(yaw))
                    geometry[rid]=dict(end_distance_m=math.dist(pose[:2],end[:2]),
                        station_error_m=math.dist(pose[:2],goal),
                        yaw_error_rad=abs(math.atan2(math.sin(yaw-pose[2]),math.cos(yaw-pose[2]))))
                passed=dict(approach=all(g['end_distance_m']<=.8 for g in geometry.values()),
                    alignment=all(g['station_error_m']<=.03 and g['yaw_error_rad']<=.06 for g in geometry.values()),
                    READY=all(b.ready for b in barriers.values()),grasp=min(forces)>=.5,
                    lift_3s=score.record()['lift_success'])
                funnel.add(now,passed)
                # Same evaluation-only target gap as the existing ACT student;
                # extent is a query range, not an acceptance tolerance.
                target_gap=min(float(mujoco.mj_geomDistance(world.model,world.data,finger,g,
                    float(world.model.stat.extent),None)) for finger in finger_geoms for g in target_geoms)
                evaluations.write(json.dumps(dict(t=now,sim_s=now-origin,truth=truth,geometry=geometry,
                    target_finger_contact_rows=contacts,assigned_contact_forces=assigned,
                    target_finger_min_gap_m=target_gap,passed=passed,score=score.record(),
                    unrestricted_score=unrestricted_score.record()),allow_nan=False)+'\n')
                if tick%5==0:  # user: complete sequence at2Hz; cameras unchanged
                    row=dict(t=now,sim_s=now-origin,own={})
                    top=scene.config['static_map']['top_cameras'][0]['name']
                    name=f'{tick:06d}-overview.jpg'
                    (review/name).write_bytes(world.render_team_jpeg(camera=top));row['overview']=name
                    for rid in ports:
                        name=f'{tick:06d}-{rid}.jpg'
                        (review/name).write_bytes(base64.b64decode(ports[rid].capture()['image']))
                        row['own'][rid]=name
                    review_rows.append(row)
                    for stream in streams:stream.flush()
                    write_json(output/'progress.json',dict(sim_s=now-origin,done_times=done_times,
                        inference_calls=len(latencies),funnel=funnel.record()))
                if now-origin>=30.-1e-8 and 'first30_speed' not in report:
                    report['first30_speed']=dict(sim_s=now-origin,wall_s=time.monotonic()-started,
                        wall_per_sim=(time.monotonic()-started)/(now-origin),scope='shared CPU record only')
                    write_json(output/'first30-speed.json',report['first30_speed'])
                # Stop only by student completion and the inherited3.1s command
                # settle window, or SIM cap. Evaluation success cannot stop it.
                if len(done_times)==len(ports) and now-max(done_times.values())>=SoloSequence.SETTLE_S-1e-8:
                    break
                tick+=1;advance(origin+tick*c.PERIOD_S)
            sim_s=float(world.data.time)-origin
            cap_end=sim_s>=cap_s-c.PERIOD_S/2
            report.update(status='complete',complete=True,sim_s=sim_s,cap_end=cap_end,
                termination='cap_end' if cap_end else 'student_done',done_times=done_times,
                command_complete=len(done_times)==len(ports),**score.record(),
                unrestricted_lift_success=unrestricted_score.record()['lift_success'],
                max_unrestricted_stable_lift_s=unrestricted_score.max_stable_s,
                physical_success=score.record()['lift_success'] and len(done_times)==len(ports) and not cap_end,
                funnel=funnel.record(),inference_calls=len(latencies),
                inference_latency_median_s=float(np.median(latencies)) if latencies else None,
                protocol_delays_s=delays,capture_cache=capture_stats)
            write_json(output/'start-protocol.json',dict(events=sync.events,
                own_events={r:b.events for r,b in barriers.items()},delays_s=delays,
                source='unchanged pinned GraspStartSync READY/GO/ACK; close proposal only'))
            write_json(review/'manifest.json',review_rows)
    except BaseException as exc:
        report.update(status='interrupted' if isinstance(exc,KeyboardInterrupt) else 'HOST_ERROR',
            complete=False,error_type=type(exc).__name__,error=str(exc))
        raise
    finally:
        for stream in streams:stream.close()
        if worker is not None:
            worker.terminate()
            try:worker.wait(timeout=5)
            except subprocess.TimeoutExpired:worker.kill();worker.wait(timeout=5)
        if world is not None:world.close()
        tail.finish(output/'failure-tail',failed=not report['physical_success'])
        report.update(wall_s=time.monotonic()-started,loadavg_at_end=os.getloadavg())
        write_json(output/'funnel.json',dict(**funnel.record(),source=str(output/'eval-only.jsonl'),
            reason_category=report.get('termination',report['status']),blocked_object='beam_1:target_not_inferred_blocker',
            min_gap_m=target_gap,gap_scope='evaluation-only target-finger signed gap; no obstruction cause inferred',
            reproduce='python -m scripts.analyze_beamact2 --root '+str(output.parent)))
        write_json(output/'result.json',report)
        from harness.beampair_recording import compress_jsons
        compress_jsons(output)
        write_json(output/'SHA256.json',{str(p.relative_to(output)):sha256(p)
            for p in output.rglob('*') if p.is_file() and p.name!='SHA256.json'})
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--episode',type=int,required=True)
    p.add_argument('--dependency-root',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--actor-python',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',default='off',choices=('off',MODE))
    a=p.parse_args()
    plan=json.loads(a.plan.read_text())['episodes'][a.episode]
    run(plan,a.output,a.dependency_root,a.model,a.actor_python,mode=a.mode)


if __name__=='__main__':main()
