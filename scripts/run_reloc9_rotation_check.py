"""Prepare-only by default; GCP-only 90L/180R issued-command rotation check.

Truth is written to evaluator rows and post-run scoring, never used to stop a
turn or change a command. No RGB or top camera is captured. Not a carry result.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
TARGETS_DEG = (90., -180.)


def run(plan, out, expected_sha):
    if platform.system() != 'Linux':
        raise RuntimeError('GCP_LINUX_ONLY_NO_MAC_PHYSICS_OR_RENDER')
    from scripts.grasp_act_host import identity, require_run_root
    identity('gcp1'); require_run_root(out)
    sha = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if sha != expected_sha or subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=ROOT):
        raise ValueError('CLEAN_PINNED_SOURCE_REQUIRED')
    from sim.grasp_act_scene import make_scene
    from sim.masterpi_drive_friction_v7 import build_world, PROFILE
    from sim.grasp_act_port import DutyActPort, duty_wheels
    from sim.solo_carry_pose import CommandPose
    from scripts.run_grasp_act_teacher import write, compress_logs
    from sim.active_lookaround import wrap
    episode = json.loads(plan.read_bytes())['episodes'][0]
    scene = make_scene({**episode, 'end_color_scene':'off'})
    scene.config['setup_only']['spawns'].update(episode['spawns'])
    out.mkdir(parents=True, exist_ok=False)
    write(out/'RUN_META.json',dict(sha=sha,pr=505,branch='claude/map-carry-zone',**{'class':'dev'},batch='reloc9-rotation-check'))
    report = dict(status='HOST_ERROR',source_sha=sha,targets_deg=TARGETS_DEG,complete=False,
        physical_success=None,model_calls=0,training_rgb=False,top_rgb_control_allowed=False)
    world = None; rows = []; segments = []; wall_start = monotonic()
    try:
        world = build_world(scene,drive_profile=PROFILE,seed=episode['seed'],render=False,
            warehouse_layout=scene.engine_layout,warehouse_cargo_ids=None,roller_collision='mesh',idle_robot_contacts='off')
        scene.setup(world)
        port = DutyActPort(world,episode['robot_id'],allow_reverse=True,allow_mecanum=True)
        now = float(world.data.time)
        pose = CommandPose(episode['task_start'],now=now,drive_model_deadband_v1=True,
                           reloc9_rotation_calibration_v1=True)
        def truth_yaw():
            return float(world.robot(episode['robot_id']).base_rpy()[2])  # evaluator only
        for target_deg in TARGETS_DEG:
            start_t = now; start_est = pose.pose[2]; start_gt = truth_yaw()
            # Internal estimate can wrap; accumulated signed issued yaw cannot.
            integrated = 0.
            while abs(math.radians(target_deg)-integrated) > math.radians(1.5):
                if (out/'SUPERVISOR_STOP.json').exists():
                    raise KeyboardInterrupt('supervisor stopped this check')
                if now-start_t > 90. or monotonic()-wall_start > 1800.:
                    raise RuntimeError('ROTATION_CHECK_TIMEOUT')
                error = math.radians(target_deg)-integrated
                effort = max(-.1,min(.1,.6*error))
                wheels,durations = duty_wheels([0.,0.,.65*effort])
                issued = dict(t=now,wheels=wheels,duration_s=durations)
                port.apply(dict(kind='wheel_pulse',wheels=wheels,duration_s=durations),now)
                until = now+.1
                while float(world.data.time) < until-1e-8:
                    port.tick(float(world.data.time)); world._physics_step_for(world.robot(episode['robot_id']))
                dt = float(world.data.time)-now
                pose.issue(issued,dt); integrated += pose.last_delta[2]
                now = float(world.data.time)
                elapsed=now-pose.started
                wall_elapsed=monotonic()-wall_start
                rows.append(dict(t=now,command=issued,estimate=pose.pose,evaluation_only_yaw_rad=truth_yaw(),
                                 wall_elapsed_s=wall_elapsed))
                if elapsed >= 30. and 'first30_wall_per_sim' not in report:
                    report['first30_wall_per_sim']=wall_elapsed/elapsed
            port.stop()
            # Fixed dwell includes the physical stopping tail in evaluation;
            # no observed pose controls dwell duration or the following turn.
            for _ in range(10):
                stopped = dict(t=now,wheels=[0.]*4,duration_s=[0.]*4)
                until = now+.1
                while float(world.data.time) < until-1e-8:
                    port.tick(float(world.data.time)); world._physics_step_for(world.robot(episode['robot_id']))
                pose.issue(stopped,float(world.data.time)-now)
                now=float(world.data.time)
                rows.append(dict(t=now,command=stopped,estimate=pose.pose,evaluation_only_yaw_rad=truth_yaw(),stage='settle'))
            actual = wrap(truth_yaw()-start_gt)
            # The -180 target stops just inside pi; preserve signed branch.
            if target_deg < 0 and actual > 0:
                actual -= 2*math.pi
            ratio = actual/integrated
            segments.append(dict(target_deg=target_deg,issued_yaw_rad=integrated,actual_yaw_rad=actual,
                                 actual_over_estimated=ratio,within_target=.9 <= ratio <= 1.1))
            port.stop()
        report.update(status='complete',complete=True,segments=segments,
                      rotation_gate_passed=all(r['within_target'] for r in segments),elapsed_sim_s=now-pose.started)
    except (Exception, KeyboardInterrupt) as exc:
        report.update(error_type=type(exc).__name__,error=str(exc),segments=segments)
        raise
    finally:
        if world is not None:
            world.close()
        with (out/'rotation-ledger.jsonl').open('x') as f:
            for row in rows:
                f.write(json.dumps(row)+'\n')
        write(out/'result.json',report); compress_logs(out)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True); p.add_argument('--out',type=Path,required=True)
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--execution-host',choices=['gcp1'],default='gcp1')
    p.add_argument('--execute',action='store_true');a=p.parse_args()
    if not a.execute:
        print(json.dumps(dict(status='PREPARED_NOT_EXECUTED',targets_deg=TARGETS_DEG)));return
    print(json.dumps(run(a.plan,a.out,a.expected_source_sha)))


if __name__ == '__main__':
    main()
