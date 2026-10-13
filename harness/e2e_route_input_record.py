"""Default-off, bounded private planner I/O capture. No world/evaluator imports."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import time

OPTION='on_v1'
SCHEMA='ugrp.route_input_record.v1'
PARAMETERS=dict(max_attempts=128,max_compressed_bytes=64*1024*1024,
                max_record_bytes=2*1024*1024,max_uncompressed_bytes=16*1024*1024,
                max_index_rows=512,codec='zstd',record_scope='private_planner_only')
VERSIONS={'e2e18-v375':387,'e2e18-v381':388,'e2e18-v389':390}


def encoded(value):
    from harness.e2e_record_scalars import normalize
    return json.dumps(normalize(value),sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def geometry(state):
    """Explain the actual private goal, not the evaluator's obstacle geometry."""
    import math
    import numpy as np
    from harness.self_odom_grid import transform
    from harness.e2e_route_stage_probe import restore
    from harness.e2e_route_coverage import counts
    c=restore(state);g=c.explorer.grid;tf=np.asarray(state['map_to_odom'])
    beam=state['beam']['pose_own_m'];entity=state['entities'].get('B')
    endpoint=state.get('route_call',{}).get('endpoint')
    target=endpoint['center'] if endpoint is not None else entity['center_m'] if entity else None
    margin=.02+3*math.sqrt(float(np.linalg.eigvalsh(np.asarray(state['covariance'])[:2,:2]).max()))
    out=dict(start_own_m=beam[:2],target_own_m=target,beam_yaw_own_rad=beam[2],
        yaw_map_rad=float(tf[2]+beam[2]),pair_dimensions_m=[1.25,.4],strict_margin_m=margin,
        nominal_margin_m=.02,grid_resolution_m=g.resolution,
        unknown_policy=state['attrs'].get('route_coverage','off'),
        route_recovery=state['attrs'].get('route_recovery','off'),
        boundary_own=state.get('B_boundary'),coordinate_registration='own-estimated; unverified',
        original_grid_padding_m=.5,cell_padding_m=g.resolution*.71)
    if target is not None:
        a,b=transform([beam[:2],target],tf);out.update(start_map_m=a.tolist(),target_map_m=b.tolist())
        out['nominal_footprint_counts']={name:counts(g,p,out['yaw_map_rad'],.02) for name,p in [('start',a),('goal',b)]}
        # Exact occupied cell positions are indispensable to distinguish width,
        # yaw and mistaken goal geometry. They are PRIVATE observations only.
        yaw=out['yaw_map_rad'];co,si=math.cos(yaw),math.sin(yaw)
        out['goal_nearby_occupied_cells']=[dict(cell=list(k),center_map_m=g.point(k).tolist(),
            center_in_beam_axes_m=[float(co*(g.point(k)[0]-b[0])+si*(g.point(k)[1]-b[1])),float(-si*(g.point(k)[0]-b[0])+co*(g.point(k)[1]-b[1]))])
            for k in sorted(g.wall_frames) if g.state(k)==1 and np.linalg.norm(g.point(k)-b)<1.]
    return out


class Recorder:
    def __init__(self,root,metadata,*,limits=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=False)
        self.metadata=copy.deepcopy(metadata);self.limits=dict(PARAMETERS if limits is None else limits)
        self.attempts=self.saved=self.dropped=self.bytes=self.index_rows=0
        self.last_error=None
        self.flush()

    def flush(self):
        value=dict(schema=SCHEMA,metadata=self.metadata,limits=self.limits,attempts=self.attempts,
            saved=self.saved,dropped=self.dropped,compressed_bytes=self.bytes,index_rows=self.index_rows,last_error=self.last_error)
        tmp=self.root/'summary.tmp';tmp.write_bytes(encoded(value));tmp.replace(self.root/'summary.json')

    def append(self,row):
        if self.index_rows<self.limits['max_index_rows']:
            with (self.root/'index.jsonl').open('ab') as f:f.write(encoded(row)+b'\n')
            self.index_rows+=1

    def attempt(self,goal,original,beam,kwargs):
        from harness.e2e_route_stage_probe import capture
        self.attempts+=1;index=self.attempts
        admitted=index<=self.limits['max_attempts'] and self.bytes<self.limits['max_compressed_bytes']
        snapshot=None
        if admitted:
            try:
                snapshot=capture(goal,beam,now=kwargs['now'],profiles=kwargs['profiles'],
                    pulse_budget=kwargs.get('pulse_budget','off'),endpoint=kwargs.get('endpoint'),endpoint_sources=kwargs.get('endpoint_sources'))
            except Exception as exc:
                self.last_error=dict(type=type(exc).__name__,reason=str(exc));self.flush()
                raise RuntimeError('ROUTE_INPUT_RECORD_HOST_ERROR') from exc
        packet=None;failure=None;started=time.perf_counter()
        try:
            packet=original(beam,**kwargs)
            return packet
        except Exception as exc:
            failure=dict(type=type(exc).__name__,reason=str(exc))
            raise
        finally:
            elapsed=time.perf_counter()-started
            row=dict(attempt=index,t_sim=kwargs['now'],generated=packet is not None,
                failure=failure,planner_wall_s=elapsed,status='OMITTED_BUDGET')
            try:
                if snapshot is not None:
                    record=dict(schema=SCHEMA,metadata=self.metadata,attempt=index,snapshot=snapshot,
                        geometry=geometry(snapshot),result=dict(generated=packet is not None,failure=failure,
                        route=None if packet is None else packet['route'],
                        observed_complete=bool(packet and packet.get('observed_coverage_complete',True)),
                        diagnostics=copy.deepcopy(getattr(goal,'e2e_route_diagnostics',{})),planner_wall_s=elapsed))
                    raw=encoded(record)
                    if len(raw)<=self.limits['max_uncompressed_bytes']:
                        packed=subprocess.check_output(['zstd','-q','-c','-3'],input=raw)
                        if len(packed)<=min(self.limits['max_record_bytes'],self.limits['max_compressed_bytes']-self.bytes):
                            restored=subprocess.check_output(['zstd','-q','-d','-c'],input=packed)
                            if restored!=raw:raise ValueError('ROUTE_RECORD_ZSTD_ROUNDTRIP')
                            name=f'{index:06d}.json.zst'
                            with (self.root/name).open('xb') as f:f.write(packed)
                            self.bytes+=len(packed);self.saved+=1
                            row.update(status='SAVED',file=name,sha256=hashlib.sha256(packed).hexdigest(),
                                uncompressed_sha256=hashlib.sha256(raw).hexdigest(),compressed_bytes=len(packed),uncompressed_bytes=len(raw))
                if row['status']!='SAVED':self.dropped+=1
                self.append(row);self.flush()
            except Exception as exc:
                self.last_error=dict(type=type(exc).__name__,reason=str(exc));self.flush()
                # Required evidence failure is a host error, not a planner miss.
                raise RuntimeError('ROUTE_INPUT_RECORD_HOST_ERROR') from exc


def install(goal,option='off',*,root=None,metadata=None):
    if option=='off':return None
    if option!=OPTION or goal.robot_id!='r1':raise ValueError('INVALID_ROUTE_INPUT_RECORD')
    if getattr(goal,'route_input_recorder',None) is not None:raise ValueError('ROUTE_RECORDER_ALREADY_INSTALLED')
    recorder=Recorder(root,metadata or {})
    original=goal.route_to_B
    def recorded(beam,**kwargs):return recorder.attempt(goal,original,beam,kwargs)
    goal.route_to_B=recorded;goal.route_input_recorder=recorder
    return recorder


def compose(bundle,option='off'):
    if option=='off':return ()
    parent=bundle['execution_bundle_id'];v=VERSIONS.get(parent)
    if option!=OPTION or v is None:raise ValueError('ROUTE_RECORD_REQUIRES_REGISTERED_PARENT')
    bundle['route_record_parent']=parent;bundle['route_record_parameters']=copy.deepcopy(PARAMETERS)
    bundle['e2e_options']['route_input_record']=option
    bundle.update(execution_bundle_id=f'e2e18-v{v}',schema=f'ugrp.e2e_ownmap_live.v{v}',workflow_version=f'7.{v-107}.0')
    return ('harness/e2e_route_input_record.py','harness/e2e_route_stage_probe.py','harness/pair_stage_probe.py',f'configs/simulation_workflows.d/e2e18_v{v}.json')


def parent_for_validation(bundle):
    b=copy.deepcopy(bundle);parent=b.get('route_record_parent');v=VERSIONS.get(parent)
    if (v is None or b['execution_bundle_id']!=f'e2e18-v{v}' or b.get('route_record_parameters')!=PARAMETERS or b['e2e_options'].get('route_input_record')!=OPTION):
        raise ValueError('REGISTERED_ROUTE_INPUT_RECORD_REQUIRED')
    b['execution_bundle_id']=b.pop('route_record_parent');b.pop('route_record_parameters');b['e2e_options'].pop('route_input_record')
    return b
