"""New offline diagnostic snapshot in writable tmp; shared root remains intact."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SOURCE=HERE/'dev09_10_diagnosis.json'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')

def main():
    receipt=HERE/'beam_frame_tensorboard.json'
    if receipt.exists():
        old=json.loads(receipt.read_text())
        if old['source_sha256']==sha(SOURCE) and Path(old['snapshot']).exists():
            print('Verified existing source receipt:',old['snapshot']);return
        raise ValueError('Preserve existing snapshot; choose a new receipt version')
    d=json.loads(SOURCE.read_text());groups={}
    for run in d['dev']:
        bots=list(run['robots'].values());cc=[c for b in bots for c in b['decision_checks']]
        groups[run['id']]={'offline/relook_frames':sum(b['frame_count'] for b in bots),
            'offline/tag_detected_frames':sum(b['frames_with_detected_tags'] for b in bots),
            'offline/decision_frames':len(cc),'offline/exact_fix_pass':sum(c['exact_frozen_predicate'] for c in cc),
            'offline/clock_clause_pass':sum(c['clock_clause_only_variant'] for c in cc),
            'offline/abort_sim_s':run['robots']['r1']['failure']['sim_s'],
            'offline/new_physics_steps':0,'offline/new_model_calls':0}
    groups['m2-evidence']={'offline/success_selected_runs':49,'offline/traces':98,
        'offline/vo_traces':d['history']['vo_trace_count'],
        'offline/first_align_shape_fit':d['history']['initial_anchor_fit_count'],
        'offline/full_design_unknown':49,'offline/preclose_input_pass':0}
    tmp=Path(tempfile.mkdtemp(prefix='beam-frame-diagnosis-tb-'));args=[]
    for name,values in groups.items():
        view=tmp/'views'/name;view.mkdir(parents=True)
        write(view/'result.json',{'schema':'ugrp.offline_audit_view.v1','derived_view_only':True,
            'offline_source':{'path':str(SOURCE),'sha256':sha(SOURCE)},'offline_scalars':values,
            'offline_scalar_scope':'Saved-input diagnosis only; clock-only predicate is conditional, not transport success',
            'family':'beam-frame-diagnosis','condition':name,'case':'offline','split':'diagnostic',
            'source_sha':d['run_source_sha'],'hparam_metrics':list(values),
            'texts':{'provenance/limits':'No new physics/video; 49 success-selected old M2 runs are not candidate validation.'}})
        args+=['--source',str(view)]
    snapshot=tmp/'snapshot'
    subprocess.run([sys.executable,str(ROOT/'scripts/export_offline_audit.py'),*args,'--output',str(snapshot)],check=True)
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    verified=[]
    for event in sorted(snapshot.rglob('events.out.tfevents.*')):
        acc=EventAccumulator(str(event.parent));acc.Reload()
        vals={t:acc.Scalars(t)[-1].value for t in acc.Tags()['scalars']}
        matches=[n for n,v in groups.items() if all(math.isclose(vals.get(k,-999),x,rel_tol=1e-6,abs_tol=1e-7) for k,x in v.items())]
        assert len(matches)==1 and acc.PluginTagToContent('hparams')
        verified.append({'run':matches[0],'sha256':sha(event),'event':str(event),'values':vals,'hparams_loaded':True})
    assert len(verified)==len(groups)
    write(receipt,{'snapshot':str(snapshot),'source_sha256':sha(SOURCE),'verified':verified,
        'shared_root_published':False,'gui_verified':False,'new_video':None,'server_started':False,
        'dashboard_url':'http://127.0.0.1:6006','view_config_read':True,
        'blockers':['shared primary outputs/tensorboard outside writable roots',
                    'Chrome CUA cgWindowNotFound; browser inventory empty; PID inspection denied'],
        'proposed_hparams_visible_columns':['condition','split','case','source_sha']})
    print(snapshot)

if __name__=='__main__':main()
