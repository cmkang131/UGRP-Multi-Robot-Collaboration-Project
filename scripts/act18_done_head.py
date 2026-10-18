"""Done-head module for act18-doneh: GRU over the student's own command history.

Trained offline on TRAIN200 episodes from the recorded issued commands only
(skill one-hot + 14 causal command features from act18_done_offline). No RGB,
no ground-truth, no evaluator state. The module is integrated into evaluation as
an extra termination head: when its current-tick probability reaches the frozen
threshold, that tick is emitted as done (issued_done format is unchanged).
Default OFF; requires an explicitly trained and hash-verified module directory.
"""
import argparse
import hashlib
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act17_data import read
from act16w_runtime import frozen_source, sha256
from act17_compact_records import original_sha256

HISTORY = 16
HIDDEN = 64
SKILLS = ('grasp', 'wait', 'regrasp', 'release')
SERVOS = ('1', '3', '4', '5', '6')
FEATURE_SPEC = 'skill4_onehot+command14_v2'
THRESHOLD = .65
PERSISTENCE = 1


def native_episodes(root, split):
    from act17_data import read
    root = Path(root)
    manifest = read(root/'manifest.json')
    if manifest.get('schema') != 'ugrp.grasp_act.dataset.v1' or not manifest.get('complete'):
        raise ValueError('complete act16w native dataset required')
    rows = []
    for episode in manifest['episodes']:
        if episode['split'] != split:
            continue
        folder = root/episode['path']
        with np.load(folder/'tensors.npz') as archive:
            action = archive['action'].astype(np.float32)
        metadata = read(folder/'samples.json')
        rows.append(dict(seed=episode['seed'], split=split, action0=action[:, 0, :].copy(),
                         done=action[:, 0, -1],
                         t=np.asarray([m['t'] for m in metadata], np.float64),
                         skill=np.asarray([m['skill'] for m in metadata])))
    if not rows:
        raise ValueError('native split has no episodes')
    return rows


def command_vector(command):
    """Encode an issued command dict into the 14-dim action vector used offline."""
    duration = [float(x)/.15 for x in command['duration_s']]
    pwm = [(float(command['pwm'][servo])-1500.)/1000. for servo in SERVOS]
    return np.asarray([float(x) for x in command['wheels']] + duration + pwm + [0.0],
                      dtype=np.float32)


class CommandFeatureState:
    """Streaming twin of act18_done_offline.command_features (verified by tests)."""

    def __init__(self):
        self.step = 0
        self.path = 0.0
        self.last_move = -1
        self.last_close = -1
        self.close_ticks = 0.0

    def update(self, action):
        wheels = np.abs(np.asarray(action[:4], np.float64))
        duration = np.asarray(action[4:8], np.float64)
        pwm = np.asarray(action[8:13], np.float64)
        pwm_counts = 1500.0+1000.0*pwm
        # NOTE (2026-10-18 정정): SERVOS=(1,3,4,5,6) so slice index 3..4 is
        # servo 5 (shoulder) + servo 6 (yaw), not the gripper (servo 1, index
        # 0). `closed` below therefore never encoded gripper closure. Frozen on
        # purpose: changing it changes the done-head training input
        # (FEATURE_SPEC) and needs a new prereg + retrain; annotated only.
        gripper = float(pwm_counts[3:5].mean())
        moving = bool(wheels.max() > .05)
        closed = gripper > 1900.0
        self.path += float(wheels.sum()*duration.mean())/10.0
        if moving:
            self.last_move = self.step
        since_move = (self.step-self.last_move)/50.0
        if closed:
            self.last_close = self.step
            self.close_ticks += 1.0
        since_close_raw = -1.0 if self.last_close < 0 else float(self.step-self.last_close)
        since_close = since_close_raw/50.0
        feature = np.zeros(14, np.float32)
        feature[0] = wheels.mean()
        feature[1] = wheels.max()
        feature[2] = duration.mean()
        feature[3] = (duration > 0).mean()
        feature[4:9] = pwm_counts/1500.0
        feature[9] = gripper/2500.0
        feature[10] = self.path
        feature[11] = since_move
        feature[12] = since_close
        feature[13] = self.close_ticks/100.0
        self.step += 1
        return feature


def skill_onehot_vector(skill):
    out = np.zeros(len(SKILLS), np.float32)
    if skill in SKILLS:
        out[SKILLS.index(skill)] = 1.0
    return out


def padded_window(rows, history=HISTORY):
    rows = np.asarray(rows, np.float32)
    out = np.zeros((history, rows.shape[1]), np.float32)
    mask = np.zeros((history,), np.float32)
    chunk = rows[-history:]
    out[-len(chunk):] = chunk
    mask[-len(chunk):] = 1.0
    return out, mask


def done_fires(probability, threshold=THRESHOLD):
    return bool(float(probability) >= float(threshold))


def apply_done_override(command, fired):
    """Mirror the frozen decode_action done semantics: stop wheels on done."""
    if not fired:
        return command
    return {**command, 'wheels': [0.0]*4, 'duration_s': [0.0]*4}


def validate_metadata(meta, model_sha256):
    required = dict(schema='ugrp.act18.done_head.v1', feature_spec=FEATURE_SPEC,
                    history=HISTORY, hidden=HIDDEN, threshold=THRESHOLD, persistence=PERSISTENCE,
                    skills=list(SKILLS), servos=list(SERVOS))
    for key, value in required.items():
        if meta.get(key) != value:
            raise ValueError('done-head metadata mismatch: '+key)
    if meta.get('model_sha256') != model_sha256:
        raise ValueError('done-head model hash mismatch')
    if not isinstance(meta.get('source_sha'), str) or len(meta['source_sha']) != 40:
        raise ValueError('done-head source sha required')
    if not isinstance(meta.get('dataset_manifest_sha256'), str) or len(meta['dataset_manifest_sha256']) != 64:
        raise ValueError('done-head dataset manifest sha required')
    if not (isinstance(meta.get('validation_auc'), float) and meta['validation_auc'] > .5):
        raise ValueError('done-head validation auc required')
    return meta


class DoneHead:
    def __init__(self, model, meta, device='cpu'):
        self.model, self.meta, self.device = model, meta, device
        self.threshold = float(meta['threshold'])
        self.history = int(meta['history'])
        self.reset()

    def reset(self):
        self.state = CommandFeatureState()
        self.rows = []

    def update(self, command, skill):
        feature = self.state.update(command_vector(command))
        self.rows.append(np.concatenate([skill_onehot_vector(skill), feature]))
        window, mask = padded_window(self.rows, self.history)
        import torch
        with torch.inference_mode():
            x = torch.from_numpy(window).unsqueeze(0).to(self.device)
            output, _ = self.model(x)
            length = int(mask.sum())
            last = output[0, max(length-1, 0)]
            probability = float(torch.sigmoid(self.head(last)))
        return probability

    @classmethod
    def load(cls, root, device='cpu'):
        import torch
        root = Path(root)
        meta = read(root/'metadata.json')
        model_sha = sha256(root/'done-head.pt')
        validate_metadata(meta, model_sha)
        gru = torch.nn.GRU(len(SKILLS)+14, int(meta['hidden']), batch_first=True)
        head = torch.nn.Linear(int(meta['hidden']), 1)
        state = torch.load(root/'done-head.pt', map_location=device, weights_only=False)
        gru.load_state_dict(state['gru']); head.load_state_dict(state['head'])
        gru.to(device).eval(); head.to(device).eval()
        instance = cls(gru, meta, device)
        instance.head = head
        return instance


def train_module(dataset, out_dir, epochs, lr, seed, extra_native=None):
    import torch, json
    from act18_done_offline import episodes, command_features, skill_onehot, windows, auc, firing_report
    torch.set_num_threads(8)
    torch.manual_seed(seed)
    data = episodes(dataset)
    if extra_native is not None:
        data = data+[dict(item, source='act16w') for item in native_episodes(extra_native, 'train')]
        data += [dict(item, source='act16w') for item in native_episodes(extra_native, 'validation')]
    def compact(item):
        onehot = np.stack([skill_onehot_vector(name) for name in item['skill']])
        return np.concatenate([onehot, command_features(item['action0'])], axis=1)
    for item in data:
        item['compact'] = compact(item)
    train = [d for d in data if d['split'] == 'train']
    validation = [d for d in data if d['split'] == 'validation']
    train_y = np.concatenate([d['done'] for d in train])
    val_y = np.concatenate([d['done'] for d in validation])
    prior = float(train_y.mean()); pos_weight = (1-prior)/prior
    train_windows = np.concatenate([windows(d['compact'], HISTORY)[0] for d in train])
    train_mask = np.concatenate([windows(d['compact'], HISTORY)[1] for d in train])
    val_windows = np.concatenate([windows(d['compact'], HISTORY)[0] for d in validation])
    val_mask = np.concatenate([windows(d['compact'], HISTORY)[1] for d in validation])
    gru = torch.nn.GRU(len(SKILLS)+14, HIDDEN, batch_first=True)
    head = torch.nn.Linear(HIDDEN, 1)
    optimizer = torch.optim.Adam(list(gru.parameters())+list(head.parameters()), lr=lr)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_weight))
    x = torch.from_numpy(train_windows); mask = torch.from_numpy(train_mask)
    y = torch.from_numpy(train_y).unsqueeze(1)
    for _ in range(epochs):
        gru.train(); head.train()
        order = torch.randperm(len(x))
        for start in range(0, len(x), 1024):
            index = order[start:start+1024]
            optimizer.zero_grad()
            output, _ = gru(x[index])
            lengths = mask[index].sum(dim=1).clamp(min=1).long()
            last = output[torch.arange(len(index)), lengths-1]
            loss_fn(head(last), y[index]).backward(); optimizer.step()
    gru.eval(); head.eval()
    probabilities = []
    with torch.inference_mode():
        for start in range(0, len(val_windows), 1024):
            block = torch.from_numpy(val_windows[start:start+1024])
            output, _ = gru(block)
            lengths = torch.from_numpy(val_mask[start:start+1024]).sum(dim=1).clamp(min=1).long()
            last = output[torch.arange(len(block)), lengths-1]
            probabilities.append(torch.sigmoid(head(last)).numpy().ravel())
    probabilities = np.concatenate(probabilities)
    validation_auc = auc(probabilities, val_y)
    pointer = 0; episode_metrics = []
    for item in validation:
        n = len(item['done'])
        episode_metrics.append(dict(seed=item['seed'], **firing_report(item, probabilities[pointer:pointer+n])))
        pointer += n
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=False)
    torch.save(dict(gru=gru.state_dict(), head=head.state_dict()), out_dir/'done-head.pt')
    meta = dict(schema='ugrp.act18.done_head.v1', feature_spec=FEATURE_SPEC, history=HISTORY,
                hidden=HIDDEN, threshold=THRESHOLD, persistence=PERSISTENCE, skills=list(SKILLS),
                servos=list(SERVOS), source_sha=frozen_source(Path(__file__).resolve().parents[1]),
                dataset_manifest_sha256=original_sha256(Path(dataset)/'manifest.json'),
                native_manifest_sha256=(original_sha256(Path(extra_native)/'manifest.json')
                                        if extra_native is not None else None),
                datasets=('v7 TRAIN200 + act16w TRAIN32' if extra_native is not None else 'v7 TRAIN200'),
                train_seeds=[d['seed'] for d in train], train_rows=len(train_y),
                train_positive_rows=int(train_y.sum()), validation_rows=len(val_y),
                validation_positive_rows=int(val_y.sum()), validation_auc=float(validation_auc),
                epochs=epochs, lr=lr, seed=seed, pos_weight=float(pos_weight),
                model_sha256=sha256(out_dir/'done-head.pt'), episode_metrics=episode_metrics,
                note='GRU over own command history only; no RGB/ground-truth/evaluator inputs; '
                     'trained candidate is a hybrid done module, not an ACT-learned done head')
    (out_dir/'metadata.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2)+'\n')
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--extra-native', type=Path)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=8)
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument('--seed', type=int, default=20261017)
    args = parser.parse_args()
    if not args.enabled:
        parser.error('done-head training default OFF')
    meta = train_module(args.dataset, args.out_dir, args.epochs, args.lr, args.seed, args.extra_native)
    import json
    print(json.dumps(dict(out=str(args.out_dir), validation_auc=meta['validation_auc'],
                          model_sha256=meta['model_sha256']), ensure_ascii=False))


if __name__ == '__main__':
    main()
