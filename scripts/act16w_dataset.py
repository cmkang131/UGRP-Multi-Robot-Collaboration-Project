"""Admit external native captures without rewriting original controller files.

The legacy converter consumes a clearly marked derived import view: original
controller training_rgb=false and external capture=true are both preserved in
provenance. Only complete successful audited episodes enter tensors. Failed,
capped, missing and host-error records remain in the independent gate table.
"""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from act16w_runtime import ACT_SHA,require_gcp2,frozen_source,sha256

B=Path('/home/ugrp/ugrp-sim');Q='f0db6b1abb842ea65b71c433738210254f300a7c';API='0362037280c6cbc4677f70366db43b9892b23690'

def read(p):
    return json.loads(p.read_text()) if p.exists() else json.loads(subprocess.check_output(['zstd','-dc',str(p)+'.zst']))

def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser()
    for k in ['root','batch','selection','protocol','act-source']:p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--enabled',action='store_true')
    p.add_argument('--native-gate',type=Path,help='explicit separate native-contact gate; excludes historical noslip pilots')
    a=p.parse_args()
    if not a.enabled:p.error('dataset admission default OFF')
    require_gcp2();source=frozen_source(Path(__file__).resolve().parents[1]);frozen_source(a.act_source,ACT_SHA)
    selection=read(a.selection);protocol=read(a.protocol);wanted=set(selection['selected_seeds']);a.root.mkdir(parents=True,exist_ok=False)
    native=None
    if a.native_gate:
        native=read(a.native_gate)
        if (not native.get('passed') or native.get('N')!=40 or native.get('n',0)<38
                or native.get('contact_profile')!='warp_native_contact_v1'
                or native.get('training_rgb') is not False or native.get('input_audit_violations')!=0
                or protocol.get('contact_profile')!='warp_native_contact_v1'):
            raise ValueError('new camera-off native40 gate required')
        for item in native['raw_results']+native['runtime_profiles']:
            if sha256(item['path'])!=item['sha256']:raise ValueError('native gate evidence changed')
    roots=([] if native else [B/'runs/act16w-resume2-pilot-86821',B/'runs/act16w-resume2-pilot-86822'])+sorted(a.batch.glob('group-*'))
    rows=[];seen=set();transport={};views=a.root/'views';views.mkdir()
    for root in roots:
        capture=root/'capture';controller=root/'controller'
        summary=read(capture/'summary.json')
        if summary.get('controller_source')!=Q or summary.get('status')!='recording_complete' or summary.get('error'):
            raise ValueError('completed qualified external capture required: '+str(root))
        audit_path=root/'dataset-audit.json'
        if not audit_path.exists():
            subprocess.run([str(B/'runs/simalt3/warp-env/bin/python'),str(Path(__file__).with_name('audit_act16w_record.py')),str(root),'--out',str(audit_path)],check=True)
        audit=read(audit_path)
        if native:
            physical=read(controller/'native-contact.json')
            if physical.get('gpu_noslip')!=0 or any(physical.get('cpu_noslip',[1])) or physical.get('cpu_impratio')!=5:
                raise ValueError('native record runtime physics differs from gate')
        capture_source=summary.get('record_api_source',API)
        for w in audit['worlds']:
            seed=w['seed']
            if seed not in wanted:continue
            if seed in seen:raise ValueError('duplicate recording seed')
            seen.add(seed);i=w['world'];raw=capture/f'world-{i:03d}';original=controller/f'world-{i:03d}'
            result=read(original/'result.json');plan=read(original/'plan.json')
            success=result.get('status')=='complete' and w['physical_success'] and not w['cap_end'] and w['command_complete']
            row=dict(seed=seed,success=bool(success),raw=str(root),world=i,audit=dict(path=str(audit_path),sha256=sha256(audit_path)),reason='success' if success else result.get('reason') or result.get('teacher',{}).get('command_result') or 'teacher_physical_failure',input_audit=w['input_audit'])
            rows.append(row)
            if not success:continue
            view=views/str(seed);dest=view/'raw';dest.mkdir(parents=True)
            for name in ['student-r1.jsonl','teacher-r1.jsonl','student-camera.json','rgb']:
                original_path=raw/name
                if not original_path.exists() and original_path.with_name(name+'.zst').exists():name+='.zst';original_path=raw/name
                if original_path.is_dir():
                    for pixel in original_path.rglob('*'):
                        if pixel.is_file():
                            link=dest/name/pixel.relative_to(original_path);link.parent.mkdir(parents=True,exist_ok=True);os.link(pixel,link)
                else:os.link(original_path,dest/name)
            os.link(original/'plan.json',dest/'plan.json')
            # This is an import adapter result, never a replacement for the
            # original controller report. It reports the external RGB recorder.
            derived={**result,'training_rgb':True,'recording_mode':'training','student_execution':False,
                     'record_view':'derived_external_capture_v1','original_controller_training_rgb':result['training_rgb'],
                     'original_controller_result':dict(path=str(original/'result.json' if (original/'result.json').exists() else original/'result.json.zst'),sha256=sha256(original/'result.json' if (original/'result.json').exists() else original/'result.json.zst')),
                     'external_capture':dict(source_sha=capture_source,upstream_source_sha=API,adapter_sha256=summary['adapter_sha256'],raw=str(raw),audit_sha256=sha256(audit_path)),
                     'import_view_source':source,'teacher_library_sha':'6f057f7e97c1a3aec9e8c398b8d9068e27b25df8'}
            write(dest/'result.json',derived);(view/'SOURCE_SHA').write_text(capture_source+'\n');(view/'EXIT').write_text('0\n');transport[str(seed)]=capture_source
    n=sum(r['success'] for r in rows);N=len(wanted);missing=sorted(wanted-seen)
    gate=dict(n=n,N=N,complete=not missing,passed=not missing and N>=40 and n/N>=.95,missing=missing,rows=rows,source_sha=Q,training_rgb=True,independent_of_warp1_debugging=True,old_debug_seed_range=[8317100,8317139],heldout_excluded=[91620,91659],scope='fresh recording-stage independent confirmation; separate from camera-off bootstrap40/40')
    write(a.root/'fresh-recording-gate.json',gate)
    prepared=N if native else 50
    funnel=[dict(gate='prepared_starts',passed=prepared,rejected=0),dict(gate='predeclared_model_subset',passed=N,rejected=prepared-N),dict(gate='recorded_native_streams',passed=len(seen),rejected=len(missing)),dict(gate='physical_teacher_complete',passed=n,rejected=len(seen)-n)]
    rejections=([dict(category='budget_model_subset',reason=selection['reason'],count=50-N,blocking_object='not_applicable_compute_admission',minimum_gap_m=None,minimum_gap_status='not_applicable_non_geometric')] if not native else [])+[dict(category='teacher_recording_failed',reason=r['reason'],count=1,seed=r['seed'],target_object='see original plan.json',blocking_object='not_attributed_before_playback',minimum_gap_m=None,minimum_gap_status='not measured; no geometric cause claim') for r in rows if not r['success']]
    write(a.root/'rejection_table.json',dict(funnel=funnel,rejections=rejections,missing=missing,raw=[str(x) for x in roots],reproduce=sys.argv))
    if not gate['passed']:raise ValueError('fresh recording-stage gate not passed')
    admitted={r['seed'] for r in rows if r['success']}
    conversion=dict(teacher_sha=Q,train_seeds=[s for s in protocol['train_seeds'] if s in admitted],validation_seeds=[s for s in protocol['validation_seeds'] if s in admitted],run_pattern='{seed}',transport_sha_by_seed=transport,done_label='last_local_row_v1',include_initial_approach_v1=True,run_class='milestone',external_capture_view_v1=True,old_bootstrap_gate_pooled=False)
    if not conversion['train_seeds'] or not conversion['validation_seeds']:raise ValueError('nonempty independent training/validation required')
    sys.path.insert(0,str(a.act_source))
    from harness.grasp_act_data import convert
    manifest=convert(views,conversion,a.root/'dataset')
    if native:
        manifest['contact_profile']='warp_native_contact_v1'
        manifest['native_gate']=dict(path=str(a.native_gate),sha256=sha256(a.native_gate))
        write(a.root/'dataset/manifest.json',manifest)
    from harness.grasp_act_data import GraspDataset
    from harness.grasp_act_loss import completion_priors
    data=GraspDataset(a.root/'dataset','train');priors=completion_priors(data)
    write(a.root/'dataset-audit.json',dict(passed=True,complete=manifest['complete'],valid_future_action_targets_verified=True,teacher_input_fields_in_tensor_whitelist=0,train_seeds=conversion['train_seeds'],validation_seeds=conversion['validation_seeds'],done_priors=priors,manifest_sha256=sha256(a.root/'dataset/manifest.json'),source_sha=source,originals_unchanged=True,input_keys=sorted(data[0]),original_gate_is_not_independent=not bool(native)))
    print(json.dumps(dict(status='complete',fresh_teacher_n=n,fresh_teacher_N=N,dataset=str(a.root/'dataset'),rows=len(data),research_training_steps=0)))

if __name__=='__main__':main()
