"""Publish sealed s2v56 offline evidence to native TensorBoard, no physics."""
import argparse
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode

import numpy as np

from replay_sensor_consistency import read,sha


def series_rows(evaluation):
    out=[]
    for q in evaluation['measurement_time_series']:
        row=dict(t=q['t'],kind='measurement',prior_ess=q['prior_ess'],posterior_ess=q['posterior_ess'],
            posterior_ess_fraction=q['posterior_ess']/q['particle_count'],
            near_mass=q['posterior']['mass_10cm_5deg'],cloud_nees=q['posterior']['nees_xy'],
            score_log10_ratio=float(np.log10(q['active_score_ratio'])))
        for f in q['components']:
            key='wall_log_span' if f['index']==0 else f"feature{f['index']}_log_span"
            row[key]=f['log_factor_range'][1]-f['log_factor_range'][0]
        out.append(row)
    out.extend(dict(t=q['t'],kind='decision',decision_nees=q['nees_xy'],xy_error_m=q['xy_error_m']) for q in evaluation['decisions'])
    return sorted(out,key=lambda q:q['t'])


def plot(root):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(3,2,figsize=(12,10),layout='constrained')
    for option,color in [('baseline','tab:blue'),('on','tab:orange')]:
        r=read(root/f's1060-{option}/evaluation.json');m=r['measurement_time_series'];d=r['decisions'];p=r['particle_time_series']
        t=[q['t'] for q in m]
        ax[0,0].semilogy(t,[q['posterior_ess']/q['particle_count'] for q in m],'.-',label=option,color=color)
        ax[0,1].plot(t,[np.log10(q['active_score_ratio']) for q in m],'.-',label=option,color=color)
        ax[1,0].plot([q['t'] for q in p],[q['mass_10cm_5deg'] for q in p],label=option,color=color)
        valid=[q for q in d if q['nees_xy'] is not None]
        ax[1,1].semilogy([q['t'] for q in valid],[q['nees_xy'] for q in valid],label=option,color=color)
        ax[2,0].plot([q['t'] for q in d],[q['xy_error_m'] for q in d],label=option,color=color)
    base=read(root/'s1060-baseline/evaluation.json')
    for i in range(5):
        points=[(q['t'],q['components'][i]['score_ratio']) for q in base['measurement_time_series'] if len(q['components'])>i]
        ax[2,1].plot([q[0] for q in points],np.log10([q[1] for q in points]),'.-',label='wall' if i==0 else f'floor {i}')
    labels=['Posterior ESS / N','log10(max/min likelihood)','Mass within 10 cm and 5 deg (carry)',
            'Reported XY NEES at fixed decisions','Reported XY error (m)','Baseline per-factor log10(max/min)']
    for panel,label in zip(ax.flat,labels):
        panel.set_title(label);panel.set_xlabel('SIM time (s)');panel.legend(fontsize=8);panel.grid(alpha=.2)
    ax[1,1].axhline(5.991464547107979,color='black',ls='--',lw=1)
    fig.suptitle('s1060 own-RGB / fixed-command replay; truth used for evaluation only')
    fig.savefig(root/'s1060-feature-consistency.png',dpi=140);fig.savefig(root/'s1060-feature-consistency.pdf')
    plt.close(fig)


def publish(root):
    from scripts.tensorboard_tools.offline_audit import convert
    result=read(root/'result.json');assert len(result['comparisons'])==9
    name='1008-s2-sensor-consistency-v56';snapshot=Path('/Users/changmin/projects/ugrp/outputs/tensorboard')/name
    if snapshot.exists():raise FileExistsError(snapshot)
    snapshot.mkdir();sources=[];manifests=[]
    for comparison in result['comparisons']:
        seed=comparison['seed']
        for option,key in [('baseline','baseline'),('on','on')]:
            run=f's{seed}-'+('off' if option=='baseline' else 'on')
            evaluation=read(root/f's{seed}-{option}/evaluation.json');summary=evaluation['summary']
            source=root/'views'/run;source.mkdir(parents=True,exist_ok=False)
            trace=source/'series.jsonl';series=series_rows(evaluation)
            trace.write_text(''.join(json.dumps(q)+'\n' for q in series))
            scalars={f'offline/{k}':summary[k] for k in ('carry_rmse_m','carry_end_xy_m','nees_exceed_fraction',
                'unflagged_gt_25cm','near_truth_support_fraction','near_truth_median_mass','actual_resamples','measurement_count','physics_runs')}
            spec=dict(schema='ugrp.offline_audit_view.v1',derived_view_only=True,
                offline_source=dict(path=str(root/'result.json'),sha256=sha(root/'result.json')),
                offline_scalar_scope='Fixed recorded commands/own RGB offline replay; not physical performance. NEES uses reported full covariance.',
                offline_scalars=scalars,offline_series=dict(source=dict(path=str(trace),sha256=sha(trace)),format='jsonl',
                    sim_time_field='t',tags=[dict(tag='trace/'+k,path=[k]) for k in
                        ('prior_ess','posterior_ess','posterior_ess_fraction','near_mass','cloud_nees','score_log10_ratio',
                         'wall_log_span','feature1_log_span','feature2_log_span','feature3_log_span','feature4_log_span','decision_nees','xy_error_m')]),
                family='S2',condition='off' if option=='baseline' else 'on',policy='sensor_consistency',seed=seed,
                source_sha=summary['source_sha'],model_calls=0,hparam_metrics=list(scalars),
                texts={'result/gates':comparison['checks'],'result/scope':'No simulation, no new physical success, no threshold retuning.'})
            (source/'result.json').write_text(json.dumps(spec,indent=2)+'\n')
            manifests.append(convert(source,snapshot/run));sources.append(str(source))
    (snapshot/'collection.json').write_text(json.dumps(dict(schema='ugrp.tensorboard.collection.v1',sources=sources,complete=True),indent=2)+'\n')
    pins=['offline/carry_rmse_m','offline/nees_exceed_fraction','offline/unflagged_gt_25cm','offline/near_truth_support_fraction','result/model_calls']
    url='http://127.0.0.1:6006/?'+urlencode(dict(pinnedCards=json.dumps([dict(plugin='scalars',tag=t) for t in pins]),smoothing=0,runFilter='^'+name+'/'))+'#timeseries'
    delivery=dict(snapshot=str(snapshot),url=url,manifests=[dict(path=str(snapshot/q['source'].split('/')[-1]/'manifest.json')) for q in manifests],
        plot=dict(path=str(root/'s1060-feature-consistency.png'),sha256=sha(root/'s1060-feature-consistency.png')),
        source_hash=sha(root/'result.json'),dashboard_ui='pending',scalar_verification='pending')
    (root/'delivery.json').write_text(json.dumps(delivery,indent=2)+'\n')
    shared=Path('/Users/changmin/projects/ugrp/outputs/tensorboard-view.json')
    view=read(shared)  # reread immediately before modifying our key only
    view['s2_sensor_consistency_v56_20261008']=dict(snapshot=str(snapshot),url=url,pinned_metrics=pins,
        default_runs=[name+'/s1060-off',name+'/s1060-on'],hparams_visible_columns=['seed'],scope='offline9 off/on; no physics')
    shared.write_text(json.dumps(view,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(delivery),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--plot-only',action='store_true')
    a=p.parse_args();plot(a.output)
    if not a.plot_only:publish(a.output)
