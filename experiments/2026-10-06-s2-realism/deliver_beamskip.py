"""Native TensorBoard for s2v57; reuse already-published baseline events."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

from harness.zone_final_pair_binding import bind
from replay_beamskip import read,sha
from deliver_sensor_consistency import plot as previous_plot,series_rows

NAME='1008-s2-beamskip-v57'
OLD='1008-s2-sensor-consistency-v56'


def publish(root):
    from scripts.tensorboard_tools.offline_audit import convert
    result=read(root/'result.json');base=Path(result['baseline_root'])
    def plot_read(path):
        return read(base/path.relative_to(root) if '-baseline' in str(path) else path)
    bind(previous_plot,read=plot_read)(root)
    shared_root=Path('/Users/changmin/projects/ugrp/outputs/tensorboard')
    snapshot=shared_root/NAME;snapshot.mkdir(exist_ok=False)
    sources=[];summary_tags=('carry_rmse_m','carry_end_xy_m','nees_exceed_fraction','unflagged_gt_25cm',
        'near_truth_support_fraction','near_truth_median_mass','actual_resamples','measurement_count','physics_runs')
    for comparison in result['comparisons']:
        seed=comparison['seed'];run=f's{seed}-on'
        evaluation=read(root/f's{seed}-on/evaluation.json');s=evaluation['summary']
        source=root/'views'/run;source.mkdir(parents=True,exist_ok=False)
        series=series_rows(evaluation);trace=source/'series.jsonl'
        trace.write_text(''.join(json.dumps(q)+'\n' for q in series))
        scalars={f'offline/{k}':s[k] for k in summary_tags};scalars['gate/all_passed']=int(comparison['passed'])
        spec=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
            offline_source=dict(path=str(root/'result.json'),sha256=sha(root/'result.json')),
            offline_scalar_scope='Fixed-command own RGB replay, offline gates only, not physical success.',
            offline_scalars=scalars,offline_series=dict(source=dict(path=str(trace),sha256=sha(trace)),format='jsonl',
                sim_time_field='t',tags=[dict(tag='trace/'+k,path=[k]) for k in
                    ('prior_ess','posterior_ess','posterior_ess_fraction','near_mass','cloud_nees','score_log10_ratio',
                     'wall_log_span','feature1_log_span','feature2_log_span','feature3_log_span','feature4_log_span','decision_nees','xy_error_m')]),
            family='S2',condition='on',policy='nav2_prob_v1',seed=seed,source_sha=s['source_sha'],model_calls=0,
            hparam_metrics=list(scalars),texts={'result/gates':comparison['checks'],
                'result/scope':'No physics. Baseline events reused from '+OLD})
        (source/'result.json').write_text(json.dumps(spec,indent=2)+'\n')
        convert(source,snapshot/run);sources.append(str(source))
    (snapshot/'collection.json').write_text(json.dumps(dict(sources=sources,complete=True))+'\n')
    pins=['offline/carry_rmse_m','offline/nees_exceed_fraction','offline/unflagged_gt_25cm','offline/near_truth_support_fraction','result/model_calls']
    run_filter='^(?:'+NAME+'/s.*-on|'+OLD+'/s.*-off)'
    url='http://127.0.0.1:6006/?'+urlencode(dict(pinnedCards=json.dumps([dict(plugin='scalars',tag=t) for t in pins]),smoothing=0,runFilter=run_filter))+'#timeseries'
    delivery=dict(snapshot=str(snapshot),baseline_snapshot=str(shared_root/OLD),baseline_reconverted=False,url=url,
        source_hash=sha(root/'result.json'),plot=dict(path=str(root/'s1060-feature-consistency.png'),sha256=sha(root/'s1060-feature-consistency.png')),
        dashboard_ui='pending',scalar_verification='pending')
    (root/'delivery.json').write_text(json.dumps(delivery,indent=2)+'\n')
    path=shared_root.parent/'tensorboard-view.json';view=read(path)
    view['s2_beamskip_v57_20261008']=dict(snapshot=str(snapshot),url=url,pinned_metrics=pins,
        default_runs=[OLD+'/s1060-off',NAME+'/s1060-on'],hparams_visible_columns=['seed'],scope='offline9 off/on; no physics')
    path.write_text(json.dumps(view,ensure_ascii=False,indent=2)+'\n')


def verify(root):
    result=read(root/'result.json');delivery=read(root/'delivery.json');verified=[]
    for q in result['comparisons']:
        for option,name,key in [('off',OLD,'baseline'),('on',NAME,'on')]:
            run=f'{name}/s{q["seed"]}-{option}'
            location=Path(delivery['snapshot']).parent/run
            ea=EventAccumulator(str(location),size_guidance={'scalars':0});ea.Reload()
            count=0
            for tag in ea.Tags()['scalars']:
                events=ea.Scalars(tag)
                url='http://127.0.0.1:6006/data/plugin/scalars/scalars?'+urlencode(dict(run=run,tag=tag))
                with urlopen(url,timeout=15) as reply:live=json.load(reply)
                assert len(live)==len(events),(run,tag,len(live),len(events))
                assert np.allclose([r[2] for r in live],[e.value for e in events],rtol=1e-6,atol=1e-8)
                if tag.startswith('offline/'):
                    metric=tag.split('/')[1]
                    assert np.isclose(events[-1].value,q[key][metric],rtol=1e-6,atol=1e-8)
                count+=len(events)
            verified.append(dict(run=run,tags=len(ea.Tags()['scalars']),values=count,
                manifest_hash=sha(location/'manifest.json')))
    delivery['scalar_verification']=dict(verified=verified,total_values=sum(v['values'] for v in verified),
        method='source summary -> event -> live native TensorBoard API; all scalar points')
    (root/'delivery.json').write_text(json.dumps(delivery,indent=2)+'\n')
    print(json.dumps(dict(runs=len(verified),values=delivery['scalar_verification']['total_values'])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true')
    a=p.parse_args();verify(a.output) if a.verify else publish(a.output)
