"""Oracle-only egomap60 DEV stages; existing physics/controller/checkpoint owners."""
from pathlib import Path
import argparse,contextlib,fcntl,hashlib,json,os,platform,signal,time,traceback
from types import MethodType
from harness.active_camera import bind,SEARCH
from harness.rbpf_stage_candidates import install,POPULATION,LOCAL,GATE
from scripts import run_goal_route_motion_audit as previous
from scripts import run_goal_route_continuous as continuous

ROOT=Path(__file__).resolve().parents[1]
PROFILES={'baseline':{},'a':{'rbpf_population':POPULATION},'b':{'rbpf_local_search':LOCAL},'c':{'rbpf_candidate_gate':GATE}}
SEEDS=(60011,60012,60021,60022)


def dump(p,r):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n')


def bundle(seed,source,profile,mode):
    if seed not in SEEDS or profile not in PROFILES:raise ValueError('UNREGISTERED_STAGE')
    b=previous.bundle(55001 if seed%2 else 55002,source)
    b['task']['seed']=seed;b['condition']='DEV_STAGE' if mode!='full' else 'DEV_CONTINUOUS'
    b['execution_bundle_id']=f'egomap60-{mode}-{profile}-{seed}-v1'
    b['options'].update({k:'off' for k in ('rbpf_population','rbpf_local_search','rbpf_candidate_gate')})
    b['options'].update(PROFILES[profile]);b['host']='oracle-x86'
    b['case_cap_s']=810. if mode=='full' else 150. if mode=='prepare' else 120.
    b['stage_diagnostic']=mode!='full';b['admission']='egomap60 preregistered oracle-only DEV'
    return b


@contextlib.contextmanager
def server_slot():
    if platform.system()!='Linux' or platform.machine()!='x86_64' or os.getenv('UGRP_EXECUTION_HOST')!='oracle-x86':
        raise RuntimeError('ORACLE_X86_ONLY_NO_MAC_PHYSICS')
    if os.getenv('MUJOCO_GL')!='osmesa':raise RuntimeError('OSMESA_REQUIRED')
    root=Path.home()/'ugrp-sim/egomap-slots';root.mkdir(exist_ok=True)
    held=None
    for i in range(8):
        f=(root/f'{i}.lock').open('a+')
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:f.close();continue
        f.seek(0);f.truncate();f.write(f'{os.getpid()}\n');f.flush();held=f;break
    if held is None:raise RuntimeError('EGOMAP_EIGHT_SLOTS_OCCUPIED')
    try:yield i
    finally:fcntl.flock(held,fcntl.LOCK_UN);held.close()


def enter_return(c,t):
    """DEV stage transition from own traversed graph; never inject a GT goal."""
    c.graph.seal();route=c.graph.route(c.graph.anchor,0)
    if route is None:raise ValueError('NO_OWN_TEMPORAL_RETURN_PATH')
    c.route=route;c.cursor=0;c.stage='return';c.active=None;c.streak=0;c.leg_start=t
    c.done=False;c.declared=False;c.navigator.reset_action()
    c.event(t,'stage_probe_return_started',length_m=route['length_m'],synthetic_task_transition=True)


def checkpoint_save(backend,c,*,tick,start,source,out):
    from scripts.dev_pair_checkpoint import DevCheckpoint
    cp=DevCheckpoint(checkpoint_dir=out/'checkpoints')
    save=bind(DevCheckpoint.save,code_identity=lambda:dict(head=source,dirty=False,branch='claude/ego-wall-map'))
    save(cp,tick,backend=backend,runtime=c,start=start,commands={},result={},reasons=['first_own_B_confirmation'])
    return cp.saved[-1]


def checkpoint_load(path,out):
    from scripts.dev_pair_checkpoint import DevCheckpoint,find_checkpoint
    row=find_checkpoint(path)
    cp=DevCheckpoint(resume=dict(row=row,file=str(path),source_case_dir=row['case_dir'],labels={'egomap60':True,'host':'oracle-x86'}))
    out.mkdir(parents=True,exist_ok=False)
    result={'loadavg_start':list(os.getloadavg())}
    backend,c,start,tick,_=cp.restore(out,result)
    # Stream prefixes are inherited; RGB prefix remains in the retained source.
    return backend,c,start,tick,row


def run(args):
    out=args.output.resolve();source=ROOT.name
    if len(source)!=40 or any(v not in '0123456789abcdef' for v in source):raise ValueError('COMMITTED_ARCHIVE_SHA_REQUIRED')
    if out.exists():raise ValueError('PRESERVE_EXISTING_OUTPUT')
    b=bundle(args.seed,source,args.profile,args.mode)
    from sim.goal_route_assets import PhysicsBackend,xml_preflight
    receipt,_=xml_preflight(b,args.seed)  # no model created before XML admission
    with server_slot() as slot:
        started=time.monotonic();backend=c=None;result=dict(status='HOST_ERROR',host='oracle-x86',source_sha=source,seed=args.seed,
            profile=args.profile,mode=args.mode,slot=slot,model_calls=0,loadavg_start=list(os.getloadavg()),platform=platform.platform(),stage_only=args.mode!='full')
        def deadline(*_):raise TimeoutError('REGISTERED_HOST_BUDGET')
        signal.signal(signal.SIGALRM,deadline);signal.alarm(3600 if args.mode=='full' else 1800)
        try:
            from harness.active_wall_vision import observe
            from scripts.run_wall_servo_stiffness import arm
            if args.mode=='stage':
                if args.checkpoint is None:raise ValueError('CHECKPOINT_REQUIRED')
                backend,c,original_start,tick,cp=checkpoint_load(args.checkpoint.resolve(),out)
                if cp['code']['head']!=source:raise ValueError('STAGE_SOURCE_MISMATCH')
                result['checkpoint']=dict(path=str(args.checkpoint.resolve()),sha256=cp['sha256'],source=cp['code']['head'],sim_s=cp['sim_s'])
                install(c.explorer.memory.self_map,**PROFILES[args.profile]);initial_tick=tick
            else:
                out.mkdir(parents=True,exist_ok=False);backend=PhysicsBackend(b,out,seed=args.seed);backend.reset(5.)
                original_start=backend.now
                for action in arm(SEARCH):backend.issue('r3',action)
                explorer=continuous.actor('r3',original_start,SEARCH,active_mapping='frontier_rbpf_v1',active_loop='information_gain_v1',seed=args.seed,
                    active_recovery='nav2_frontier_v1',navigation_map='public_ros_v8',motion_model='s2_pulse_v122_rotL_v1')
                continuous.base.install_profile(explorer.memory.self_map,profile='egomap27_wide')
                install(explorer.memory.self_map,**PROFILES[args.profile]);c=continuous.controller(explorer);tick=initial_tick=0
            start=backend.now;end=start+b['case_cap_s'];backend.set_deadline(end)
            result.update(start_sim_s=start,original_start_sim_s=original_start)
            dump(out/'bundle.json',b);dump(out/'preflight.json',receipt)
            entered=False;last_revision=None
            while backend.now<=end+1e-8:
                t=backend.now
                if args.mode=='stage' and t-start>=60 and not entered:
                    enter_return(c,t);entered=True
                obs,rgb=backend.capture()['r3']
                if tick>=10:
                    detection=observe(rgb,SEARCH,body_settling=.7)
                    image=out/f'robots/r3/rgb/{backend.frame-1:05d}.jpg'
                    frame_hash=hashlib.sha256(image.read_bytes()).hexdigest()
                    cmd,trace=c.receive(robot_id='r3',t=t,frame_id=obs['frame_id'],rgb=rgb,servo=SEARCH,observation=detection,
                        frame_sha256=frame_hash,own_range=backend.own_range())
                    backend._append('own-controller.jsonl',trace);backend._append('own-contacts.jsonl',dict(t=t,frame_id=obs['frame_id'],**detection))
                    g=c.explorer.memory.self_map
                    backend._append('frontend-covariances.jsonl',dict(t=t,frame_id=obs['frame_id'],pose=list(g.odom.pose),covariance=g.odom.covariance.tolist()))
                    revision=(g.revision,g.best,g.resamples)
                    if revision!=last_revision:
                        backend._append('online-maps.jsonl',dict(t=t,frame_id=obs['frame_id'],grid=g.export()))
                        last_revision=revision
                    backend.issue('r3',{k:v for k,v in cmd.items() if k!='t'});c.command(cmd)
                backend.eval_sample()
                if tick%25==0:
                    progress=dict(sim_s=t-start,frame=tick,stage=c.stage,reached=list(c.reached))
                    dump(out/'progress.json',progress);print(json.dumps(progress),flush=True)
                if c.done or t>=end-1e-8:break
                backend.advance_to(round(t+.2,9));tick+=1
                if args.mode=='prepare' and 'B' in c.entities:
                    result['saved_checkpoint']=checkpoint_save(backend,c,tick=tick,start=original_start,source=source,out=out)
                    break
            result.update(status='RECORDED',frames=backend.frame,total_sim_s=backend.now,stage=c.stage,
                declared_B='B' in c.reached,declared_return=c.declared)
            if args.mode=='prepare' and 'saved_checkpoint' not in result:result['status']='PREPARE_B_UNOBSERVED'
        except Exception as e:
            result.update(status='PHYSICAL_FAILURE' if type(e).__name__=='PhysicalStop' else 'HOST_ERROR',failure=dict(type=type(e).__name__,message=str(e)),
                total_sim_s=backend.now if backend else None,frames=backend.frame if backend else 0)
            traceback.print_exc()
        finally:
            signal.alarm(0)
            if backend is not None:backend.close()
            out.mkdir(parents=True,exist_ok=True)
            if c is not None:
                g=c.explorer.memory.self_map
                for name,value in [('route-map',c.snapshot()),('utility-events',c.events),('frontend-grid',g.export()),('frontend-ledger',g.ledger),
                    ('decisions',g.decisions),('heading-decisions',c.heading_host.rows),('stage-candidates',getattr(g,'_stage_candidates',{}))]:dump(out/(name+'.json'),value)
            result.update(wall_s=time.monotonic()-started,loadavg_end=list(os.getloadavg()))
            dump(out/'result.json',result)
            dump(out/'artifacts.sha256.json',{str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifacts.sha256.json'})
        return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=('prepare','stage','full'),required=True);p.add_argument('--profile',choices=PROFILES,default='baseline')
    p.add_argument('--seed',type=int,choices=SEEDS,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--checkpoint',type=Path)
    a=p.parse_args();r=run(a);print(json.dumps(r),flush=True);return 0 if r['status']=='RECORDED' else 1

if __name__=='__main__':raise SystemExit(main())
