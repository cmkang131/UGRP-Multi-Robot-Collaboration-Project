"""CPU-only profile summary. Missing/running/error rows are never zero timings."""
import argparse
import hashlib
import json
from pathlib import Path


def collect(root):
    rows=[]
    for n in (1,4,16,64):
        raw=root/f'n{n}';summary=raw/'summary.json';profile=raw/'profile.json'
        row=dict(nworld=n,load='exclusive_gcp3',status='UNRETRIEVED',raw=str(raw),timing=None)
        if not summary.is_file():
            if raw.exists():row['status']='RUNNING_OR_HOST_ERROR_UNRESOLVED'
            rows.append(row);continue
        report=json.loads(summary.read_text());row.update(status=report['status'],
            source_sha=report['source_sha'],host=report['host'],shared_load=report['shared_load'],
            sim_s=report.get('batch_sim_s'),task_outcome='unmeasured',errors=report['errors'])
        if report['status']=='PROFILE_COMPLETE' and not profile.is_file():
            row.update(status='PROFILE_ARTIFACT_MISSING',errors=[dict(category='HOST_ERROR',
                reason='completed marker without required profile.json',blocked_object=str(profile),minimum_gap_m=None)])
        if profile.is_file():
            value=json.loads(profile.read_text());phases={}
            for group in value['groups']:
                for name,stats in group['phases'].items():
                    target=phases.setdefault(name,{k:0 for k in stats})
                    for key,val in stats.items():target[key]+=val
            total=lambda predicate,key:sum(v[key] for k,v in phases.items() if predicate(k))
            row['timing']=dict(
                physics_device_s=total(lambda k:k=='physics_graph','device_s'),
                render_device_s=total(lambda k:k in ('render_refit_gpu','render_extract_gpu','render_kinematics_gpu'),'device_s'),
                python_control_wall_s=total(lambda k:k in ('command_python','controller_python'),'wall_s'),
                h2d_allocate_copy_wall_s=total(lambda k:k in ('command_h2d','render_model_h2d'),'wall_s'),
                d2h_blocking_wall_s=total(lambda k:'d2h' in k,'wall_s'),
                d2h_bytes=total(lambda k:'d2h' in k,'bytes'),
                explicit_completion_wait_s=total(lambda k:True,'wait_s')+total(lambda k:k.endswith('existing_sync'),'wall_s'),
                explicit_sync_calls=total(lambda k:True,'explicit_syncs'),
                blocking_numpy_calls=total(lambda k:True,'implicit_syncs'))
            row['ranked_exclusive_wall_phases']=sorted((dict(phase=k,**v) for k,v in phases.items()
                if not k.endswith('_total')),key=lambda r:r['wall_s'],reverse=True)
            row['profile_sha256']=hashlib.sha256(profile.read_bytes()).hexdigest()
        rows.append(row)
    return dict(schema='warp9.phase_scaling.v1',rows=rows,
        scope='intrusive CUDA event intervals and host phase timings; columns overlap, not additive; no task success evidence',
        unresolved=['device event interval includes scheduling gaps, not kernel busy sum',
                    'blocking numpy transfer includes its implicit synchronization',
                    'uninstrumented N16 first30/transport/place/full/E2E remain separate gates'])


def markdown(result):
    text=['|load|N|status|SIM s|physics GPU s|render GPU s|Python s|H2D alloc/copy s|D2H blocking s|explicit wait s|numpy calls|',
          '|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in result['rows']:
        t=row['timing'] or {}
        values=[row['load'],row['nworld'],row['status'],row.get('sim_s')]
        values += [t.get(k) for k in ('physics_device_s','render_device_s','python_control_wall_s',
            'h2d_allocate_copy_wall_s','d2h_blocking_wall_s','explicit_completion_wait_s','blocking_numpy_calls')]
        text.append('|'+ '|'.join('—' if v is None else f'{v:.6f}' if isinstance(v,float) else str(v) for v in values)+'|')
    text += ['', 'Shared gcp2 warp7 R3 (별도 코호트): N16·2그룹·0.4 SIM s / loop145.099 s; command+physics97.792 s, render+평가복사35.126 s. 분리 계측 없음.',
             '', result['scope']]
    return '\n'.join(text)+'\n'


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    result=collect(a.root)
    (a.output/'summary.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    (a.output/'timing-table.md').write_text(markdown(result))


if __name__=='__main__':main()
