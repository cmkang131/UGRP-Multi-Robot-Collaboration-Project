"""Create one immutable native TensorBoard snapshot from completed summaries."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[3]
EXP = ROOT/'experiments/2026-10-11-egomap-reconfirmation'
PRIMARY = Path('/Users/changmin/projects/ugrp')
REPORTS = PRIMARY/'outputs/egomap71-reports'
VIEWS = PRIMARY/'outputs/egomap71-tensorboard-views-v1'
SNAPSHOT = PRIMARY/'outputs/tensorboard/1011-egomap71-v1'
PYTHON = PRIMARY/'.venv-sim-worker-mac/bin/python'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def view(name, source, scalars, scope, **extra):
    folder=VIEWS/name
    folder.mkdir(parents=True, exist_ok=False)
    data={'schema':'ugrp.offline_audit_view.v1','derived_view_only':True,
          'offline_source':{'path':str(source),'sha256':digest(source)},
          'offline_scalar_scope':scope,'offline_scalars':scalars,
          'family':'egomap71','condition':name,'model_calls':0,
          'hparam_metrics':list(scalars),'scope':scope,'texts':{'evaluation/limits':scope},**extra}
    (folder/'result.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    return folder

def main():
    sources=[]
    az=REPORTS/'azure-admission-summary.json'
    summary=json.loads(az.read_text())
    for condition,r in summary['conditions'].items():
        scalars={f'offline/{k}':r[k] for k in ['registered','attempted','measured','host_errors']}
        for metric in ['false_return','false_B']:
            scalars[f'offline/{metric}_observed']=r[metric]['count']
            scalars[f'offline/{metric}_measured_denominator']=r[metric]['measured_run_denominator']
        sources.append(view('azure-'+condition,az,scalars,summary['interpretation'],
                            outcome='HOST_ERROR_INPUT_ADMISSION',source_sha=summary['source_sha']))
    base=summary['baseline_reference']
    sources.append(view('prior-baseline',az,
        {'offline/false_return':base['false_return']['count'],
         'offline/false_B':base['false_B']['count'],
         'offline/registered':base['false_return']['denominator']},
        'Previously recorded egomap70 calib_traversed six-seed DEV reference; no new execution or matched on/off improvement.',
        outcome='HISTORICAL_DEV_REFERENCE'))
    cov=REPORTS/'covariance-summary.json'
    result=json.loads(cov.read_text())
    for condition,r in result['results']['check']['overall'].items():
        sources.append(view('cov-'+condition,cov,
            {'offline/NEES_p999_exceedances':r['exceedances']['p999']['count'],
             'offline/NEES_p95_exceedances':r['exceedances']['p95']['count'],
             'offline/NEES_rows':r['samples'],'offline/NEES_mean':r['mean']},
            'Previously seen DEV seed63002, four correlated conditions and temporal rows; seed63001 calibration; not independent confirmation or robot success.',
            outcome='RETROSPECTIVE_DEV',seed=63002))
    rgb=REPORTS/'rgb-summary.json'
    if rgb.is_file():
        result=json.loads(rgb.read_text())
        for kind,r in result['aggregate'].items():
            scalars={f'offline/{k}':r[k] for k in ['declarations','truth_scored','truth_false','fully_replayed','false_geometry_accepted','false_geometry_rejected','true_geometry_rejected']}
            sources.append(view('rgb-'+kind,rgb,scalars,'; '.join(result['limitations']),outcome='HISTORICAL_GEOMETRY_ONLY'))
    command=[str(PYTHON),str(ROOT/'scripts/export_offline_audit.py'),'--output',str(SNAPSHOT)]
    for source in sources:command += ['--source',str(source)]
    subprocess.run(command,check=True)
    # Verify every emitted scalar directly from the new event files.
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    readback=[]
    for source in sources:
        declared=json.loads((source/'result.json').read_text())
        event=EventAccumulator(str(SNAPSHOT/source.name));event.Reload()
        expected={**declared['offline_scalars'],'result/model_calls':0}
        observed={tag:event.Scalars(tag)[-1].value for tag in expected}
        for tag,value in expected.items():assert abs(observed[tag]-value)<=max(1e-5,abs(value)*1e-6)
        assert 'evaluation/reported_success' not in event.Tags()['scalars']
        readback.append({'run':source.name,'scalars':observed,
                         'manifest_sha256':digest(SNAPSHOT/source.name/'manifest.json')})
    pins=['offline/NEES_p999_exceedances','offline/NEES_rows','offline/host_errors','offline/measured','offline/false_return','offline/false_B','result/model_calls']
    url='http://127.0.0.1:6006/?'+urlencode({'pinnedCards':json.dumps([{'plugin':'scalars','tag':tag} for tag in pins],separators=(',',':')),'smoothing':'0','runFilter':'^1011-egomap71-v1/'})+'#timeseries'
    record={'active_logdir':str(PRIMARY/'outputs/tensorboard'),'snapshot':str(SNAPSHOT),'run_filter':'^1011-egomap71-v1/','url':url,'pinned_tags':pins,
            'hparams_visible_columns':['outcome','result/wall_s','result/commands','result/model_calls'],
            'events_verified':True,'readback':readback,'new_videos_registered':0,
            'media_limit':'No new simulation ran; historical RGB stays remote and Mac uses fetch-lite. No new video is claimed.',
            'unavailable_metrics':['robot success','runtime of executed trial','model response time']}
    (EXP/'tensorboard.json').write_text(json.dumps(record,indent=2,ensure_ascii=False)+'\n')
    # Preserve all unrelated shared settings, including their order/format.
    config=PRIMARY/'outputs/tensorboard-view.json'
    original=config.read_text();current=json.loads(original)
    key='egomap71_reconfirmation_20261011'
    if key in current:raise RuntimeError('Existing shared task key; refuse overwrite')
    end=original.rfind('}')
    entry=json.dumps({key:record},indent=2,ensure_ascii=False)[1:-1].strip('\n')
    config.write_text(original[:end].rstrip()+',\n'+entry+'\n'+original[end:])
    print(url)

if __name__=='__main__':main()
