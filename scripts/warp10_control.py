"""Default-off local spawned CPU lanes; parent alone owns MJWarp.

Python multiprocessing spawn / Gymnasium AsyncVectorEnv pattern. Native handles
never cross a pipe. Only the existing evaluator mirror, JPEGs and issued-port
state are copied. The unchanged visible-only teacher/InputAudit still owns its
existing observation boundary; this adds no controller measurement fields.
"""
import copy,hashlib,multiprocessing,traceback,time,json
import numpy as np

PORT_FIELDS=('_servo_applied','_servo_targets','_servo_tick_time','_servo_pulses',
    '_motor_commands','_wheel_deadlines','_drive_expires_at','_busy_until','_command_expires_at')
ADVANCED_FIELDS=('_servo_applied','_servo_targets','_servo_tick_time','_motor_commands',
    '_wheel_deadlines','_drive_expires_at')

def port_state(context,fields=PORT_FIELDS):
    return {rid:dict(values={name:copy.deepcopy(getattr(p,name)) for name in fields if hasattr(p,name)},
        pulses=dict(context['world'].robot(rid).servo_command_pulses)) for rid,p in context['ports'].items()}

def apply_ports(context,state):
    if set(state)!=set(context['ports']):raise ValueError('port owner mismatch')
    for rid,row in state.items():
        p=context['ports'][rid]
        for name,value in row['values'].items():
            if name not in PORT_FIELDS or not hasattr(p,name):raise ValueError('unregistered issued state')
            setattr(p,name,copy.deepcopy(value))
        context['world'].robot(rid).servo_command_pulses.update(row['pulses'])

def initial_proof(context):
    w=context['world']
    return dict(xml_sha256=hashlib.sha256(w.scene_xml.encode()).hexdigest(),
        qpos_sha256=hashlib.sha256(w.data.qpos.tobytes()).hexdigest(),origin=context['origin'])

def get_path(obj,path):
    for name in path:obj=getattr(obj,name)
    return obj

def mirror(context,fields):
    d=context['world'].data;values={}
    for path in fields:
        value=get_path(d,path)
        values[path]=value.copy() if isinstance(value,np.ndarray) else value
    # These counts are allocated implicitly by upstream get_data_into.
    return dict(values=values,counts={k:int(getattr(d,k)) for k in ('ncon','nefc','nJ','nisland','nidof')})

def restore(context,packet):
    import mujoco
    w=context['world'];d=w.data;c=packet['counts']
    if (d.ncon,d.nefc,d.nJ)!=(c['ncon'],c['nefc'],c['nJ']):
        mujoco._functions._realloc_con_efc(d,ncon=c['ncon'],nefc=c['nefc'],nJ=c['nJ'])
    if c['nisland']>0 and (d.island_idofadr.shape[0]<c['nisland'] or d.ifrc_smooth.shape[0]<c['nidof']):
        mujoco._functions._realloc_island(d,nisland=c['nisland'],nidof=c['nidof'])
    for path,value in packet['values'].items():
        owner=d
        for name in path[:-1]:owner=getattr(owner,name)
        target=getattr(owner,path[-1])
        if isinstance(value,np.ndarray):
            if target.shape!=value.shape or target.dtype!=value.dtype:raise ValueError('evaluation mirror layout changed: '+'.'.join(path))
            target[:]=value
        else:setattr(owner,path[-1],value)
    if (d.ncon,d.nefc)!=(c['ncon'],c['nefc']):raise ValueError('evaluation counts changed')

def packet_exact(context,packet):
    for path,value in packet['values'].items():
        actual=get_path(context['world'].data,path)
        if isinstance(value,np.ndarray):
            if actual.tobytes()!=value.tobytes():return False
        elif actual!=value:return False
    return True

def worker(pipe,spec,source,out,host):
    import cv2
    # One CPU lane per allocated core; prevent nested OpenCV thread pools.
    # This is resource allocation, not a new robot acceptance threshold.
    cv2.setNumThreads(1)
    from scripts.warp5_episode import make_carry
    lane=None
    try:
        if spec['kind']!='carry':raise ValueError('CPU pool admits existing carry lanes only')
        lane,bridge=make_carry(source,spec['plan'],out,host,spec['kwargs']);c=next(lane)
        if c['kind']!='setup':raise ValueError('worker setup barrier missing')
        images={};w=c['world']
        def forbidden(*a,**kw):raise RuntimeError('controller worker cannot step or render physics')
        w._physics_step_for=forbidden;w.render_rgb=forbidden
        w.render_jpeg=lambda robot_id='r1',camera='robot_cam',**kw:images[robot_id]
        w.render_team_jpeg=lambda camera='cctv_top',**kw:images[camera]
        pipe.send(dict(kind='ready',proof=initial_proof(c),opencv_threads=cv2.getNumThreads()))
        epoch=0
        while True:
            message=pipe.recv()
            if message['op']=='close':break
            if message['epoch']!=epoch:raise ValueError('stale controller epoch')
            restore(c,message['mirror']);apply_ports(c,message['ports']);images.clear();images.update(message['images'])
            exact=packet_exact(c,message['mirror']) if epoch==0 else None
            if exact is False:raise ValueError('controller evaluation mirror changed bytes')
            try:
                started=time.perf_counter()
                event=next(lane)
                pipe.send(dict(kind='step',event=event,ports=port_state(c),mirror_exact=exact,epoch=epoch,compute_wall_s=time.perf_counter()-started))
            except StopIteration as done:
                pipe.send(dict(kind='done',result=done.value,epoch=epoch));break
            epoch+=1
    except BaseException as exc:
        try:pipe.send(dict(kind='error',reason=repr(exc),traceback=traceback.format_exc()))
        except (BrokenPipeError,EOFError):pass
    finally:
        if lane is not None:
            try:lane.close()
            except BaseException:pass
        pipe.close()

class Controllers:
    def __init__(self,runs,contexts,source,out,host):
        if len(runs)>host['cpu_count']:raise ValueError('one controller process per available CPU maximum')
        self.channels=[];self.processes=[];self.epochs=[0]*len(runs);self.audit=[]
        ctx=multiprocessing.get_context('spawn')
        try:
            for i,spec in enumerate(runs):
                parent,child=ctx.Pipe();p=ctx.Process(target=worker,args=(child,spec,source,out/f'world-{i:03d}'/'raw',host))
                p.start();child.close();self.channels.append(parent);self.processes.append(p)
            for i,pipe in enumerate(self.channels):
                result=pipe.recv()
                if result.get('kind')!='ready' or result['proof']!=initial_proof(contexts[i]):raise ValueError('spawned controller initial state/model differs: '+str(result))
                self.audit.append(dict(world=i,pid=self.processes[i].pid,initial_exact=True,mirror_exact=None,
                    opencv_threads=result['opencv_threads'],initial_command_exact=None,ticks=0,compute_wall_s=0.))
        except BaseException:
            self.close();raise

    def send(self,i,context,transport,local_index):
        fields=transport.exported_fields[local_index]
        images={name:value for (world,name),value in transport.camera_cache.items() if world==local_index and name in ('r1','r2','r3','cctv_top')}
        self.channels[i].send(dict(op='next',epoch=self.epochs[i],mirror=mirror(context,fields),
            images=images,ports=port_state(context,ADVANCED_FIELDS)))

    def receive(self,i,context):
        result=self.channels[i].recv()
        if result['kind']=='error':raise RuntimeError('controller worker '+str(i)+': '+result['reason']+'\n'+result['traceback'])
        if result['epoch']!=self.epochs[i]:raise ValueError('controller response epoch mismatch')
        self.epochs[i]+=1
        if result['kind']=='step':
            self.audit[i]['ticks']+=1;self.audit[i]['compute_wall_s']+=result['compute_wall_s']
            if result['mirror_exact'] is not None:self.audit[i]['mirror_exact']=result['mirror_exact']
        return result

    def close(self):
        for pipe,p in zip(self.channels,self.processes):
            if p.is_alive():
                try:pipe.send(dict(op='close'))
                except (BrokenPipeError,EOFError):pass
        for pipe,p in zip(self.channels,self.processes):
            p.join();pipe.close()
