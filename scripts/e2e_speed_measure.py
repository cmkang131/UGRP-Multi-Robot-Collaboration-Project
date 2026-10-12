"""External bounded measurement: never changes the authored execution bundle."""
import cProfile
import hashlib
from itertools import chain
import json
from pathlib import Path
import pstats
import struct
import time


def profile_rows(stats, sim_s):
    rows=[]
    for (filename,line,function),(primitive,calls,self_s,cumulative_s,_) in stats.stats.items():
        rows.append(dict(file=filename,line=line,function=function,calls=calls,
                         self_s=self_s,cumulative_s=cumulative_s,
                         cumulative_wall_per_sim=cumulative_s/sim_s))
    return sorted(rows,key=lambda x:x['cumulative_s'],reverse=True)[:20]


AUDIT_MODES=('off','binary_v1','both_v1','none','final_v1')
# Row keys per scheme. Legacy/default rows keep exactly {robot,frame,t,sha256}.
SCHEMES={'json_v1':'sha256','binary_v1':'binary_sha256'}
BINARY_MAGIC=b'ugrp.rbpf_audit.binary_v1\x00'


def _array_part(h,grid):
    for name in ('poses','pending_cov','weights','log_weights'):
        a=getattr(grid,name)
        h.update(name.encode());h.update(a.dtype.str.encode());h.update(str(a.shape).encode());h.update(a.tobytes())


def rbpf_digest(robot):
    """Raw float bytes, RNG, all particle grids/history and revision after receive."""
    grid=robot.goal.explorer.memory.self_map
    h=hashlib.sha256()
    _array_part(h,grid)
    value=dict(rng=grid.rng.bit_generator.state,best=grid.best,resamples=grid.resamples,
               revision=grid.revision,histories=grid.histories,
               maps=[sorted(g.cells.items()) for g in grid.maps])
    h.update(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
    return h.hexdigest()


def _length(n):return n.to_bytes(8,'big')


def _encode(out,o):
    """Prefix-free typed encoding of the JSON value tree (str-keyed dicts sorted)."""
    if o is None:out+=b'N'
    elif o is True:out+=b'T'
    elif o is False:out+=b'F'
    elif isinstance(o,int):
        n=int(o);raw=n.to_bytes(n.bit_length()//8+1,'big',signed=True)
        out+=b'I'+_length(len(raw))+raw
    elif isinstance(o,float):out+=b'D'+struct.pack('>d',o)
    elif isinstance(o,str):
        raw=o.encode('utf-8','surrogatepass');out+=b'S'+_length(len(raw))+raw
    elif isinstance(o,(list,tuple)):
        out+=b'L'+_length(len(o))
        for x in o:_encode(out,x)
    elif isinstance(o,dict):
        if any(type(k) is not str for k in o):raise TypeError('RBPF_BINARY_STR_KEYS_REQUIRED')
        out+=b'M'+_length(len(o))
        for k in sorted(o):_encode(out,k);_encode(out,o[k])
    else:raise TypeError('RBPF_BINARY_UNSUPPORTED:'+type(o).__name__)


def _cells(out,cells):
    """One particle map = sorted (int,int)->float items, as big-endian i8/f8 columns."""
    import numpy as np
    if (cells and set(map(type,cells))=={tuple} and set(map(len,cells))=={2}
            and set(map(type,chain.from_iterable(cells)))=={int} and set(map(type,cells.values()))=={float}):
        try:keys=np.fromiter(chain.from_iterable(cells),np.int64,2*len(cells)).reshape(-1,2)
        except OverflowError:keys=None  # beyond int64: typed fallback
        if keys is not None:
            values=np.fromiter(cells.values(),np.float64,len(cells))
            order=np.lexsort((keys[:,1],keys[:,0]))  # == sorted(items): unique (x,y) keys
            out+=b'G'+_length(len(cells))+keys[order].astype('>i8').tobytes()+values[order].astype('>f8').tobytes()
            return
    _encode(out,sorted(cells.items()))


def rbpf_digest_binary(robot):
    """rbpf_audit_hash=binary_v1: the same state as rbpf_digest, canonical binary.

    Arrays: the identical name/dtype(endianness)/shape header + C-order bytes.
    Scalars/RNG: prefix-free typed fields in fixed order. Histories: the same
    canonical JSON bytes, length-prefixed. Maps: lexsorted big-endian columns
    (typed fallback). Any change of the JSON digest input changes this input.
    """
    grid=robot.goal.explorer.memory.self_map
    h=hashlib.sha256(BINARY_MAGIC)
    _array_part(h,grid)
    out=bytearray()
    for name,value in (('rng',grid.rng.bit_generator.state),('best',grid.best),
                       ('resamples',grid.resamples),('revision',grid.revision)):
        _encode(out,name);_encode(out,value)
    histories=json.dumps(grid.histories,sort_keys=True,separators=(',',':')).encode()
    out+=b'H'+_length(len(histories))+histories
    out+=b'P'+_length(len(grid.maps))
    for g in grid.maps:_cells(out,g.cells)
    h.update(out)
    return h.hexdigest()


def audit_row(robot,mode,seconds):
    """One receive's audit row; mode off keeps the legacy bytes/keys exactly."""
    if mode not in AUDIT_MODES:raise ValueError('UNKNOWN_RBPF_AUDIT_HASH')
    row=dict(robot=robot.robot_id,frame=robot.frame.index,t=robot.now)
    if mode in ('off','both_v1'):
        start=time.perf_counter();row['sha256']=rbpf_digest(robot);seconds['json_v1']+=time.perf_counter()-start
    if mode in ('binary_v1','both_v1'):
        start=time.perf_counter();row['binary_sha256']=rbpf_digest_binary(robot);seconds['binary_v1']+=time.perf_counter()-start
    return row


def hash_schemes(rows):
    return {name for name,key in SCHEMES.items() if rows and all(key in r for r in rows)}


def compare_rbpf(a,b,scheme=None):
    """Like-with-like only: both runs must carry the compared scheme on every row."""
    sa,sb=hash_schemes(a),hash_schemes(b);common=sa&sb
    if not common or (scheme is not None and scheme not in common):
        raise ValueError(f'RBPF_HASH_SCHEME_MISMATCH: {sorted(sa)} vs {sorted(sb)}'
                         f'{"" if scheme is None else " requested "+scheme}; compare json_v1 with json_v1 or binary_v1 with binary_v1')
    scheme=scheme or ('json_v1' if 'json_v1' in common else 'binary_v1');key=SCHEMES[scheme]
    ident=lambda r:(r['robot'],r['frame'],r['t'])
    if [ident(r) for r in a]!=[ident(r) for r in b]:raise ValueError('RBPF_ROWS_NOT_ALIGNED')
    bad=[ident(x) for x,y in zip(a,b) if x[key]!=y[key]]
    return dict(scheme=scheme,N=len(a),n=len(a)-len(bad),mismatches=bad[:10],equal=not bad)


def hash_mapping(rows):
    """Validation (both_v1) runs: the recorded json_v1 -> binary_v1 mapping."""
    if 'json_v1' not in hash_schemes(rows) or 'binary_v1' not in hash_schemes(rows):
        raise ValueError('BOTH_V1_ROWS_REQUIRED')
    forward={}
    for r in rows:forward.setdefault(r['sha256'],set()).add(r['binary_sha256'])
    return dict(rows=len(rows),distinct_json=len(forward),distinct_binary=len({r['binary_sha256'] for r in rows}),
                functional=all(len(v)==1 for v in forward.values()),
                mapping=[dict(robot=r['robot'],frame=r['frame'],t=r['t'],json_v1=r['sha256'],binary_v1=r['binary_sha256']) for r in rows])


def measured_run(run,b,out,receipt,limit,profile,audit='off'):
    if not 30<=limit<=90:raise ValueError('MEASUREMENT_REQUIRES_30_TO_90_SIM_SECONDS')
    if audit not in AUDIT_MODES:raise ValueError('UNKNOWN_RBPF_AUDIT_HASH')
    import mujoco
    from sim.e2e_ownmap_live import PhysicsBackend
    from harness.e2e_live_mapping import Robot
    from harness.e2e_result_writer import write
    root=out.parent
    profiler=cProfile.Profile() if profile else None
    timers=[];states=[];backend_ref=[];origin=[None]
    original_receive=Robot.receive
    last_robots={}
    hash_seconds=[0.];scheme_seconds={'json_v1':0.,'binary_v1':0.}
    def receive(self,*args,**kwargs):
        result=original_receive(self,*args,**kwargs)
        start=time.perf_counter()
        if audit=='final_v1':last_robots[self.robot_id]=self
        elif audit!='none':states.append(audit_row(self,audit,scheme_seconds))
        hash_seconds[0]+=time.perf_counter()-start
        return result
    class MeasuredBackend(PhysicsBackend):
        def reset(self,cap):
            result=super().reset(cap);origin[0]=self.now;backend_ref.append(self)
            return result
        def advance_to(self,at):
            result=super().advance_to(at)
            if origin[0] is not None and self.now-origin[0]>=limit-1e-8:
                raise KeyboardInterrupt('MEASUREMENT_SIM_LIMIT')
            return result
        def close(self):
            if profile:
                for i,timer in enumerate(self.world.data.timer):
                    timers.append(dict(timer=mujoco.mjtTimer(i).name,duration_s=timer.duration,
                                       calls=timer.number,wall_per_sim=timer.duration/limit))
            return super().close()
    Robot.receive=receive
    previous=mujoco.get_mjcb_time()
    if profile:mujoco.set_mjcb_time(time.perf_counter)
    wall=time.perf_counter();cpu=time.process_time()
    try:
        if profiler:profiler.enable()
        result=run(b,out,receipt,backend_factory=MeasuredBackend)
    finally:
        if profiler:profiler.disable()
        wall=time.perf_counter()-wall;cpu=time.process_time()-cpu
        Robot.receive=original_receive
        if profile:mujoco.set_mjcb_time(previous)
    final_hash_seconds=0.
    if audit=='final_v1':
        start=time.perf_counter()
        states=[audit_row(robot,'binary_v1',scheme_seconds) for robot in last_robots.values()]
        final_hash_seconds=time.perf_counter()-start
    sim=result.get('sim_s',0.)
    record=dict(sim_s=sim,wall_s=wall,cpu_s=cpu,wall_per_sim=wall/sim if sim else None,
                cpu_per_sim=cpu/sim if sim else None,rbpf_hash_wall_s=hash_seconds[0],
                profiling=profile,includes_setup_and_finalization=True,mujoco_timers=timers,
                expected_stop=result.get('failure')=='MEASUREMENT_SIM_LIMIT',
                cprofile_top20=profile_rows(pstats.Stats(profiler),sim) if profiler and sim else [])
    record.update(rbpf_audit_hash=audit,final_hash_wall_s=final_hash_seconds)
    if audit in ('binary_v1','both_v1'):
        used=('json_v1','binary_v1') if audit=='both_v1' else ('binary_v1',)
        record.update(rbpf_audit_hash=audit,rbpf_hash_scheme_wall_s={k:scheme_seconds[k] for k in used})
    if profiler:profiler.dump_stats(str(root/'cprofile.pstats'))
    write(root/'measurement.json',record)
    write(root/'rbpf-sha256.json',states)
    if audit=='both_v1':write(root/'rbpf-hash-mapping.json',hash_mapping(states))
    return result


def main(argv=None):
    import argparse
    p=argparse.ArgumentParser(description='Compare RBPF audit hashes of two runs (like-with-like only).')
    p.add_argument('a',type=Path);p.add_argument('b',type=Path)
    p.add_argument('--scheme',choices=tuple(SCHEMES))
    a=p.parse_args(argv)
    result=compare_rbpf(json.loads(a.a.read_text()),json.loads(a.b.read_text()),a.scheme)
    print(json.dumps(result));return 0 if result['equal'] else 1


if __name__=='__main__':raise SystemExit(main())
