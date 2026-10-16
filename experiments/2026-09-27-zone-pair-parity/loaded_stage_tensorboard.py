"""Publish only a local temporary native TensorBoard audit; no viewer/server."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

import loaded_stage_analysis as evidence

HERE=evidence.HERE
SOURCE=HERE/'loaded_stage_metrics.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
    receipt=HERE/'loaded_stage_tensorboard.json'
    if receipt.exists():
        old=json.loads(receipt.read_text())
        if old['source_sha256']==sha(SOURCE) and Path(old['snapshot']).exists():
            print('Existing identical-source snapshot preserved:',old['snapshot'])
            return
        raise RuntimeError('Existing receipt preserved; use a new version for changed source')
    m=json.loads(SOURCE.read_text());source_hash=sha(SOURCE)
    points=[b['last_report_at_or_before_abort'] for r in m['dev'] if r['id'] in ('dev05','dev06','dev08') for b in r['robots'].values()]
    groups={
      'dev-pf':{'offline/traces':len(points),'offline/xy_error_min_m':min(p['eval_xy_error_m'] for p in points),
        'offline/xy_error_max_m':max(p['eval_xy_error_m'] for p in points),
        'offline/error_sigma_ratio_max':max(p['error_over_sigma_xy'] for p in points)},
      'm2-shadow':{'offline/success_selected_runs':49,'offline/conditional_gate_rejects':98,
        'offline/loaded_to_gate_p50_s':m['m2']['seconds_since_loaded_command_at_shadow_reject']['p50'],
        'offline/door_carry_p50_s':m['m2']['phase_duration_by_stage_s']['door']['carry']['p50']},
      'pf-clock':{'offline/loaded_yaw_var_ratio':m['noise']['loaded_to_unloaded_yaw_variance_ratio'],
        'offline/seconds_from_2p5_to_3deg':m['noise']['stationary_budget'][-1]['stationary_seconds_to_3deg'],
        **{f"offline/loaded_sigma_at_{int(x['external_predict_interval_s']*1000)}ms_deg":x['synthetic_pf_yaw_std_deg']
           for x in m['noise']['zero_motion'] if x['mode']=='motion_loaded'}}}
    tmp=Path(tempfile.mkdtemp(prefix='zone-pair-loaded-design-tb-'));args=[]
    for name,values in groups.items():
        view=tmp/'views'/name;view.mkdir(parents=True)
        write(view/'result.json',{'schema':'ugrp.offline_audit_view.v1','derived_view_only':True,
            'offline_source':{'path':str(SOURCE),'sha256':source_hash},'offline_scalars':values,
            'offline_scalar_scope':'Design evidence: stored logs / inherited conditional replay / synthetic PF; not physical success',
            'family':'loaded-stage-design','condition':name,'case':'offline','split':'diagnostic',
            'source_sha':'a1a304d1594bbe9b060b48c95b99e65b793a2094','hparam_metrics':list(values),
            'texts':{'provenance/limits':'No physics or model call; no new video; shared viewer publication blocked by write scope.'}})
        args+=['--source',str(view)]
    snapshot=tmp/'snapshot'
    subprocess.run([sys.executable,str(evidence.ROOT/'scripts/export_offline_audit.py'),*args,'--output',str(snapshot)],check=True)
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    verified=[]
    for event in sorted(snapshot.rglob('events.out.tfevents.*')):
        acc=EventAccumulator(str(event.parent));acc.Reload()
        values={tag:acc.Scalars(tag)[-1].value for tag in acc.Tags()['scalars']}
        matches=[name for name,expected in groups.items() if all(math.isclose(values.get(k,-999),v,rel_tol=1e-6,abs_tol=1e-7) for k,v in expected.items())]
        assert len(matches)==1,(event,values)
        assert acc.PluginTagToContent('hparams')
        verified.append({'run':matches[0],'event':str(event),'sha256':sha(event),'scalars':values,'hparams_loaded':True})
    assert len(verified)==3 and sha(SOURCE)==source_hash
    write(receipt,{'snapshot':str(snapshot),'source':str(SOURCE),'source_sha256':source_hash,
        'verified_events':verified,'shared_root_published':False,'gui_verified':False,
        'dashboard_url':'http://127.0.0.1:6006','new_video':None,'server_started':False,
        'blockers':['primary outputs/tensorboard outside writable roots','Chrome CUA cgWindowNotFound; browser inventory empty'],
        'suggested_hparams_columns':['condition','split','case'],'source_unchanged':True})
    print(snapshot)
if __name__=='__main__':main()
