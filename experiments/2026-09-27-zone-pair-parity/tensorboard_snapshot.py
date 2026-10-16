"""Create and read back native TensorBoard offline-audit events in /tmp."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import replay as r


def main():
    root=Path(tempfile.mkdtemp(prefix='zone-pair-parity-tb-'))
    base=root/'views';sources=[];expected={}
    for name in ('dev-main','dev-grasp-v4','dev-grasp-v5','m2-shadow-main','m2-input-contracts'):
        path=r.OUT/(name+'.json');doc=r.read(path);runs=doc['runs']
        metrics={'offline/replayed_runs':len(runs)}
        if name.startswith('dev'):
            robots=[v for run in runs for v in run['robots'].values()]
            metrics.update({'offline/admission_refusals':sum(v['replayed_admission']['state']!='available' for v in robots),
                'offline/postapproach_gate_rejects':sum(v['first_postapproach_gate_reject'] is not None for v in robots)})
            if 'preclose_replay' in runs[4]['robots']['r1']:
                metrics['offline/dev07_preclose_pass']=int(runs[4]['robots']['r1']['preclose_replay']['accepted'])
        elif name=='m2-shadow-main':
            robots=[v for run in runs for v in run['robots'].values()]
            metrics.update({'offline/conditional_gate_rejects':sum(v['first_shadow_postapproach_gate_reject'] is not None for v in robots),
                            'offline/verified_jpegs':sum(v['verified_jpegs'] for v in robots)})
        else:
            cs=[v for run in runs for rob in run['robots'].values() for v in rob['close_attempts']]
            metrics.update({'offline/close_input_tests':len(cs),'offline/fresh_matching_camera_pass':sum(v['necessary_preclose_input_pass'] for v in cs)})
        target=base/name;target.mkdir(parents=True)
        r.write(target/'result.json',{'schema':'ugrp.offline_audit_view.v1','derived_view_only':True,
            'offline_source':{'path':str(path),'sha256':r.sha(path)},'offline_scalars':metrics,
            'offline_scalar_scope':'saved-input diagnostic; conditional shadow is not a physical failure rate',
            'family':'zone-pair-parity','condition':name,'case':'offline','split':'diagnostic',
            'source_sha':doc['judge_ref'],'hparam_metrics':list(metrics),
            'texts':{'provenance/limits':'No new physics, no new RGB, no physical success claim. Shared viewer publication pending.'}})
        sources+=['--source',str(target)];expected[name]=metrics
    snapshot=root/'snapshot'
    subprocess.run([sys.executable,str(r.ROOT/'scripts/export_offline_audit.py'),*sources,'--output',str(snapshot)],check=True)
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    verified=[]
    for event in sorted(snapshot.rglob('events.out.tfevents.*')):
        acc=EventAccumulator(str(event.parent));acc.Reload()
        values={tag:acc.Scalars(tag)[-1].value for tag in acc.Tags()['scalars']}
        matching=[n for n,ms in expected.items() if all(values.get(k)==v for k,v in ms.items())]
        assert matching,(event,values)
        verified.append({'event':str(event),'sha256':r.sha(event),'scalars':values,
                         'hparams_loaded':bool(acc.PluginTagToContent('hparams'))})
    assert len(verified)==5
    r.write(r.OUT/'tensorboard.json',{'snapshot':str(snapshot),'verified_events':verified,
        'source_unchanged':True,'shared_root_published':False,'dashboard_url':'http://127.0.0.1:6006',
        'gui_verified':False,'reason':'primary outputs write denied; Chrome/IAB unavailable; existing viewer unchanged',
        'new_video':'none: offline reanalysis, existing raw videos remain untouched'})


if __name__=='__main__':main()
