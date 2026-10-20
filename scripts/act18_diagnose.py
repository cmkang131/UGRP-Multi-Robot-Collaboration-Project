"""Default-off expert-state diagnosis on gcp2; no physics, recording or training.

Count unique h0 teacher commands, never padded/overlapping future targets.
The stop projection is the existing frozen student contract, not a new gate.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2, frozen_source, sha256
from act17_data import Dataset, library, read
from act17_open_loop import action_errors, quantiles
from act17_policy import Actor, observation_batch
from act17_compact_records import original_sha256

B = Path('/home/ugrp/ugrp-sim')


def histogram(values):
    # Decimal formatting is a display key only; signs/counts use original data.
    counts = Counter(format(float(v), '.9g') for v in np.asarray(values).flat)
    return dict(N=sum(counts.values()), values=dict(sorted(counts.items(), key=lambda x: float(x[0]))))


def confusion(truth, raw, projected):
    truth, raw, projected = map(np.asarray, (truth, raw, projected))
    moving = truth != 0
    return dict(N=int(truth.size), teacher_moving=int(moving.sum()),
        teacher_stopped=int((~moving).sum()),
        projected_stop_while_teacher_moves=int((moving & (projected == 0)).sum()),
        raw_opposite_sign_while_teacher_moves=int((moving & (raw * truth < 0)).sum()),
        projected_opposite_sign_while_teacher_moves=int((moving & (projected * truth < 0)).sum()),
        projected_moves_while_teacher_stops=int(((~moving) & (projected != 0)).sum()))


def write(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    for name in ('dataset', 'models-root', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--candidates', nargs='+', choices=['F', 'S'], default=['F', 'S'])
    a = p.parse_args()
    if not a.enabled:
        p.error('diagnosis is default OFF')
    host = require_gcp2(training=True)
    source = frozen_source(Path(__file__).resolve().parents[1])
    library()
    import torch
    from harness import grasp_act_contract as c
    torch.set_num_threads(2)
    a.out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = dict(schema='ugrp.act18.diagnosis.v1', source_sha=source, host=host,
        complete=False, status='running', physics_steps=0, training_updates=0,
        dataset_manifest_sha256=original_sha256(a.dataset/'manifest.json'),
        reproduce=sys.argv, distributions={}, open_loop={})
    lease = B/'leases/act18.json'
    current = read(lease)
    if current.get('task') != 'act18':
        raise ValueError('owned lease required')
    current.update(pid=os.getpid(), active='act18_diagnose', expected_end='finite h0 census and F/S TRAIN audit')
    write(lease, current)
    try:
        train = Dataset(a.dataset, 'train', image_mode='current_full_v1')
        val = Dataset(a.dataset, 'validation', image_mode='current_full_v1')
        for split, data in [('train', train), ('validation', val)]:
            groups = defaultdict(list)
            for idx, (shard, row) in enumerate(data.index):
                action = data.shards[shard]['action'][row, 0]
                groups['all'].append(action)
                groups[data.metadata[idx]['stage']].append(action)
            report['distributions'][split] = {}
            for stage, actions in groups.items():
                values = np.asarray(actions)
                report['distributions'][split][stage] = dict(rows=len(values),
                    wheels=histogram(values[:, :4]), pulse_ms=histogram(values[:, 4:8]*150),
                    wheel_sign=dict(negative=int((values[:, :4]<0).sum()),zero=int((values[:, :4]==0).sum()),positive=int((values[:, :4]>0).sum())),
                    servo_PWM=[quantiles(1500+1000*values[:, k]) for k in range(8, 13)])
        # TRAIN-only h0 normalization audit; float accumulation precision is reported.
        actions = np.concatenate([s['action'][:, 0] for s in train.shards])
        report['action_statistics_recomputed'] = dict(
            mean=actions.mean(0, dtype=np.float64).tolist(),
            population_std=actions.std(0, dtype=np.float64).tolist(),
            saved=train.stats, note='saved floor0.01; torch sample-vs-population std implementation checked separately')
        # Fixed first TRAIN quartet, one of each kind, plus ALL TRAIN alignment.
        seeds = train.manifest['protocol']['train_seeds'][:4]
        ids = [i for i, m in enumerate(train.metadata) if m['seed'] in seeds or m['stage']=='alignment']
        report['TRAIN_selection'] = dict(seeds=seeds, rows=len(ids), rule='first four preregistered TRAIN seeds union all TRAIN alignment', no_outcome_selection=True)
        write(a.out/'histogram.json', report)
        for candidate in a.candidates:
            root = a.models_root/candidate/'actor'
            actor = Actor.load(root, device='cuda')
            summaries = defaultdict(lambda: defaultdict(list))
            wheel = defaultdict(lambda: defaultdict(list))
            parity = []
            for ep in train.manifest['episodes']:
                if ep['split']!='train' or ep['seed'] not in seeds:
                    continue
                observations=read(Path(ep['source_capture'])/'student-r1.jsonl', lines=True)
                i=next(i for i,m in enumerate(train.metadata) if m['seed']==ep['seed'])
                obs=next(o for o in observations if o['sample_id']==train.metadata[i]['sample_id'])
                jpgs=[(Path(ep['source_capture'])/r['path']).read_bytes() for r in obs['rgb']]
                deployment=observation_batch(obs,jpgs,train.stats,'current_full_v1')
                item=train[i]
                parity.append(dict(seed=ep['seed'],sample_id=obs['sample_id'],equal={k:np.array_equal(v,item[k]) for k,v in deployment.items()},image_shape=list(item['observation.images.own_history'].shape)))
            if len(parity)!=4 or not all(all(r['equal'].values()) for r in parity):
                raise ValueError('actual TRAIN/deployment transform mismatch')
            with gzip.open(a.out/(candidate+'-TRAIN-frames.jsonl.gz'),'xt') as stream:
                for offset in range(0,len(ids),8):
                    selected=ids[offset:offset+8]
                    batch={k:v.to('cuda') for k,v in torch.utils.data.default_collate([train[i] for i in selected]).items() if k.startswith('observation.')}
                    with torch.inference_mode():
                        predictions=actor.policy.predict_action_chunk(batch).cpu().numpy()
                    predictions=actor.base.decode_predictions(predictions)
                    for i,pred in zip(selected,predictions):
                        j,k=train.index[i];truth=train.shards[j]['action'][k,0];meta=train.metadata[i]
                        decoded=c.decode_action(pred[0])
                        projected=np.asarray(c.encode_action(dict(t=meta['t'],**{k:decoded[k] for k in ('wheels','duration_s','pwm')}),done=decoded['done']))
                        for stage in ['all',meta['stage']]:
                            summaries[stage]['rows'].append(1)
                            for mode,v in [('raw',pred[0]),('projected',projected)]:
                                for unit,errors in action_errors(v,truth).items():
                                    summaries[stage][mode+':'+unit].extend(errors.tolist())
                            wheel[stage]['truth'].extend(truth[:4].tolist())
                            wheel[stage]['raw'].extend(pred[0,:4].tolist())
                            wheel[stage]['projected'].extend(projected[:4].tolist())
                        stream.write(json.dumps(dict(**meta,teacher_h0_encoded=truth.tolist(),prediction_h0_encoded=pred[0].tolist(),projected_h0_encoded=projected.tolist()))+'\n')
            report['open_loop'][candidate]=dict(checkpoint_sha256=sha256(root/'model.safetensors'),parity=parity,
                stages={s:dict(rows=len(v['rows']),errors={k:quantiles(x) for k,x in v.items() if ':' in k},wheel_confusion=confusion(**wheel[s])) for s,v in summaries.items()})
            del actor
            torch.cuda.empty_cache()
            write(a.out/'summary.json',report)
        report.update(complete=True,status='complete')
        write(a.out/'rejection_table.json',dict(source_sha=source,raw=str(a.out),reproduce=sys.argv,
            funnel=[dict(gate='TRAIN_h0_rows',passed=len(train),rejected=0),dict(gate='fixed_TRAIN_audit_selection',passed=len(ids),rejected=len(train)-len(ids),reason_category='preregistered_diagnostic_subset')],
            failures=[dict(candidate=name,reason_category='expert_state_command_mismatch',blocked_object='not_attributed_by_command_only_audit',minimum_gap_m=None,minimum_gap_status='not_measured',**row['stages']['alignment']['wheel_confusion']) for name,row in report['open_loop'].items()],
            note='component confusion counts overlap; no causal attribution from marginal histogram'))
    except BaseException as error:
        report.update(status='HOST_ERROR',error=repr(error))
        raise
    finally:
        report['wall_s']=time.monotonic()-started
        write(a.out/'summary.json',report)


if __name__=='__main__':
    main()
