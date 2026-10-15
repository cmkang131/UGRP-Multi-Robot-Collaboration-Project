"""v6 own-observation dataset. Teacher fields never enter model inputs.

Conversion is offline; numpy/Pillow only. Torch and LeRobot are loaded only by
the GPU trainer. Episode/robot/task boundaries and excluded intervals are hard
chunk boundaries. Metadata is kept outside the tensor input whitelist.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from harness import grasp_act_contract as c

DATA_SCHEMA = 'ugrp.grasp_act.dataset.v1'
DONE_LABELS = ('teacher_v1', 'last_local_row_v1')
IMAGE_HW = (240, 320)
MODEL_IMAGE_HW = (480, 640)
IMAGE_KEYS = ('observation.images.own_history',)
INPUT_KEYS = frozenset((*IMAGE_KEYS, 'observation.state'))
TRAIN_KEYS = INPUT_KEYS | {'action', 'action_is_pad'}
# The state slot contains issued commands / discrete instructions, NEVER joints.
CONTINUOUS = list(range(c.HISTORY * 14)) + [c.CONTEXT_DIM - 2, c.CONTEXT_DIM - 1]


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def write_summary(path, value):
    """Write report-only nonfinite numbers as null, without changing inputs.

    Contracts, tensors and checkpoint metadata still use strict write_json;
    a missing report metric must never relax model-input validation.
    """
    def clean(item):
        if isinstance(item, np.ndarray):
            return clean(item.tolist())
        if isinstance(item, np.generic):
            return clean(item.item())
        if isinstance(item, float) and not math.isfinite(item):
            return None
        if isinstance(item, dict):
            return {key: clean(v) for key, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [clean(v) for v in item]
        return item
    write_json(path, clean(value))


def read_rows(path):
    path = Path(path)
    if path.suffix != '.zst':
        return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]
    # Existing recording format uses the zstd CLI. No new framework/dependency.
    raw = subprocess.check_output(['zstd', '-dc', str(path)])
    return [json.loads(s) for s in raw.splitlines() if s.strip()]


def read_json(path):
    path = Path(path)
    raw = subprocess.check_output(['zstd', '-dc', str(path)]) if path.suffix == '.zst' else path.read_bytes()
    return json.loads(raw)


def safe_path(root, rel):
    root = Path(root).resolve()
    target = (root / rel).resolve()
    if not target.is_relative_to(root) or Path(rel).is_absolute():
        raise ValueError('path escapes dataset/episode')
    return target


def image_array(jpeg):
    with Image.open(io.BytesIO(jpeg)) as im:
        if im.size != (640, 480):
            raise ValueError('original student camera must be 640x480')
        return np.asarray(im.convert('RGB').resize(IMAGE_HW[::-1], Image.Resampling.BILINEAR),
                          dtype=np.uint8).transpose(2, 0, 1).copy()


def normalized_image(image, blank=False):
    # A separately trained blank-image control receives constant zero pixels,
    # with identical preprocessing; never evaluated as a post-hoc ablation only.
    x = np.zeros_like(image) if blank else image
    return (x.astype(np.float32) / 255. - np.array([.485, .456, .406], np.float32)[:, None, None]) / np.array([.229, .224, .225], np.float32)[:, None, None]


def history_image(frames, *, blank=False):
    """Fixed row-major lag montage preserves temporal identity in upstream ACT.

    Upstream reuses the same positional grid for each camera, so merely naming
    four camera keys does NOT encode lag order. A 2x2 montage uses one spatial
    grid: [5.2s, 1.5s; .5s, now]. No extra measurements or learned framework.
    """
    if len(frames) != 4 or any(np.asarray(x).shape != (3, *IMAGE_HW) for x in frames):
        raise ValueError('four resized own frames required')
    rows = [np.concatenate(frames[i:i+2], axis=2) for i in (0, 2)]
    return normalized_image(np.concatenate(rows, axis=1), blank)


def audit_camera(camera):
    if (camera['schema'] != c.SCHEMA or camera['width'] != 640 or camera['height'] != 480
            or camera['period_s'] != c.PERIOD_S or camera['hz'] != 10.
            or camera['camera'] != 'robot_cam'):
        raise ValueError('camera contract mismatch')
    if camera['sources']['harness/grasp_act_contract.py'] != sha256(Path(c.__file__)):
        raise ValueError('recorded student contract differs from loader')


def paired_segments(observations, labels, *, done_label='teacher_v1', include_initial_approach_v1=False):
    """Select local rows, optionally deriving completion from skill row order.

    A skill interval has one actor/episode/task identity. Excluded rows and
    clock gaps split action chunks, but do not create extra completion targets.
    Derived labels are copies; teacher originals and privileged fields are
    never used to choose the last local row.
    """
    if done_label not in DONE_LABELS:
        raise ValueError('unknown done_label protocol option')
    if not observations or len(observations) != len(labels):
        raise ValueError('nonempty one-to-one student/teacher alignment required')
    seen, pairs = set(), []
    previous = None
    for obs, label in zip(observations, labels):
        c.validate_observation(obs)  # strict nested allowlist, including excluded rows
        sid = obs['sample_id']
        if sid in seen or label['sample_id'] != sid:
            raise ValueError('duplicate or mismatched sample id')
        seen.add(sid)
        if previous is not None and obs['t'] <= previous:
            raise ValueError('non-monotone student clock')
        previous = obs['t']
        if (label['skill'] != obs['skill'] or label['object_kind'] != obs['object_kind']
                or type(label['done']) is not bool or type(label['local_skill_sample']) is not bool):
            raise ValueError('teacher label mismatch')
        if label.get('perturbation_interval', False) and label['local_skill_sample']:
            raise ValueError('perturbation interval cannot be a training target')
        target = c.command(label['clean_teacher_command'])
        if abs(target['t'] - obs['t']) > 1e-6:
            raise ValueError('teacher command time mismatch')
        if label['done'] and label['terminal_reason'] != 'command_sequence_complete':
            raise ValueError('timeout/failure cannot be a done target')
        if (include_initial_approach_v1 and obs['skill'] == 'grasp'
                and label.get('teacher_phase') in ('start', 'fold', 'approach')
                and not label.get('perturbation_interval', False)):
            # ACT15 raw audit: ACT14 starts at skill elapsed=0, but ACT13's
            # selected support starts at .7..4.9 SIM s (350 fold +102 approach
            # rows omitted in 50 episodes). Include the recorded expert prefix,
            # not a deployment warmup/controller. Original labels stay intact.
            label = {**label, 'local_skill_sample': True}
        key = tuple(obs[k] for k in ('robot_id', 'skill', 'object_kind', 'role', 'destination_zone'))
        key += (sid.split(':')[0],)
        pairs.append((obs, label, key))
    if done_label == 'last_local_row_v1':
        from itertools import groupby
        derived = []
        for _, interval in groupby(pairs, key=lambda pair: pair[2]):
            interval = list(interval)
            last_local = next((i for i in range(len(interval) - 1, -1, -1)
                               if interval[i][1]['local_skill_sample']), None)
            for i, (obs, label, key) in enumerate(interval):
                done = i == last_local
                derived.append((obs, {**label, 'done': done,
                    'terminal_reason': 'command_sequence_complete' if done else None}, key))
        pairs = derived
    groups, current = [], []
    for obs, label, key in pairs:
        contiguous = current and abs(obs['t'] - current[-1][0]['t'] - c.PERIOD_S) < 1e-5
        same = current and key == current[-1][2] and not current[-1][1]['done']
        if current and (not contiguous or not same or not label['local_skill_sample']):
            groups.append(current)
            current = []
        if label['local_skill_sample']:
            current.append((obs, label, key))
    if current:
        groups.append(current)
    return groups


def fit_stats(states, actions, seeds):
    states, actions = np.asarray(states, np.float64), np.asarray(actions, np.float64)
    if not len(states) or len(states) != len(actions):
        raise ValueError('nonempty training rows required for normalization')
    mean, std = np.zeros(c.CONTEXT_DIM), np.ones(c.CONTEXT_DIM)
    mean[CONTINUOUS] = states[:, CONTINUOUS].mean(0)
    std[CONTINUOUS] = np.maximum(states[:, CONTINUOUS].std(0), .01)
    return {'schema': DATA_SCHEMA, 'train_seeds': sorted(set(seeds)), 'rows': len(states),
            'state_mean': mean.tolist(), 'state_std': std.tolist(),
            'action_mean': actions.mean(0).tolist(),
            'action_std': np.maximum(actions.std(0), .01).tolist(),
            'fit_scope': 'unique selected training timesteps only; no padded targets; no heldout'}


def assert_tensor_keys(batch, *, training=False):
    if set(batch) != (TRAIN_KEYS if training else INPUT_KEYS):
        raise ValueError('model input whitelist mismatch')


def convert(runs_root, protocol, output, *, seeds=None):
    output = Path(output)
    done_label = protocol.get('done_label', 'teacher_v1')
    if done_label not in DONE_LABELS:
        raise ValueError('unknown done_label protocol option')
    requested = protocol['train_seeds'] + protocol['validation_seeds']
    if len(requested) != len(set(requested)):
        raise ValueError('split overlap or duplicate seeds')
    seeds = requested if seeds is None else list(seeds)
    if not seeds or len(set(seeds)) != len(seeds) or not set(seeds) <= set(requested):
        raise ValueError('unknown or duplicate conversion seeds')
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': DATA_SCHEMA, 'status': 'running', 'complete': False,
              'protocol': protocol, 'done_label': done_label, 'image_hw': list(IMAGE_HW), 'episodes': [],
              'input_keys': sorted(INPUT_KEYS), 'normalization': None,
              'input_audit': {'forbidden_input_fields': 0, 'teacher_input_fields': 0},
              'admission': protocol.get('admission', 'user/coordinator accepted 50/50; not independently remeasured')}
    write_json(output / 'manifest.json', report)
    train_x, train_y, train_seeds = [], [], []
    sample_ids, camera_reference = set(), None
    try:
        for seed in seeds:
            run = Path(runs_root) / protocol['run_pattern'].format(seed=seed)
            raw = run / 'raw'
            # Remote runner transport checkout can differ from the pinned teacher.
            # An explicit per-episode mapping is required; result.source_sha below
            # must still match the executed teacher. Never rewrite original files.
            transport_sha = protocol.get('transport_sha_by_seed', {}).get(str(seed), protocol['teacher_sha'])
            if (run / 'SOURCE_SHA').read_text().strip() != transport_sha:
                raise ValueError('transport source SHA mismatch')
            result_path = raw / 'result.json.zst' if (raw / 'result.json.zst').exists() else raw / 'result.json'
            result = read_json(result_path)
            if ((run / 'EXIT').read_text().strip() != '0' or result.get('status') != 'complete'
                    or result.get('source_sha') != protocol['teacher_sha']
                    or result.get('physical_success') is not True or result.get('training_rgb') is not True
                    or result.get('student_execution') is not False or result.get('recording_mode') != 'training'):
                raise ValueError('completed successful teacher recording required')
            if protocol.get('recovery_mode'):
                if (result.get('recovery', {}).get('mode') != protocol['recovery_mode']
                        or result.get('noise_sha256') != protocol['noise_sha256']
                        or result.get('training_candidate') is not True
                        or not result.get('recovery_gate')
                        or result.get('input_audit', {}).get('held_world_reads') != 0
                        or result.get('input_audit', {}).get('invisible_measurements') != 0):
                    raise ValueError('unqualified recovery recording')
                if (protocol.get('rotation_calibration') and
                        result['recovery'].get('rotation_calibration') != protocol['rotation_calibration']):
                    raise ValueError('rotation calibration mismatch')
            plan = json.loads((raw / 'plan.json').read_text())
            if plan['seed'] != seed:
                raise ValueError('plan seed mismatch')
            camera = json.loads((raw / 'student-camera.json').read_text())
            audit_camera(camera)
            if camera_reference is not None and camera != camera_reference:
                raise ValueError('mixed camera configuration')
            camera_reference = camera
            split = 'train' if seed in protocol['train_seeds'] else 'validation'
            students = sorted(raw.glob('student-*.jsonl.zst')) or sorted(raw.glob('student-*.jsonl'))
            if not students:
                raise ValueError('no student records')
            for student in students:
                robot = student.name.split('.')[0].removeprefix('student-')
                teacher = raw / student.name.replace('student-', 'teacher-', 1)
                observations, labels = read_rows(student), read_rows(teacher)
                from harness.grasp_act_perturb import PERTURB_MODES
                if protocol.get('recovery_mode') in PERTURB_MODES:
                    from harness.grasp_act_perturb import verified_recovery_audit, validate_recorded_labels
                    validate_recorded_labels(labels, verified_recovery_audit(result, result_path))
                if any(o['robot_id'] != robot for o in observations):
                    raise ValueError('mixed actor in file')
                groups = paired_segments(observations, labels, done_label=done_label,
                    include_initial_approach_v1=protocol.get('include_initial_approach_v1', False))
                if not groups:
                    raise ValueError('no local skill samples')
                selected = [pair for group in groups for pair in group]
                ids = [o['sample_id'] for o, _, _ in selected]
                if sample_ids.intersection(ids):
                    raise ValueError('duplicate episode across inputs')
                sample_ids.update(ids)
                folder = output / f'{seed}-{robot}'
                folder.mkdir()
                refs = {}
                for obs, _, _ in selected:
                    for ref in obs['rgb']:
                        old = refs.setdefault(ref['path'], ref)
                        if old != ref or Path(ref['path']).parts[:2] != ('rgb', robot):
                            raise ValueError('conflicting or foreign RGB reference')
                ordered = sorted(refs)
                frame_index = {name: i for i, name in enumerate(ordered)}
                images = np.lib.format.open_memmap(folder / 'images.npy', mode='w+', dtype=np.uint8,
                                                  shape=(len(ordered), 3, *IMAGE_HW))
                for i, name in enumerate(ordered):
                    path = safe_path(raw, name)
                    if sha256(path) != refs[name]['sha256']:
                        raise ValueError('raw RGB hash mismatch')
                    images[i] = image_array(path.read_bytes())
                images.flush()
                del images
                states, targets, pads, image_ids, metadata = [], [], [], [], []
                counts, done = Counter(), Counter()
                for group in groups:
                    windows = c.training_windows([p[0] for p in group], [p[1] for p in group])
                    for (obs, label, _), window in zip(group, windows):
                        states.append(c.context(obs))
                        targets.append(window['action'])
                        pads.append(window['action_is_pad'])
                        image_ids.append([frame_index[r['path']] for r in obs['rgb']])
                        metadata.append({k: obs[k] for k in ('sample_id', 'robot_id', 'role', 'object_kind', 'skill', 't')})
                        counts[obs['skill']] += 1
                        done[obs['skill']] += int(label['done'])
                        if split == 'train':
                            train_x.append(states[-1])
                            train_y.append(c.encode_action(label['clean_teacher_command'], done=label['done']))
                            train_seeds.append(seed)
                np.savez_compressed(folder / 'tensors.npz', state=np.asarray(states, np.float32),
                                    action=np.asarray(targets, np.float32), action_is_pad=np.asarray(pads, bool),
                                    image_index=np.asarray(image_ids, np.int64))
                write_json(folder / 'samples.json', metadata)
                write_json(folder / 'rgb-provenance.json', [refs[p] for p in ordered])
                sources = {str(p.relative_to(run)): sha256(p) for p in
                           (student, teacher, raw / 'student-camera.json', raw / 'plan.json',
                            result_path, run / 'SOURCE_SHA', run / 'EXIT')}
                report['episodes'].append({'path': folder.name, 'seed': seed, 'split': split, 'robot_id': robot,
                    'source_root': str(run), 'source_hashes': sources, 'rows_total': len(observations),
                    'rows_selected': len(states), 'frames': len(refs), 'skill_counts': dict(counts),
                    'done_counts': dict(done), 'missing_done_skills': sorted(k for k in counts if done[k] == 0),
                    'files': {p.name: sha256(p) for p in folder.iterdir()}})
        if train_x:
            stats = fit_stats(train_x, train_y, train_seeds)
            write_json(output / 'normalization.json', stats)
            report['normalization'] = {'path': 'normalization.json', 'sha256': sha256(output / 'normalization.json')}
        report.update(status='complete' if set(seeds) == set(requested) else 'partial_audit',
                      complete=set(seeds) == set(requested), camera=camera_reference)
        write_json(output / 'RUN_META.json', {'class': protocol.get('run_class', 'milestone'), 'scope': 'student tensors and teacher targets',
                                             'raw_source_retained': True})
        report['files'] = {str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob('*'))
                           if p.is_file() and p.name != 'manifest.json'}
    except BaseException as exc:
        report.update(status='HOST_ERROR', error_type=type(exc).__name__, complete=False)
        raise
    finally:
        write_json(output / 'manifest.json', report)
    return report


class GraspDataset:
    """Map-style torch-compatible loader; IDs and truth are never returned."""
    def __init__(self, root, split, *, blank=False):
        self.root, self.blank = Path(root), blank
        self.manifest = json.loads((self.root / 'manifest.json').read_text())
        if self.manifest['schema'] != DATA_SCHEMA or not self.manifest['complete']:
            raise ValueError('only complete audited datasets may train/evaluate')
        if split not in ('train', 'validation'):
            raise ValueError('unknown split')
        norm = self.manifest['normalization']
        if sha256(safe_path(self.root, norm['path'])) != norm['sha256']:
            raise ValueError('normalization hash mismatch')
        self.stats = json.loads((self.root / norm['path']).read_text())
        if self.stats['train_seeds'] != sorted(self.manifest['protocol']['train_seeds']):
            raise ValueError('normalization split mismatch')
        self.shards, self.index = [], []
        for episode in self.manifest['episodes']:
            if episode['split'] != split:
                continue
            folder = safe_path(self.root, episode['path'])
            for name, digest in episode['files'].items():
                if sha256(safe_path(folder, name)) != digest:
                    raise ValueError('tensor dataset hash mismatch')
            with np.load(folder / 'tensors.npz', allow_pickle=False) as f:
                data = {k: f[k] for k in f.files}
            if set(data) != {'state', 'action', 'action_is_pad', 'image_index'}:
                raise ValueError('tensor shard whitelist mismatch')
            data['images'] = np.load(folder / 'images.npy', mmap_mode='r', allow_pickle=False)
            j = len(self.shards)
            self.index.extend((j, i) for i in range(len(data['state'])))
            self.shards.append(data)
        if not self.index:
            raise ValueError('empty split')

    def __len__(self):
        return len(self.index)

    def __getitem__(self, index):
        j, i = self.index[index]
        s, stats = self.shards[j], self.stats
        batch = {IMAGE_KEYS[0]: history_image([s['images'][frame] for frame in s['image_index'][i]],
                                            blank=self.blank)}
        batch['observation.state'] = ((s['state'][i] - np.asarray(stats['state_mean'], np.float32)) /
                                      np.asarray(stats['state_std'], np.float32))
        batch['action'] = ((s['action'][i] - np.asarray(stats['action_mean'], np.float32)) /
                           np.asarray(stats['action_std'], np.float32))
        batch['action_is_pad'] = s['action_is_pad'][i].copy()
        batch['action'][batch['action_is_pad']] = 0.
        assert_tensor_keys(batch, training=True)
        return batch
