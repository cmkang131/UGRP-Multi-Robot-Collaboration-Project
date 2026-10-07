"""v8 evaluation adapter: integer 100 ms logical time, unchanged task/scorer.

Derived from frozen run_persistent. No changes to B time threshold or environment.
ROS sec/nanosec principle; finite 900s timestamps can be represented exactly at
observation boundaries. No MuJoCo/model/timing benchmark.
"""
from collections import Counter
import json
import numpy as np
from harness.self_odom_grid import transform


class _ZeroVelocityStop:
    """v8 2D cmd_vel stop adapter, NOT a physical braking model.

    The final zero-velocity output must not be smoothed into residual motion by
    the legacy M1 integrator. Preserve active-command dynamics and all covariance.
    Only own commands are inspected; no poses, contacts or geometry trigger this.
    """
    def __init__(self,odometry):
        self.odometry=odometry
        self.zero_commands=0

    def command(self,row):
        result=self.odometry.command(row)  # finish integration up to issue time
        zero=row['kind'] in ('stop','hold') or (
            row['kind'] in ('mecanum','drive') and
            all(float(row.get(k,0.))==0. for k in ('forward','left','turn')))
        if zero:
            self.odometry._predictor.vel[:]=0.
            self.zero_commands+=1
        return result

    def __getattr__(self,name):return getattr(self.odometry,name)


def velocity_stop(odometry,*,navigation='off'):
    if navigation=='off':return odometry
    if navigation!='public_ros_v8':raise ValueError('EXPLICIT_V8_STOP_ADAPTER_REQUIRED')
    return _ZeroVelocityStop(odometry)


def observation_time(frame):
    return (30*frame+20)/10


def control_end_time(frame,tick):
    return (30*frame+21+tick)/10


def episode(runner,index,start_id,seed,split,condition,sensing,out):
    RectangleOracleWorld,RectangleWorld = runner.RectangleOracleWorld,runner.RectangleWorld
    start_pose,static_inputs,PublicActor = runner.start_pose,runner.static_inputs,runner.PublicActor
    issued_passage,write,SETTINGS = runner.issued_passage,runner.write,runner.SETTINGS
    world = (RectangleOracleWorld if sensing=='oracle' else RectangleWorld)(index,start_pose(index,start_id,seed),seed,'development' if split=='development' else 'confirmation')
    actor = PublicActor(condition,*(static_inputs(world) if condition=='static_map' else (None,None)),navigation='public_ros_v3')
    world.motion=velocity_stop(world.motion,navigation=actor.option)
    actor.odom=velocity_stop(actor.odom,navigation=actor.option)
    logs,truth_logs,commands,contact_inputs = [],[],[],[]
    wait_checks=[]
    track_truth = {}
    first = None
    status = 'budget'
    if world.collision(world.pose[:2]):
        status = 'HOST_SETUP_ERROR'
    else:
        for frame in range(300):
            if actor.t>=900-1e-8 or world.distance>=40 :
                status = 'budget'
                break
            # Keep zero cmd_vel and contact callbacks alive during the 2 s wait.
            # Same integer observation schedule; no planner/recovery motion here.
            before=world.pose.copy()
            start_distance=world.distance
            start_contacts=world.collisions
            max_speed=0.
            for tick in range(round(actor.t*10)+1,round(observation_time(frame)*10)+1):
                hold=actor.wait_command()
                commands.append(dict(frame=frame,tick=tick,t=actor.t,phase='observation_wait',
                    pose_odom=list(actor.odom.pose),command=hold))
                actor.odom.command(hold)
                world.advance(hold,tick/10)
                actor.odom.advance(tick/10)
                actor.t=actor.odom.t
                max_speed=max(max_speed,float(np.max(np.abs(world.motion._predictor.vel))))
                sample=world.contact_sample(actor.t)
                contact_inputs.append(sample)
                actor.receive_contact(sample)
            wait_checks.append(dict(frame=frame,t=actor.t,phase='observation_wait',
                pose_delta=(world.pose-before).tolist(),distance_m=world.distance-start_distance,
                max_abs_model_velocity=max_speed,new_contacts=world.collisions-start_contacts))
            observation,patches,truth = world.observe(frame)
            actor.steps = frame
            accepted = actor.receive(observation,patches)
            for patch,true in zip(accepted,truth):
                evidence = track_truth.setdefault(patch['track_id'],[])
                evidence.append(bool(true))
                if patch['confirmed_t'] is not None:
                    correct = sum(evidence)>=2 and sum(evidence)>len(evidence)/2
                    first = dict(time_s=actor.t,distance_m=world.distance,true=correct,
                                 true_views=sum(evidence),total_views=len(evidence))
                    status = 'B_confirmed' if correct else 'B_false_confirmed'
                    break
            plan = actor.plan()
            logs.append(dict(frame=frame,t=actor.t,pose_odom=list(actor.odom.pose),
                             observation=observation,patches=accepted,plan=plan))
            truth_logs.append(dict(frame=frame,t=actor.t,pose_world=world.pose.tolist(),
                coverage=world.coverage(),B_component_truth=truth,distance_m=world.distance))
            if first:
                break
            if actor.navigator.failed or actor.navigator.finished:
                status='recovery_exhausted' if actor.navigator.failed else 'exploration_finished'
                break
            # Public path tracker operates at 10 Hz during the same one-second motion interval.
            for tick in range(10):
                command = actor.command(plan)
                commands.append(dict(frame=frame,tick=tick,t=actor.t,pose_odom=list(actor.odom.pose),command=command))
                issued_passage(world,command,plan,actor.odom.pose,actor.t)
                actor.odom.command(command)
                end = control_end_time(frame,tick)
                world.advance(command,end)
                actor.odom.advance(end)
                actor.t = actor.odom.t
                sample = world.contact_sample(actor.t)
                contact_inputs.append(sample)
                if actor.receive_contact(sample):
                    stop = dict(t=actor.t,kind='stop')
                    world.advance(stop,actor.t)
                    plan = actor.plan()  # apply newly received bumper evidence before reversing
                    commands.append(dict(frame=frame,tick=tick,t=actor.t,pose_odom=list(actor.odom.pose),command=stop))
    result = dict(scenario=f's{index}',start=start_id,seed=seed,split=split,condition=condition,sensing=sensing,
        status=status,first_B=first,time_s=actor.t,distance_m=world.distance,coverage=world.coverage(),
        collisions=world.collisions,door_attempts=world.door_attempts,wrong_door_attempts=world.wrong_doors,
        candidate_passage_attempts=world.candidate_attempts,false_candidate_passage_attempts=world.false_candidate_attempts,
        plans=actor.counts,navigation_events=dict(Counter(e['reason'] for e in actor.navigator.events)),
        observations=len(logs),sensor_draws=world.sensor_counters,
        end_position_error_m=float(np.linalg.norm(transform([actor.odom.pose[:2]],world.start)[0]-world.pose[:2])),
        sources=world.sources,options=SETTINGS,passage_scoring='issued_translation_public_v1')
    out.mkdir(parents=True,exist_ok=False)
    for name,rows in [('actor',logs),('eval_only',truth_logs),('commands',commands),('navigation_events',actor.navigator.events),('contact_inputs',contact_inputs),
                      ('eval_contacts',world.contact_events)]:
        (out/(name+'.jsonl')).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))
    write(out/'monitor.json',getattr(actor,'monitor_log',[]))
    write(out/'eval_wait_checks.json',wait_checks)
    write(out/'result.json',result)
    write(out/'eval_path.json',world.path)
    write(out/'own_grid.json',dict(resolution_m=.1,cells=[[*c,v] for c,v in sorted(actor.grid.odds.items())]))
    return result
