"""GCP2 package selected final weights and compact provenance; no upload/key."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil

from harness.grasp_act_data import sha256, write_json
from scripts.beamact1_runtime import require_gcp2
from scripts.grasp_act_training_guard import ROOT, source_sha
from scripts.model_artifacts import pack

MODEL_ID='beamact2-pair-shared-step10000-20261016'
TAG='models-20261016-beamact2-v1'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,required=True)
    p.add_argument('--training-summary',type=Path,required=True)
    p.add_argument('--offline-summary',type=Path,required=True)
    p.add_argument('--evaluation-summary',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();require_gcp2(training=False);packaging_source=source_sha()
    training=json.loads(a.training_summary.read_text())
    offline=json.loads(a.offline_summary.read_text())
    evaluation=json.loads(a.evaluation_summary.read_text())
    meta=json.loads((a.model/'adapter.json').read_text())
    assert training['complete'] and training['steps_completed']==10000 and training['readback_verified']
    assert meta['provenance']['source_sha']==training['source_sha'] and meta['provenance']['step']==10000
    assert meta['history_causal_split_v1']=='wheel_pulse_train_mean'
    assert offline['ACT_measured'] and offline['model_sha256']==sha256(a.model/'model.safetensors')
    assert evaluation['complete'] and evaluation['N']==20 and evaluation['model_sha256']==offline['model_sha256']
    a.output.mkdir(parents=True,exist_ok=False)
    staging=a.output/'payload';staging.mkdir()
    shutil.copytree(a.model,staging/'actor')
    for name,value,original in [('training-summary.json',training,a.training_summary),
                                ('offline-summary.json',offline,a.offline_summary),
                                ('student-summary.json',evaluation,a.evaluation_summary)]:
        value=deepcopy(value)
        if 'timing' in value:
            for key in ('step_s','batch_load_s'):value['timing'].pop(key,None)
        value.pop('episodes',None)
        if 'runs' in value:
            value['runs']=[{k:r[k] for k in ('seed','status','complete','physical_success','result_sha256','category') if k in r} for r in value['runs']]
        value['original_summary']=dict(path=str(original),sha256=sha256(original))
        write_json(staging/name,value)
    shutil.copyfile(ROOT/'requirements-reference-act.txt',staging/'requirements-reference-act.txt')
    provenance=dict(model_id=MODEL_ID,training_source_sha=training['source_sha'],
        evaluation_source_sha=evaluation['source_sha'],analysis_source_sha=evaluation.get('analysis_source_sha'),
        packaging_source_sha=packaging_source,step=10000,selection='fixed final10000; no validation/heldout checkpoint selection',
        dataset_manifest_sha256=training['dataset_manifest_sha256'],
        model_sha256=offline['model_sha256'],student_n=evaluation['n'],student_N=20,
        teacher_actions=0,truth_corrections=0,held_object_hidden_v1=True,weld='off',
        gpu_load_label='shared-load',default_controller=False,
        scope='beam pair local student finite reserved20; not LLM E2E, transport/release or physical robot success',
        originals='raw datasets and videos remain on GCP2; archive is selected model/inference metadata only')
    write_json(staging/'provenance.json',provenance)
    (staging/'README.md').write_text(
        '# beamact2 comparison model\n\nFixed step10000; shared L4 training. '
        f'Student reserved20: {evaluation["n"]}/20; {evaluation["verdict"]}.\n\n'
        'Use the frozen source and pinned optional ACT environment. CPU load check:\n\n'
        '```sh\npython -m scripts.beamact2_worker --model /PATH/actor < /dev/null\n```\n\n'
        'Own RGB/issued-history only; the beamact1.v3 adapter applies the TRAIN-mean wheel/pulse mask. '
        'This model is not a default controller. See provenance and experiment records for verification limits.\n')
    files=[dict(path=str(f.relative_to(staging)),bytes=f.stat().st_size,sha256=sha256(f))
        for f in sorted(staging.rglob('*')) if f.is_file()]
    row=dict(id=MODEL_ID,status='available',description='Fixed final shared-weight beam pair ACT comparison model; default off',
        source_sha=training['source_sha'],training_source_sha=training['source_sha'],
        evaluation_source_sha=evaluation['source_sha'],
        release=dict(tag=TAG,asset=MODEL_ID+'.zip',
            url=f'https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/download/{TAG}/{MODEL_ID}.zip'),
        files=files,limitations=[f'reserved20 student {evaluation["n"]}/20; {evaluation["verdict"]}',
            'shared-load GPU time; no speed acceptance claim','not default controller or E2E/transport/release/real robot proof'])
    archive=pack(row,staging,a.output/(MODEL_ID+'.zip'))
    row['archive']={k:archive[k] for k in ('sha256','bytes')}
    write_json(a.output/'model-entry.json',row)
    write_json(a.output/'packaging.json',dict(packaging_complete=True,upload_complete=False,redownload_verified=False,
        model_entry_sha256=sha256(a.output/'model-entry.json'),archive=archive))
    (a.output/'SHA256SUMS').write_text(archive['sha256']+'  '+MODEL_ID+'.zip\n')
    print(json.dumps(dict(model_id=MODEL_ID,archive=archive,files=len(files))))


if __name__=='__main__':main()
