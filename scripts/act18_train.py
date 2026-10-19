"""Default-off, fixed 100k reference ACT comparison on existing v7 data."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2, frozen_source, sha256, LEROBOT_ACT_SHA256, ACT_SHA
from act17_data import library, read
from act17_compact_records import original_sha256
from act17_policy import observation_batch
from act18_policy import (CANDIDATES, TUNE_CANDIDATE, PILOT_CANDIDATES, PILOT_KINDS, ReferenceDataset,
                          WeightedReferenceDataset, done_positive_indices, extend_targets,
                          make_policy, save_actor, Actor)
from act18_diagnose import write

B = Path('/home/ugrp/ugrp-sim')
ROOT = Path(__file__).resolve().parents[1]


def validate_probe_options(candidate, init_checkpoint, steps, post_close_weight, pre_close_weight,
                           done_positive_batch_fraction=None, base_smooth_window=None, val_select=False,
                           done_current_step_only=False, done_window_ticks=None, done_clock_jitter_s=None):
    """Default-off pilot options; never silently mixes with the R8/R100 reference pair."""
    supplied = [value is not None for value in
                (init_checkpoint, steps, post_close_weight, pre_close_weight, done_positive_batch_fraction,
                 base_smooth_window, done_window_ticks, done_clock_jitter_s)] + ([True] if val_select else [])
    pilot_only = [value is not None for value in
                  (init_checkpoint, steps, post_close_weight, pre_close_weight, done_positive_batch_fraction)]
    if candidate in PILOT_CANDIDATES:
        if steps is None:
            raise ValueError(candidate+' requires --steps')
        if candidate in (TUNE_CANDIDATE, 'act18-doneb1', 'act18-r3dw') and init_checkpoint is None:
            raise ValueError(candidate+' requires --init-checkpoint')
        if candidate == 'act18-r3dw' and done_window_ticks is None:
            raise ValueError(candidate+' requires --done-window-ticks')
    elif candidate == 'act18-co':
        if any(pilot_only):
            raise ValueError('co-training does not combine with pilot options')
    elif any(supplied):
        raise ValueError('pilot options require a registered pilot candidate '+str(PILOT_CANDIDATES))
    if steps is not None and not 1 <= steps <= 20000:
        raise ValueError('probe --steps must be within [1, 20000]')
    for value, label in ((post_close_weight, '--post-close-weight'), (pre_close_weight, '--pre-close-weight')):
        if value is not None and not 1 <= value <= 20:
            raise ValueError(label+' must be within [1, 20]')
    if done_positive_batch_fraction is not None:
        if candidate not in PILOT_CANDIDATES:
            raise ValueError('--done-positive-batch-fraction requires a pilot candidate')
        if not 0 <= done_positive_batch_fraction <= 1:
            raise ValueError('--done-positive-batch-fraction must be within [0, 1]')
    if base_smooth_window is not None:
        if candidate not in PILOT_CANDIDATES and candidate != 'act18-co':
            raise ValueError('--base-smooth-window requires a pilot candidate')
        if type(base_smooth_window) is not int or not 1 <= base_smooth_window <= 21:
            raise ValueError('--base-smooth-window must be an integer within [1, 21]')
    if val_select and candidate not in PILOT_CANDIDATES and candidate != 'act18-co':
        raise ValueError('--val-select requires a pilot candidate')
    if done_current_step_only and candidate not in PILOT_CANDIDATES:
        raise ValueError('--done-current-step-only requires a pilot candidate')
    if done_window_ticks is not None:
        if candidate != 'act18-r3dw':
            raise ValueError('--done-window-ticks requires --candidate act18-r3dw')
        if type(done_window_ticks) is not int or not 1 <= done_window_ticks <= 20:
            raise ValueError('--done-window-ticks must be an integer within [1, 20]')
    if done_clock_jitter_s is not None:
        if candidate != 'act18-r3dw':
            raise ValueError('--done-clock-jitter-s requires --candidate act18-r3dw')
        if done_window_ticks is None:
            raise ValueError('--done-clock-jitter-s requires --done-window-ticks')
        if (not isinstance(done_clock_jitter_s, (int, float))
                or isinstance(done_clock_jitter_s, bool)
                or not 0 < done_clock_jitter_s <= 2.):
            raise ValueError('--done-clock-jitter-s must be within (0, 2] seconds')
    return steps


def init_checkpoint_receipt(path, protocol, protocol_path, dataset, chunk):
    """Exact completed 100k checkpoint receipt before a short TUNE probe."""
    path = Path(path)
    hashes = read(path/'SHA256.json')
    if set(hashes) != {'model.safetensors', 'config.json', 'adapter.json'}:
        raise ValueError('init checkpoint inventory must be exactly three registered files')
    if any(sha256(path/name) != digest for name, digest in hashes.items()):
        raise ValueError('init checkpoint file hash mismatch')
    adapter = read(path/'adapter.json')
    provenance = adapter.get('provenance', {})
    step = provenance.get('step')
    probe = provenance.get('probe') or {}
    reference = step == protocol['steps']
    pilot = (probe.get('kind') in PILOT_KINDS and step == probe.get('steps_override')
             and 1 <= step <= 20000 and probe.get('packaging_eligible') is False)
    continuation = (provenance.get('candidate') == 'act18-co' and isinstance(provenance.get('resume'), dict)
                    and isinstance(step, int) and 20000 <= step <= 100000 and not probe)
    if (adapter.get('schema') != 'ugrp.act18.adapter.v1' or adapter.get('chunk') != chunk
            or not provenance.get('training_complete') or not (reference or pilot or continuation)
            or provenance.get('protocol_sha256') != sha256(protocol_path)
            or provenance.get('dataset_manifest_sha256') != original_sha256(dataset/'manifest.json')):
        raise ValueError('init checkpoint must be a completed matched reference or registered pilot ACT18 model')
    return dict(path=str(path), step=provenance['step'], candidate=provenance.get('candidate'),
                chunk=adapter['chunk'], model_sha256=hashes['model.safetensors'],
                adapter_sha256=hashes['adapter.json'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enabled', action='store_true')
    p.add_argument('--candidate', choices=tuple(CANDIDATES), required=True)
    # AGENTS 2026-10-17 user decision: new ACT training runs bf16 by default after
    # the gcp5 paired probe (2000 steps/arm, 1.10x, 0 NaN). fp32 stays selectable
    # only for replay/matched-fp32 comparison; bf16 and fp32 results never pool.
    p.add_argument('--precision', choices=('bf16_autocast_v1','fp32'), default='bf16_autocast_v1')
    # TUNE probe options (default OFF): initialize from a completed checkpoint,
    # run a short bf16 schedule, and optionally upweight align..close rows.
    p.add_argument('--init-checkpoint', type=Path)
    p.add_argument('--steps', type=int)
    # Frozen segment table: post-close (where the student halts) and the
    # preceding hover/descent/close tail. Both default OFF.
    p.add_argument('--post-close-weight', type=float)
    p.add_argument('--pre-close-weight', type=float)
    # B1 pre-registration (2026-10-18): done-only supervision probe. Fraction of
    # batches that force one positive completion row plus uniform rows; the
    # existing balanced BCE weights (0.5/prior vs 0.5/(1-prior) = 361:1) stay
    # the harness implementation, so action losses are unchanged.
    p.add_argument('--done-positive-batch-fraction', type=float)
    # R3 done-window (default OFF): expand the grasp completion labels over the
    # K-1 immediately preceding same-episode/skill rows at 0.1 s spacing.
    p.add_argument('--done-window-ticks', type=int)
    # R3-B (default OFF): add U(-s,+s) seconds to verify_lift/hold clock inputs.
    p.add_argument('--done-clock-jitter-s', type=float)
    # B2 standard alignment (default OFF): act-plus-plus smooths the mobile base
    # action with a per-episode moving average at data-load time.
    p.add_argument('--base-smooth-window', type=int)
    # Checkpoint selection on validation episodes EXCLUDING the protocol VAL8
    # seeds, so the later VAL8 gate is not used for selection.
    p.add_argument('--val-select', action='store_true')
    p.add_argument('--val-rows', type=int, default=256)
    p.add_argument('--validate-every', type=int, default=1000)
    # B3 (Lead-approved): keep completion targets only at the chunk row matching
    # the observation itself, to test the executed h=0 vs far-horizon mismatch.
    p.add_argument('--done-current-step-only', action='store_true')
    # Pilot-only optimizer lr override (default 1e-5, the standard ACT value).
    p.add_argument('--lr', type=float)
    # Phase C co-training (Lead-approved): v7 TRAIN200 + act16w 40-world dataset,
    # with a 2-dim dataset-origin token appended to observation.state.
    p.add_argument('--cotrain-native', type=Path)
    p.add_argument('--cotrain-weight', type=float, default=.5)
    p.add_argument('--checkpoint-every', type=int)
    p.add_argument('--co-smooth-window', type=int, default=5)
    # Phase C continuation after a host interruption (label required; never
    # resumed silently): warm-start the ACT weights from a completed co run.
    p.add_argument('--transition-weight', type=float)
    p.add_argument('--resume-from', type=Path)
    p.add_argument('--resume-extra-steps', type=int)
    for name in ('dataset','protocol','out','queue'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    if not a.enabled:
        p.error('reference ACT candidate is default OFF')
    host = require_gcp2(training=True)
    source = frozen_source(ROOT)
    library()
    protocol, queue = read(a.protocol), read(a.queue)
    if (protocol.get('schema')!='ugrp.act18.protocol.v1' or queue.get('source_sha')!=source
            or protocol['steps']!=100000 or protocol['batch_size']!=8
            or a.candidate not in queue['candidates']):
        raise ValueError('fixed registered matched queue required')
    # Strict: a queue without the precision receipt must not silently run bf16.
    if queue.get('training_precision')!=a.precision:
        raise ValueError('queue training_precision receipt and --precision must match')
    cotrain = a.cotrain_native is not None
    resume = a.resume_from is not None
    if resume:
        if a.candidate != 'act18-co' or a.resume_extra_steps is None or a.steps is not None:
            raise ValueError('resume requires --candidate act18-co, --resume-extra-steps and no --steps')
        resume_meta = read(a.resume_from/'adapter.json')
        resume_step = int(resume_meta['provenance']['step'])
        total_steps = resume_step+a.resume_extra_steps
        if total_steps > protocol['steps'] or resume_step <= 0:
            raise ValueError('resume cumulative steps must stay within the 100k reference protocol')
    else:
        total_steps = validate_probe_options(a.candidate, a.init_checkpoint, a.steps,
                                             a.post_close_weight, a.pre_close_weight,
                                             a.done_positive_batch_fraction,
                                             a.base_smooth_window, a.val_select,
                                             a.done_current_step_only,
                                             a.done_window_ticks, a.done_clock_jitter_s) or protocol['steps']
    if cotrain and (a.post_close_weight is not None or a.pre_close_weight is not None
                    or a.done_positive_batch_fraction is not None or a.done_current_step_only
                    or a.done_window_ticks is not None or a.done_clock_jitter_s is not None):
        raise ValueError('co-training does not combine with tuning options')
    if cotrain and a.candidate not in ('act18-co', 'act18-loop'):
        raise ValueError('--cotrain-native requires --candidate act18-co or act18-loop')
    if a.transition_weight is not None:
        if a.candidate != 'act18-loop' or a.init_checkpoint is None:
            raise ValueError('--transition-weight requires the act18-loop pilot with an init checkpoint')
        if not .01 <= a.transition_weight <= 10.:
            raise ValueError('transition weight bounds [0.01,10]')
    if a.lr is not None:
        if a.candidate not in PILOT_CANDIDATES:
            raise ValueError('--lr override requires a pilot candidate')
        if not 1e-7 <= a.lr <= 1e-4:
            raise ValueError('--lr override must be within [1e-7, 1e-4]')
    done_positive_fraction = a.done_positive_batch_fraction
    weighted = a.post_close_weight is not None or a.pre_close_weight is not None
    if weighted and (a.done_window_ticks is not None or a.done_clock_jitter_s is not None):
        raise ValueError('R3 done-window options do not combine with post-close weighting')
    sampling = (('cotrain_transition_v1' if a.transition_weight is not None else 'cotrain_v1')
                if cotrain else ('weighted_post_close_v1' if weighted else 'uniform_episode_v1'))
    if cotrain:
        from act18_cotrain_data import CoTrainingDataset
        data = CoTrainingDataset(a.dataset, a.cotrain_native, chunk=CANDIDATES[a.candidate],
                                 base_smooth_window=a.co_smooth_window, native_weight=a.cotrain_weight,
                                 transition_weight=a.transition_weight)
        state_dim = data.state_dim
    elif weighted:
        data = WeightedReferenceDataset(a.dataset, 'train', chunk=CANDIDATES[a.candidate],
                                        post_close_weight=a.post_close_weight,
                                        pre_close_weight=a.pre_close_weight)
    else:
        data = ReferenceDataset(a.dataset, 'train', chunk=CANDIDATES[a.candidate],
                                base_smooth_window=a.base_smooth_window,
                                done_horizon='current_only' if a.done_current_step_only else 'all',
                                done_window_ticks=int(a.done_window_ticks or 0),
                                done_clock_jitter_s=a.done_clock_jitter_s)
    positive_indices = done_positive_indices(data) if done_positive_fraction is not None else None
    if (set(data.manifest['eligible_train_seeds'])!=set(protocol['train_seeds'])
            or original_sha256(a.dataset/'manifest.json')!=queue['dataset_manifest_sha256']):
        raise ValueError('same complete v7 TRAIN dataset required')
    if cotrain:
        if queue.get('cotrain_native_manifest_sha256') != data.native_manifest_sha256:
            raise ValueError('registered act16w co-training manifest required')
        if queue.get('cotrain_weight') != a.cotrain_weight:
            raise ValueError('registered co-training weight required')

    import torch
    from harness.grasp_act_loss import policy_loss
    from lerobot.policies.act import modeling_act
    if sha256(Path(modeling_act.__file__))!=LEROBOT_ACT_SHA256:
        raise ValueError('pinned valid-token normalized upstream required')
    if not torch.cuda.is_available() or 'L4' not in torch.cuda.get_device_name(0):
        raise ValueError('L4 required')
    torch.set_num_threads(2)
    torch.manual_seed(protocol['seed'])
    torch.cuda.manual_seed_all(protocol['seed'])
    torch.backends.cudnn.benchmark=False
    generator=torch.Generator().manual_seed(protocol['seed'])
    policy=make_policy(data.chunk,device='cuda',pretrained=True,
                       state_dim=(data.state_dim if cotrain else None))
    init_receipt=None
    if resume:
        from safetensors.torch import load_file
        policy.load_state_dict(load_file(str(a.resume_from/'model.safetensors')),strict=True)
        init_receipt=dict(kind='cotrain_continuation_v1',from_checkpoint=str(a.resume_from),
            from_step=resume_step,new_steps=a.resume_extra_steps,cumulative_steps=total_steps)
    if a.init_checkpoint is not None:
        init_receipt=init_checkpoint_receipt(a.init_checkpoint,protocol,a.protocol,a.dataset,data.chunk)
        from safetensors.torch import load_file
        state=load_file(str(Path(a.init_checkpoint)/'model.safetensors'))
        policy.load_state_dict(state,strict=True)
        del state
    train_lr=a.lr if a.lr is not None else 1e-5
    optimizer=torch.optim.AdamW(policy.get_optim_params(),lr=train_lr,weight_decay=1e-4)
    priors=data.completion_priors(sampling)
    val_batches=None
    if a.val_select:
        # Selection data: validation episodes EXCLUDING the protocol VAL8 seeds,
        # so the later VAL8 gate never selects the checkpoint.
        if cotrain:
            from act18_cotrain_data import CoTrainingValidation
            val_data=CoTrainingValidation(a.dataset,data.stats,chunk=CANDIDATES[a.candidate])
        else:
            val_data=ReferenceDataset(a.dataset,'validation',chunk=CANDIDATES[a.candidate],
                                      base_smooth_window=a.base_smooth_window)
        val8=set(protocol['validation8_seeds'])
        selectable=[index for index,row in enumerate(val_data.metadata) if row['seed'] not in val8]
        if len(selectable)<a.val_rows:
            raise ValueError('insufficient non-VAL8 validation rows for selection')
        val_generator=torch.Generator().manual_seed(protocol['seed']+1)
        picked=[selectable[int(i)] for i in torch.randperm(len(selectable),generator=val_generator)[:a.val_rows].tolist()]
        val_batches=[]
        for start in range(0,len(picked),64):
            batch={k:v.to('cuda') for k,v in torch.utils.data.default_collate([val_data[i] for i in picked[start:start+64]]).items()}
            val_batches.append(batch)
    first=next(ep for ep in data.manifest['episodes'] if ep['split']=='train')
    obs=next(o for o in read(Path(first['source_capture'])/'student-r1.jsonl',lines=True)
             if o['sample_id']==data.metadata[0]['sample_id'])
    jpgs=[(Path(first['source_capture'])/r['path']).read_bytes() for r in obs['rgb']]
    own=observation_batch(obs,jpgs,data.stats,'current_full_v1')
    first_batch=data[0]
    state_dim=own['observation.state'].shape[-1]
    if state_dim!=first_batch['observation.state'].shape[-1]:
        # co-training view: deck the registered v7 condition token onto the v7 obs
        import numpy as _np
        token=_np.asarray([1.0,0.0],_np.float32)
        if first_batch['observation.state'].shape[-1]!=state_dim+len(token):
            raise ValueError('unexpected co-training state width')
        own=dict(own);own['observation.state']=_np.concatenate([own['observation.state'],token])
        if not _np.array_equal(first_batch['observation.state'][:state_dim],own['observation.state'][:state_dim]):
            raise ValueError('real training/deployment transforms differ')
        if not _np.array_equal(first_batch['observation.state'][state_dim:],token):
            raise ValueError('condition token mismatch')
    elif any(not __import__('numpy').array_equal(v,first_batch[k]) for k,v in own.items()):
        raise ValueError('real training/deployment transforms differ')
    a.out.mkdir(parents=True,exist_ok=False)
    config=dict(source_sha=source,cohort='act18-v7-reference',candidate=a.candidate,
        host=host,contact_profile='warp_native_contact_v1',chunk=data.chunk,seed=protocol['seed'],
        steps_requested=total_steps,batch_size=8,lr=train_lr,kl_weight=10.,
        normalization_sha256=data.manifest['normalization']['sha256'],
        dataset_manifest_sha256=queue['dataset_manifest_sha256'],protocol_sha256=sha256(a.protocol),
        lerobot_act_sha256=LEROBOT_ACT_SHA256,act_library_source_sha=ACT_SHA,
        done_loss='balanced_bce_v1',image_mode='current_full_v1',sampling=sampling,
        train_inference_transform_identical=True,gradient_checkpointing=False,
        training_precision=a.precision,
        training_precision_scope=('fp32 weights/optimizer/grad clip; forward+loss bf16 autocast'
                                  if a.precision=='bf16_autocast_v1' else 'fp32 end-to-end'),
        static_map_use='none',wall_cap=None,optimizer_recipe='LeRobot AdamW defaults; no implicit resume',
        state_dim=(data.state_dim if cotrain else None))
    if resume:
        config['resume']=dict(kind='cotrain_continuation_v1',from_checkpoint=str(a.resume_from),
            from_step=resume_step,new_steps=a.resume_extra_steps,cumulative_steps=total_steps,
            optimizer_state='reset (AdamW is stateless at continuation boundary)',
            note='Phase C interrupted by VM guest shutdown; continuation is NOT a pooled result')
    if cotrain:
        config.update(cotraining=dict(v7_root=str(a.dataset),native_root=str(a.cotrain_native),
            native_manifest_sha256=data.native_manifest_sha256,native_weight=a.cotrain_weight,
            state_token_dim=2,state_token_order=['v7','act16w'],base_smooth_window=a.co_smooth_window,
            condition_token=dict(default=[1.0,0.0],order=['v7','act16w'],dim=2),
            note='v7 TRAIN200 + act16w TRAIN32; condition token appended to state; done head trained separately'))
    if a.candidate in PILOT_CANDIDATES:
        if a.candidate == 'act18-r3dw':
            probe_kind='done_window_finetune_v1'
        elif a.done_current_step_only:
            probe_kind='done_horizon_current_only_v1'
        elif a.init_checkpoint is not None:
            probe_kind=('transition_weighted_finetune_v1' if a.transition_weight is not None
                        else 'init_aligned_finetune_v1')
        elif a.base_smooth_window is not None or a.val_select:
            probe_kind='standard_aligned_scratch_v1'
        elif done_positive_fraction is not None:
            probe_kind='done_positive_balanced_finetune_v1'
        else:
            probe_kind='standard_aligned_scratch_v1'
        probe=dict(kind=probe_kind,init_checkpoint=init_receipt,
            steps_override=a.steps if a.steps is not None else None,
            post_close_weight=a.post_close_weight,pre_close_weight=a.pre_close_weight,sampling=sampling,
            post_close_phases=['grasp:'+phase for phase in ('lift','lift_settle','lookback_pose','lookback','lookback_settle','verify_lift','hold')],
            pre_close_phases=['grasp:'+phase for phase in ('hover','descent','close')],
            other_rows_weight=1.0,
            packaging_eligible=False,
            done_positive_batch_fraction=done_positive_fraction,
            base_smooth_window=a.base_smooth_window,
            val_select=a.val_select,
            done_current_step_only=a.done_current_step_only,lr_override=a.lr,
            done_window_ticks=int(a.done_window_ticks or 0),
            done_window_skill='grasp' if a.done_window_ticks else None,
            done_window_receipt=(data.done_window_receipt if a.done_window_ticks else None),
            done_clock_jitter_s=a.done_clock_jitter_s,
            done_clock_jitter_seed=(20261017 if a.done_clock_jitter_s is not None else None),
            done_clock_jitter_rows=int(getattr(data,'clock_jitter_rows',0)),
            completion_prior=priors,
            note='short default-off pilot probe; never packaged or pooled with R8/R100')
        config.update(probe=probe)
    report=dict(**config,status='running',complete=False,steps_completed=0,
        started_utc=datetime.now(timezone.utc).isoformat(),TRAIN_rows=len(data),
        TRAIN_starts=len(data.episode_indices),readback_verified=False,checkpoints=[])
    lease=B/'leases'/('act18-train-'+a.candidate+'.json')
    with lease.open('x') as f:
        json.dump(dict(task='act18',candidate=a.candidate,pid=os.getpid(),start=report['started_utc'],
            expected_end='finite100000updates; no wall deadline',concurrency=0),f)
    stop={'requested':False}
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.update(requested=True))
    if a.checkpoint_every is not None:
        save_steps=tuple(range(a.checkpoint_every,total_steps+1,a.checkpoint_every))
        if total_steps not in save_steps:save_steps=save_steps+(total_steps,)
    else:
        save_steps=(10000,50000,100000) if a.steps is None else (total_steps,)
    best_val={'loss':float('inf'),'step':None,'state':None}

    def validation_loss():
        policy.eval();total=0.;count=0
        with torch.inference_mode():
            for batch in val_batches:
                value,_=policy_loss(policy,batch,mode='balanced_bce_v1',stats=data.stats,priors=priors)
                size=batch['action'].shape[0];total+=float(value)*size;count+=size
        policy.train();return total/count
    started=time.monotonic()
    try:
        with (a.out/'progress.jsonl').open('x') as stream:
            start_step=resume_step if resume else 0
            for local_step in range(1,total_steps-start_step+1):
                step=start_step+local_step
                if stop['requested']:
                    raise InterruptedError('explicit supervisor stop')
                ids=data.sample(generator,8,sampling)
                if positive_indices is not None and torch.rand(1,generator=generator).item() < done_positive_fraction:
                    ids[0]=int(positive_indices[int(torch.randint(len(positive_indices),(1,),generator=generator))])
                    report['done_positive_batches']=report.get('done_positive_batches',0)+1
                report['batches_seen']=report.get('batches_seen',0)+1
                batch={k:v.to('cuda') for k,v in torch.utils.data.default_collate([data[i] for i in ids]).items()}
                policy.train()
                optimizer.zero_grad(set_to_none=True)
                # Probe-verified scope: only forward/loss autocast; weights,
                # optimizer state and grad clip stay fp32.
                with torch.autocast('cuda',dtype=torch.bfloat16,enabled=a.precision=='bf16_autocast_v1'):
                    loss,metrics=policy_loss(policy,batch,mode='balanced_bce_v1',stats=data.stats,priors=priors)
                if not torch.isfinite(loss):
                    raise ValueError('nonfinite loss')
                loss.backward()
                # Same existing LeRobot training gradient clip1.0; no new motion/acceptance threshold.
                norm=torch.nn.utils.clip_grad_norm_(policy.parameters(),1.,error_if_nonfinite=True)
                optimizer.step()
                if val_batches is not None and (step%a.validate_every==0 or step==total_steps):
                    value=validation_loss()
                    history=report.setdefault('val_history',[])
                    history.append(dict(step=step,val_loss=value))
                    if value<best_val['loss']:
                        best_val=dict(loss=value,step=step,
                            state={k:t.detach().cpu().clone() for k,t in policy.state_dict().items()})
                if local_step==1 or step%100==0:
                    row=dict(step=step,loss=float(loss),**metrics,gradient_norm=float(norm),wall_s=time.monotonic()-started)
                    stream.write(json.dumps(row)+'\n');stream.flush()
                    report.update(steps_completed=step,latest=row)
                    write(a.out/'summary.json',report)
                # Standard100k endpoint; intermediate10k/50k allow exact prior-z0
                # TRAIN diagnosis, never selection on FINAL or hidden VAL outcomes.
                # A TUNE probe only saves its final short-step checkpoint.
                if step in save_steps:
                    folder=a.out/('step-'+str(step))
                    completed = step == total_steps
                    save_actor(policy,folder,data.stats,dict(**config,step=step,training_complete=completed))
                    restored=Actor.load(folder,device='cuda')
                    inputs={k:torch.from_numpy(v.copy()).unsqueeze(0).to('cuda') for k,v in own.items()}
                    policy.eval()
                    with torch.inference_mode():
                        if not torch.equal(policy.predict_action_chunk(inputs),restored.policy.predict_action_chunk(inputs)):
                            raise ValueError('saved prediction readback changed')
                    del restored
                    report['checkpoints'].append(dict(step=step,path=str(folder),sha256=sha256(folder/'model.safetensors'),readback_verified=True))
                    write(a.out/'summary.json',report)
        if best_val['state'] is not None and best_val['step']!=total_steps:
            policy.load_state_dict(best_val['state'])
            folder=a.out/('step-'+str(total_steps)+'-best')
            save_actor(policy,folder,data.stats,dict(**config,step=total_steps,training_complete=True,
                val_selected_step=best_val['step'],val_selected_loss=best_val['loss']))
            restored=Actor.load(folder,device='cuda')
            inputs={k:torch.from_numpy(v.copy()).unsqueeze(0).to('cuda') for k,v in own.items()}
            policy.eval()
            with torch.inference_mode():
                if not torch.equal(policy.predict_action_chunk(inputs),restored.policy.predict_action_chunk(inputs)):
                    raise ValueError('saved prediction readback changed')
            del restored
            report['checkpoints'].append(dict(step=total_steps,path=str(folder),
                sha256=sha256(folder/'model.safetensors'),readback_verified=True,selected='best_val'))
            report['best_val']=dict(step=best_val['step'],loss=best_val['loss'],checkpoint=str(folder))
        report.update(status='complete',complete=True,readback_verified=True,
            checkpoint=report['checkpoints'][-1]['path'],checkpoint_sha256=report['checkpoints'][-1]['sha256'],
            peak_gpu_bytes=torch.cuda.max_memory_allocated())
    except BaseException as error:
        report.update(status='SUPERVISOR_STOP' if isinstance(error,InterruptedError) else 'HOST_ERROR',error=repr(error),complete=False)
        raise
    finally:
        report['wall_s']=time.monotonic()-started
        write(a.out/'summary.json',report)
        if lease.exists() and read(lease).get('pid')==os.getpid():
            lease.unlink()


if __name__=='__main__':
    main()
