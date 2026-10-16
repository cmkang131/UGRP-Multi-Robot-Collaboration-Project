"""CPU-only, finite raw accounting on gcp2. No model/renderer/device calls."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np

def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def summarize(root):
    result=[]
    for variant in ('before','after-r1','after-r2','after-r3','after-uninstrumented','first30','pool-smoke','first30-pool','first30-pool-r2','first30-pool-r3'):
        for n in (1,4,16,64):
            p=root/variant/f'n{n}'
            if not p.exists():continue
            s=p/'summary.json';row=dict(variant=variant,nworld=n,raw=str(p),status='UNRESOLVED_HOST_ERROR_OR_RUNNING')
            if not s.exists():result.append(row);continue
            r=read(s);row.update(status=r['status'],source_sha=r['source_sha'],host=r['host'],model_calls=r['model_calls'],errors=r['errors'],summary_sha256=digest(s))
            if (p/'progress.json').exists():
                t=read(p/'progress.json');row.update(sim_s=t['sim_s'],wall_s=t['wall_s'],
                    batch_wall_per_sim=t['wall_s']/t['sim_s'],per_execution_wall_per_sim=t['wall_s']/(t['sim_s']*n))
            if (p/'profile.json').exists():
                phases={}
                for group in read(p/'profile.json')['groups']:
                    for name,stats in group['phases'].items():
                        out=phases.setdefault(name,{k:0 for k in stats})
                        for key,value in stats.items():out[key]+=value
                row['phases']=phases
                total=lambda test,key:sum(v[key] for k,v in phases.items() if test(k))
                row['timing']=dict(physics_gpu_s=total(lambda k:k=='physics_graph','device_s'),
                    render_cpu_s=total(lambda k:k in ('render_cpu_convert','render_blend_cpu','jpeg_cpu'),'wall_s'),
                    python_control_s=total(lambda k:k in ('command_python','controller_python'),'wall_s'),
                    d2h_s=total(lambda k:'d2h' in k,'wall_s'),d2h_bytes=total(lambda k:'d2h' in k,'bytes'),
                    camera_completion_n=total(lambda k:k=='render_existing_sync','explicit_syncs'))
            if (p/'host-path-audit.json').exists():row['host_path_audit']=read(p/'host-path-audit.json')
            if (p/'first30.json').exists():row['first30']=read(p/'first30.json')
            result.append(row)
    return result

def compare(root,rows):
    values=[]
    for row in rows:
        if row['variant']=='before' or not row.get('wall_s'):continue
        # Motion/IPC cohorts have different initial cases and durations.
        # Compare only the fixed replica work, never their task trajectories.
        if row['variant'].startswith('first30'):continue
        n=row['nworld'];p=root/row['variant']/f'n{n}';base=root/'before'/f'n{n}'
        if not (base/'summary.json').exists():continue
        old=next(r for r in rows if r['variant']=='before' and r['nworld']==n)
        value=dict(variant=row['variant'],nworld=n,same_machine=row['host']['machine_type']==old['host']['machine_type'],
            same_initial=read(p/'initial-state.json')==read(base/'initial-state.json'),
            scope='separate GPU runs may differ; same-state render/export audits isolate host-copy fidelity')
        if (p/'physics-settings.json').exists() and (base/'physics-settings.json').exists():
            value['physics_settings_exact']=read(p/'physics-settings.json')==read(base/'physics-settings.json')
        if (p/'group-0-final-state.npz').exists() and (base/'group-0-final-state.npz').exists():
            aa,bb=np.load(p/'group-0-final-state.npz'),np.load(base/'group-0-final-state.npz')
            value['state']={k:dict(exact=bool(np.array_equal(aa[k],bb[k])),max_abs=float(np.max(np.abs(aa[k].astype(float)-bb[k].astype(float)))) if aa[k].size else None) for k in aa.files}
        if row['sim_s']==old['sim_s']:value['speedup']=old['wall_s']/row['wall_s']
        values.append(value)
    return values

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);rows=summarize(a.root);comparisons=compare(a.root,rows)
    write(a.output/'scaling.json',dict(rows=rows,comparisons=comparisons,
        scope='fixed initial replica diagnostics; setup excluded; instrumented and uninstrumented separate; phase columns overlap'))
    lines=['|variant|N|status|SIM s|wall s|batch wall/SIM|wall/(SIM×N)|physics GPU s|render CPU s|control Python s|D2H GB|',
           '|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        t=r.get('timing',{});v=[r['variant'],r['nworld'],r['status'],r.get('sim_s'),r.get('wall_s'),r.get('batch_wall_per_sim'),r.get('per_execution_wall_per_sim'),t.get('physics_gpu_s'),t.get('render_cpu_s'),t.get('python_control_s'),t['d2h_bytes']/1e9 if 'd2h_bytes' in t else None]
        lines.append('|'+ '|'.join('—' if x is None else f'{x:.4f}' if isinstance(x,float) else str(x) for x in v)+'|')
    (a.output/'timing-table.md').write_text('\n'.join(lines)+'\n')
    complete=[r for r in rows if r['status'] in ('PROFILE_COMPLETE','FIXED_WORK_COMPLETE','FIRST30_COMPLETE')]
    errors=[dict(variant=r['variant'],nworld=r['nworld'],status=r['status'],errors=r.get('errors',[])) for r in rows if r not in complete]
    write(a.output/'rejection-table.json',dict(unit='diagnostic_configuration',
        stages=[dict(stage='started_configurations',cumulative_pass_n=len(rows),rejected_n=0),
                dict(stage='fixed_requested_work_complete',cumulative_pass_n=len(complete),rejected_n=len(rows)-len(complete))],
        jobs=[{k:v for k,v in r.items() if k in ('variant','nworld','status','raw','source_sha')} for r in rows],errors=errors,
        task_funnel=dict(independent_trials=0,LLM_calls=sum(r.get('model_calls',0) for r in rows),place=0,complete=0),
        raw=str(a.root),reproduction=['python',__file__,'--root',str(a.root),'--output',str(a.output)]))
    write(a.output/'SHA256SUMS.json',{str(p.relative_to(a.output)):digest(p) for p in a.output.rglob('*') if p.is_file() and p.name!='SHA256SUMS.json'})
if __name__=='__main__':main()
