"""Terminal-result delivery on GCP2; no new physical execution."""
import argparse,datetime,hashlib,json,platform,statistics,subprocess
from pathlib import Path
ROOT=Path('/home/ugrp/ugrp-sim/runs')

def read(p):return json.loads(Path(p).read_text())
def write(p,x):Path(p).write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(count):
    assert platform.node().startswith('ugrp-sim-gcp2')
    out=ROOT/'reloc17-delivery';out.mkdir(exist_ok=True)
    batches=[('decomposition',read(ROOT/'reloc17-decomposition/summary.json'))]+[(f'round{n}',read(ROOT/f'reloc17-round{n}/summary.json')) for n in range(1,count+1)]
    lite=[];inventory=[];rejections=[]
    for stage,data in batches:
        queue=read(data['source_queue'])
        for r in data['runs']:
            assert r['status'] not in ('running','UNRETRIEVED')
            assert r['integrity']['verified'],r['name']
            raw=Path(r['raw']);name=r['name']
            keep=('name','kind','condition','seed','source_sha','raw','status','termination','first30','drive_errors','registered_errors','registered_frames','false_registration_events','fresh_pose_error','command_only_replay','command_only_same_drive_frames','local_execution_drift','floor_line_residuals','camera_pan_evaluation','registration_frame_funnel','known_mode_measurement_funnel','place_verified','sim_s','all_pose_error','input_audit','failure')
            row={k:r[k] for k in keep if k in r};row['stage']=stage
            if 'heading' in r:row['heading']={k:v for k,v in r['heading'].items() if k not in ('admissions','increments')}
            lite.append(row)
            manifests=[p for p in (raw/'result.json',raw/'artifacts.sha256.json',raw/'artifacts.sha256.json.zst',raw/'manifest.json',raw/'manifest.json.zst') if p.is_file()]
            inventory.append(dict(run=name,raw=str(raw),source_sha=r['source_sha'],verified=r['integrity'],stored_files={str(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in manifests}))
            if 'registration_frame_funnel' in r:
                rejections.append(dict(stage=stage,run=name,raw=str(raw),**r['registration_frame_funnel']))
            else:
                rejections.append(dict(stage=stage,run=name,raw=str(raw),cumulative=dict(exposures=r.get('heading',{}).get('exposures',0),accepted=r.get('heading',{}).get('accepted',0)),
                    rejections=[dict(category=k,N=v,blocked_object='own_rgb_static_background',minimum_gap_m=None,gap_status='not_applicable_localization_gate') for k,v in r.get('heading',{}).get('statuses',{}).items() if k!='accepted']))
            meta=raw.parent/'RUN_META.json';m=read(meta);m.update(pr=536,branch='claude/reloc17',source_sha=r['source_sha']);write(meta,m)
        # Large analysis JSON/JSONL: compress losslessly, verify decompressed hash,
        # preserve the stored raw manifests untouched. Only new analysis files.
        for p in [Path(data['source_queue']).parent/'summary.json']:
            if p.stat().st_size>65536:
                z=p.with_suffix(p.suffix+'.zst');subprocess.run(['zstd','-q','-f',str(p),'-o',str(z)],check=True)
                assert hashlib.sha256(subprocess.check_output(['zstd','-dqc',str(z)])).hexdigest()==sha(p)
                # Keep the summary readable until the final analysis/lifecycle is
                # complete; archival removal is a separate final step.
    final=[r for r in lite if r['stage']==f'round{count}'];carry=[r for r in final if r['kind']=='carry'];ss=[r for r in final if r['kind']=='selfmap']
    baseline=read(ROOT/'reloc16-round2/summary.json')['runs']
    pairs=[]
    for r in ss:
        b=next(x for x in baseline if x['kind']=='selfmap' and x['seed']==r['seed'])
        pairs.append(dict(seed=r['seed'],old_R2=b['drive_errors'],candidate=r['drive_errors'],old_raw=b['raw'],new_raw=r['raw']))
    verdict='READY' if all(r.get('place_verified') for r in carry) and len(carry)==2 and all(r['drive_errors']['N']>0 for r in ss) and len(ss)==2 and all(p['candidate'][a][q]<=p['old_R2'][a][q] for p in pairs for a in ('xy_m','yaw_deg') for q in ('p50','p95')) else 'NOT_READY'
    summary=dict(schema='ugrp.reloc17.summary.v1',verdict=verdict,created=datetime.datetime.now(datetime.timezone.utc).isoformat(),pr=536,parent_pr=532,base_sha='5f63909becb63edc633ab3ad243a4b694fb38846',candidate_source_sha=final[0]['source_sha'],
        scene='walls_floor_contrast_v5_indigo110_s80 + v1 floor + no_mip_v1',host='gcp2 / ugrp-sim-b-1014 / n4-highcpu-64 / C MuJoCo CPU',
        investigation_complete_before_controller_edit=True,controller_fix='reloc17_servo_wait_v1 (default off), ordinary pending-servo hold replaced by existing zero-wheel primitive; terminal hold unchanged',
        constants_changed=False,raw_truth_scope='evaluator-only error calculation; no GT, joints or contacts supplied to controller',
        runs=lite,rounds=count,pairs=pairs,final_place=dict(N=len(carry),verified=sum(bool(r.get('place_verified')) for r in carry)),
        speed={f'round{n}':read(ROOT/f'reloc17-round{n}/speed-gate.json') for n in range(1,count+1)},
        scope=dict(mac_physics=0,mac_render=0,mac_gui=0,model_calls=0,training=0,weld=False,full_raw_backup=False,full_raw_download=False,physical_robot_or_ACT_student_success_not_claimed=True),
        playback='playback-review.md; full mission success video unavailable',records=dict(inventory='inventory.json',rejection_table='rejection-table-candidate.json',references='references.md',constants='constants.md',decomposition='decomposition.md'))
    write(out/'summary.json',summary);write(out/'inventory.json',inventory);write(out/'rejection-table-candidate.json',dict(unit='ordered frames/events, acquisition and tracking kept separate',runs=rejections,reproduce=f'{__file__} --rounds {count}'))
    for n in range(1,count+1):
        src=ROOT/f'reloc17-round{n}';(out/f'round{n}.md').write_bytes((src/'table.md').read_bytes());write(out/f'round{n}-speed.json',read(src/'speed-gate.json'))
    for name in ('host.json','servo-audit.json','likelihood-audit.json','playback-manifest.json'):
        (out/name).write_bytes((ROOT/'reloc17-investigation'/name).read_bytes())
    print(json.dumps(dict(verdict=verdict,place=summary['final_place'],runs=len(lite),pairs=pairs),ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--rounds',type=int,required=True);a=p.parse_args();main(a.rounds)
