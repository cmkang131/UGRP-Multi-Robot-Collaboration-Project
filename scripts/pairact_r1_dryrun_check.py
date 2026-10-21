"""pairact-r1 dry-run checks (SYNTHETIC_DRYRUN — 수집 데이터 아님 · 판정 아님 · teacher 시연 아님).

Sub-commands (each writes one labelled JSON; exit 1 when a plumbing check fails):

  verify-data          converted synthetic dataset + stage sidecar: complete, labelled,
                       2 seeds x 2 robots, ``missing_stages == []``  (CPU)
  reload               smoke checkpoint -> two independent loads through the existing
                       ``harness.pairact_r1.PairActActor.load`` -> fixed inputs ->
                       action chunk, done logit and stage logits ``torch.equal``  (GPU/CPU)
  student-eval-config  P5 ``--student-eval`` JSON with exactly the teacher -c5
                       ``harness.pairact_student_eval.CONFIG_KEYS`` (+ a separate label file)
  p5-report            P5 1-world plumbing report from the root runner output
                       (``student_eval.funnel`` present, ``teacher_steps == 0``,
                       ``gt_inputs_to_student == 0``); dry-run 배관 확인, 판정 아님

No new checkpoint loader, trainer or evaluator is defined here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LABEL = 'SYNTHETIC_DRYRUN — 수집 데이터 아님 · 판정 아님 · teacher 시연 아님'
P5_LABEL = 'dry-run 배관 확인, 판정 아님, 학습 데이터 합성 (SYNTHETIC_DRYRUN 300 step smoke 체크포인트)'
POLICY_LABEL = ('learned policy (student ACT), 그러나 합성 데이터 300 step smoke라 성능 의미 없음; '
                'teacher 아님')
MARK = {'label': LABEL, 'synthetic': True, 'judgement': None}
# Exact copy of teacher -c5 75929e7719ad98a089e3dda5251f4249d8bae511 harness/pairact_student_eval.py
# CONFIG_KEYS / MODE and root -r-c5 a93082c343ef5f3687851bf4b0c9fb0f2484ada1
# scripts/run_warp_flow_teacher.py STUDENT_EVAL_KEYS / STUDENT_EVAL_MODE / STUDENT_SHA.
STUDENT_EVAL_KEYS = frozenset({'mode', 'python', 'source', 'model', 'config', 'device'})
STUDENT_EVAL_MODE = 'pairact_r1_student_eval_v1'
STUDENT_SHA = '3c9337d5f5c9deefd49139b26ae7117022e3d5cc'
RAW_PROBE = dict(split='validation', robot='r1', row=40)   # fixed raw observation for predict_staged


def write_report(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


# ---------------------------------------------------------------- verify-data

def verify_data(dataset, stage_targets):
    dataset = Path(dataset)
    manifest = json.loads((dataset / 'manifest.json').read_text())
    sidecar = json.loads(Path(stage_targets).read_text())
    protocol = manifest.get('protocol', {})
    episodes = manifest.get('episodes', [])
    from harness.grasp_act_data import sha256
    checks = {
        'manifest_complete': manifest.get('complete') is True and manifest.get('status') == 'complete',
        'protocol_synthetic_label': protocol.get('synthetic') is True and protocol.get('label') == LABEL,
        'episodes_2_seeds_x_2_robots': sorted((e['split'], e['robot_id']) for e in episodes) ==
            [('train', 'r1'), ('train', 'r2'), ('validation', 'r1'), ('validation', 'r2')],
        'sidecar_bound_to_dataset': sidecar.get('dataset_manifest_sha256') == sha256(dataset / 'manifest.json'),
        'missing_stages_empty': sidecar.get('missing_stages') == [],
    }
    return {**MARK, 'check': 'verify-data', 'dataset': str(dataset), 'stage_targets': str(stage_targets),
            'checks': checks, 'passed': all(checks.values()),
            'h0_stage_counts': sidecar.get('h0_stage_counts'), 'missing_stages': sidecar.get('missing_stages'),
            'seeds': {'train': protocol.get('train_seeds'), 'validation': protocol.get('validation_seeds')}}


# ---------------------------------------------------------------- reload

def compare_outputs(first, second):
    """``torch.equal`` per named output tensor; shapes and dtypes are reported."""
    import torch
    if set(first) != set(second):
        raise ValueError('output name mismatch')
    return {k: {'torch_equal': bool(torch.equal(first[k], second[k])), 'shape': list(first[k].shape),
                'dtype': str(first[k].dtype)} for k in sorted(first)}


def raw_probe(dataset):
    """One fixed recorded synthetic observation + its own JPEGs (worker predict_staged input)."""
    manifest = json.loads((Path(dataset) / 'manifest.json').read_text())
    episode = next(e for e in manifest['episodes']
                   if e['split'] == RAW_PROBE['split'] and e['robot_id'] == RAW_PROBE['robot'])
    raw = Path(episode['source_root']) / 'raw'
    from harness.grasp_act_data import read_rows, safe_path
    observation = read_rows(raw / f'student-{RAW_PROBE["robot"]}.jsonl')[RAW_PROBE['row']]
    jpegs = [safe_path(raw, ref['path']).read_bytes() for ref in observation['rgb']]
    return observation, jpegs, str(raw)


def actor_outputs(actor, inputs, observation, jpegs):
    """Same upstream predict_action_chunk the trainer readback uses + the worker's predict_staged."""
    import torch
    with torch.inference_mode():
        chunk = actor.policy.predict_action_chunk(inputs).detach().clone()
        stage = actor.policy.model.action_head.stage_logits.detach().clone()
    staged = actor.predict_staged(observation, jpegs)
    return {'action_chunk': chunk, 'done_logit': chunk[..., -1].clone(), 'stage_logits': stage,
            'staged_chunk': torch.tensor(staged['chunk'], dtype=torch.float64),
            'staged_stage_logits': torch.tensor(staged['stage_logits'], dtype=torch.float64)}


def reload_check(run, dataset, stage_targets, *, device='cuda'):
    import torch
    from harness import beamact3
    from harness import pairact_r1 as p
    from harness.grasp_act_data import assert_tensor_keys
    run = Path(run)
    summary = json.loads((run / 'summary.json').read_text())
    if summary.get('status') != 'complete' or not summary.get('readback_verified'):
        raise ValueError('complete smoke summary with trainer readback_verified required')
    checkpoint = Path(summary['last_checkpoint']) / 'actor'
    torch.manual_seed(0)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    data = p.pair_dataset_class()(dataset, 'validation', stage_manifest=stage_targets)   # no augmentation
    probe = data[0]
    inputs = {k: torch.from_numpy(v.copy()).unsqueeze(0).to(device) for k, v in probe.items()
              if k.startswith('observation.')}
    assert_tensor_keys(inputs)
    inputs = beamact3.transform_batch(inputs, 'A')
    observation, jpegs, raw = raw_probe(dataset)
    outputs = []
    for _ in range(2):
        actor = p.PairActActor.load(checkpoint, device=device)    # existing loader, unchanged
        outputs.append({k: v.cpu() for k, v in actor_outputs(actor, inputs, observation, jpegs).items()})
        del actor
    compared = compare_outputs(*outputs)
    stages = p.decode_stages(outputs[0]['stage_logits'][0].numpy())
    return {**MARK, 'policy': POLICY_LABEL, 'check': 'reload', 'run': str(run), 'checkpoint': str(checkpoint),
            'step': summary.get('steps_completed'), 'source_sha': summary.get('source_sha'),
            'trainer_readback_verified': summary.get('readback_verified'),
            'fixed_inputs': {'tensor': 'PairActDataset(validation, no augmentation)[0], beamact3 arm A transform',
                             'raw': {**RAW_PROBE, 'raw_dir': raw, 'sample_id': observation['sample_id']}},
            'outputs': compared, 'decoded_stages_h0_to_h7': stages, 'device': device,
            'torch_equal': all(v['torch_equal'] for v in compared.values()),
            'passed': all(v['torch_equal'] for v in compared.values())}


# ---------------------------------------------------------------- student-eval-config

def student_eval_config(*, python, source, model, config, device='cuda'):
    """Exact 6-key P5 config. The label cannot go inside (root/teacher reject extra keys)."""
    cfg = {'mode': STUDENT_EVAL_MODE, 'python': str(python), 'source': str(source), 'model': str(model),
           'config': str(config), 'device': device}
    if set(cfg) != STUDENT_EVAL_KEYS:
        raise AssertionError('student eval key set drifted from teacher -c5 CONFIG_KEYS')
    for key in ('python', 'source', 'model', 'config'):
        if not Path(cfg[key]).is_absolute():
            raise ValueError(f'absolute {key} path required (root load_student_eval)')
    return cfg


def student_eval_label(cfg):
    return {**MARK, 'label_p5': P5_LABEL, 'policy': POLICY_LABEL, 'student_eval_config': cfg,
            'note': 'config JSON must hold exactly the 6 CONFIG_KEYS; this label lives in a separate file',
            'student_sha_required_by_root': STUDENT_SHA}


def source_head(path):
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()


# ---------------------------------------------------------------- p5-report

def p5_report(out):
    """Plumbing only. ``success`` values are copied but carry no judgement."""
    out = Path(out)
    summary = json.loads((out / 'summary.json').read_text())
    worlds = []
    for w in summary.get('worlds', []):
        raw = Path(w['raw'])
        result_path = raw / 'result.json.zst' if (raw / 'result.json.zst').is_file() else raw / 'result.json'
        from harness.grasp_act_data import read_json
        result = read_json(result_path) if result_path.is_file() else {}
        se = result.get('student_eval') or {}
        funnel = se.get('funnel')
        checks = {'result_json': result_path.is_file(),
                  'student_eval_funnel': isinstance(funnel, dict) and 'reached' in funnel,
                  'teacher_steps_0': se.get('teacher_steps') == 0 and w.get('teacher_steps') == 0,
                  'gt_inputs_to_student_0': se.get('gt_inputs_to_student') == 0,
                  'student_execution': result.get('student_execution') is True}
        worlds.append({'world': w.get('world'), 'seed': w.get('seed'), 'checks': checks,
                       'passed': all(checks.values()), 'funnel': funnel,
                       'success_not_a_judgement': w.get('success'),
                       'carry_success_not_a_judgement': w.get('carry_success'),
                       'student_worker_requests': w.get('student_worker_requests')})
    top = {'summary_student_eval': isinstance(summary.get('student_eval'), dict),
           'host_error_0': summary.get('HOST_ERROR') == 0,
           'one_world': len(worlds) == 1}
    passed = all(top.values()) and all(w['passed'] for w in worlds)
    return {**MARK, 'label_p5': P5_LABEL, 'policy': POLICY_LABEL, 'check': 'p5-report', 'out': str(out),
            'status': summary.get('status'), 'checks': top, 'worlds': worlds, 'passed': passed}


# ---------------------------------------------------------------- CLI

def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = a.add_subparsers(dest='cmd', required=True)
    v = sub.add_parser('verify-data')
    v.add_argument('--dataset', type=Path, required=True)
    v.add_argument('--stage-targets', type=Path, required=True)
    v.add_argument('--out', type=Path, required=True)
    r = sub.add_parser('reload')
    r.add_argument('--run', type=Path, required=True, help='trainer --output of the smoke run')
    r.add_argument('--dataset', type=Path, required=True)
    r.add_argument('--stage-targets', type=Path, required=True)
    r.add_argument('--device', default='cuda')
    r.add_argument('--out', type=Path, required=True)
    s = sub.add_parser('student-eval-config')
    for k in ('python', 'source', 'model', 'config'):
        s.add_argument('--' + k, type=Path, required=True)
    s.add_argument('--device', default='cuda')
    s.add_argument('--out', type=Path, required=True, help='student-eval.json (label goes to *.LABEL.json)')
    s.add_argument('--skip-source-head-check', action='store_true', help='tests only')
    q = sub.add_parser('p5-report')
    q.add_argument('--p5-out', type=Path, required=True, help='root runner --out directory')
    q.add_argument('--out', type=Path, required=True)
    args = a.parse_args(argv)
    if args.cmd == 'verify-data':
        report = verify_data(args.dataset, args.stage_targets)
    elif args.cmd == 'reload':
        report = reload_check(args.run, args.dataset, args.stage_targets, device=args.device)
    elif args.cmd == 'student-eval-config':
        cfg = student_eval_config(python=args.python, source=args.source, model=args.model,
                                  config=args.config, device=args.device)
        if not args.skip_source_head_check and source_head(args.source) != STUDENT_SHA:
            raise SystemExit(f'student worker source HEAD != pinned {STUDENT_SHA} (root would refuse)')
        if args.out.exists():
            raise SystemExit(f'{args.out} exists; new run root only')
        write_report(args.out, cfg)
        report = {**student_eval_label(cfg), 'passed': True}
        args.out = args.out.with_suffix('.LABEL.json')
    else:
        report = p5_report(args.p5_out)
    write_report(args.out, report)
    print(json.dumps({k: report.get(k) for k in ('check', 'label', 'passed')}, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
