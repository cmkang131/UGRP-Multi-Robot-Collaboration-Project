"""Offline done-signal probe on recorded v7 episodes; no physics, no contract change.

Question: can the completion instant be predicted from the student's own issued
command history (state already contains 4 ticks) plus derived command-timing
features such as time-since-gripper-close, cumulative movement and time since
last command change? Fits causal classifiers on TRAIN200 and reports held-out
metrics on the 40 validation episodes (AUC, probability separation, persisted
firing-time offsets vs recorded done rows). Default OFF.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act17_data import read

SKILLS = ('grasp', 'release', 'approach', 'align', 'alignment')
SERVOS = ('1', '3', '4', '5', '6')
# From the v7 command contract: wheels are full-scale values, durations <=.15 s,
# PWM counts around 1500 center. Thresholds below are derived from the recorded
# teacher command stream, not from the evaluator or any ground-truth state.
GRIPPER_CLOSED_PWM = 1900
MOVING_WHEEL = 0.05


def episodes(root):
    manifest = read(root/'manifest.json')
    rows = []
    for episode in manifest['episodes']:
        folder = Path(root)/episode['path']
        with np.load(folder/'tensors.npz') as archive:
            state = archive['state'].astype(np.float32)
            action = archive['action'].astype(np.float32)
        metadata = read(folder/'samples.json')
        if len(metadata) != len(state):
            raise ValueError('metadata/state length mismatch')
        done = action[:, 0, -1]
        if not np.isin(done, [0.0, 1.0]).all():
            raise ValueError('binary completion label required')
        rows.append(dict(seed=episode['seed'], split=episode['split'], state=state,
                         action0=action[:, 0, :].copy(),
                         done=done,
                         t=np.asarray([m['t'] for m in metadata], np.float64),
                         skill=np.asarray([m['skill'] for m in metadata])))
    return rows


def skill_onehot(skill):
    out = np.zeros((len(skill), len(SKILLS)), np.float32)
    for index, name in enumerate(skill):
        if name in SKILLS:
            out[index, SKILLS.index(name)] = 1.0
    return out


def command_features(action0):
    """Causal features derived only from the recorded issued command stream."""
    n = len(action0)
    wheels = np.abs(action0[:, :4])
    duration = action0[:, 4:8]
    pwm = np.stack([action0[:, 8+i] for i in range(len(SERVOS))], axis=1)  # raw PWM counts after decode? encoded [-1,1]
    # encode_action stores (pwm-1500)/1000, so recover approximate PWM counts.
    pwm_counts = 1500.0 + 1000.0*pwm
    gripper = pwm_counts[:, 3:5].mean(axis=1)
    moving = wheels.max(axis=1) > MOVING_WHEEL
    closed = gripper > GRIPPER_CLOSED_PWM
    features = np.zeros((n, 14), np.float32)
    features[:, 0] = wheels.mean(axis=1)
    features[:, 1] = wheels.max(axis=1)
    features[:, 2] = duration.mean(axis=1)
    features[:, 3] = (duration > 0).mean(axis=1)
    features[:, 4:9] = pwm_counts/1500.0
    features[:, 9] = gripper/2500.0
    features[:, 10] = np.asarray([np.sum(wheels[:i+1].sum(axis=1)*duration[:i+1].mean(axis=1))
                                  for i in range(n)], np.float32)/10.0  # cumulative path proxy
    last_move = -1; since_move = np.zeros(n, np.float32)
    last_close = -1; since_close = np.full(n, -1.0, np.float32)
    close_ticks = np.zeros(n, np.float32)
    for i in range(n):
        if moving[i]:
            last_move = i
        since_move[i] = (i-last_move)
        if closed[i]:
            last_close = i
            close_ticks[i] = 1.0
        if last_close >= 0:
            since_close[i] = i-last_close
        close_ticks[i] = close_ticks[i-1]+close_ticks[i] if i else close_ticks[i]
    features[:, 11] = since_move/50.0
    features[:, 12] = since_close/50.0
    features[:, 13] = close_ticks/100.0
    return features


def windows(features, history):
    n = len(features)
    out = np.zeros((n, history, features.shape[1]), np.float32)
    mask = np.zeros((n, history), np.float32)
    for i in range(n):
        start = max(0, i-history+1)
        chunk = features[start:i+1]
        out[i, -len(chunk):] = chunk
        mask[i, -len(chunk):] = 1.0
    return out, mask


def train_mlp(train_x, train_y, seed, epochs, lr, width, pos_weight):
    import torch
    torch.manual_seed(seed)
    model = torch.nn.Sequential(torch.nn.Linear(train_x.shape[1], width), torch.nn.ReLU(),
                                torch.nn.Linear(width, width), torch.nn.ReLU(),
                                torch.nn.Linear(width, 1))
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_weight))
    x = torch.from_numpy(train_x); y = torch.from_numpy(train_y).unsqueeze(1)
    for _ in range(epochs):
        model.train(); optimizer.zero_grad()
        loss_fn(model(x), y).backward(); optimizer.step()
    return lambda array: torch.sigmoid(model(torch.from_numpy(array))).detach().numpy().ravel()


def train_gru(train_windows, train_mask, train_y, seed, epochs, lr, hidden, pos_weight, batch=1024):
    import torch
    torch.manual_seed(seed)
    model = torch.nn.GRU(train_windows.shape[2], hidden, batch_first=True)
    head = torch.nn.Linear(hidden, 1)
    parameters = list(model.parameters()) + list(head.parameters())
    optimizer = torch.optim.Adam(parameters, lr=lr)
    loss_fn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pos_weight))
    x = torch.from_numpy(train_windows); mask = torch.from_numpy(train_mask)
    y = torch.from_numpy(train_y).unsqueeze(1)
    n = len(x)
    for _ in range(epochs):
        model.train(); head.train()
        order = torch.randperm(n)
        for start in range(0, n, batch):
            index = order[start:start+batch]
            optimizer.zero_grad()
            output, _ = model(x[index])
            lengths = mask[index].sum(dim=1).clamp(min=1).long()
            last = output[torch.arange(len(index)), lengths-1]
            loss_fn(head(last), y[index]).backward(); optimizer.step()
    def predict(windows_, mask_):
        model.eval(); head.eval(); result = []
        with torch.inference_mode():
            for start in range(0, len(windows_), 1024):
                block = torch.from_numpy(windows_[start:start+1024])
                output, _ = model(block)
                lengths = torch.from_numpy(mask_[start:start+1024]).sum(dim=1).clamp(min=1).long()
                last = output[torch.arange(len(block)), lengths-1]
                result.append(torch.sigmoid(head(last)).numpy().ravel())
        return np.concatenate(result)
    return predict


def auc(score, label):
    score = np.asarray(score, np.float64); label = np.asarray(label, bool)
    order = np.argsort(score)
    ranks = np.empty(len(score), np.float64)
    ranks[order] = np.arange(1, len(score)+1)
    npos = label.sum(); nneg = len(label)-npos
    if npos == 0 or nneg == 0:
        return None
    return float((ranks[label].sum() - npos*(npos+1)/2) / (npos*nneg))


def firing_report(data, probabilities):
    done_ts = [float(t) for t, label in zip(data['t'], data['done']) if label == 1]
    out = []
    for threshold in (.5, .9):
        for persistence in (1, 3):
            fire = None; streak = 0
            for i, value in enumerate(probabilities):
                streak = streak+1 if value >= threshold else 0
                if streak >= persistence:
                    fire = float(data['t'][i-persistence+1]); break
            out.append(dict(threshold=threshold, persistence=persistence,
                            fired=fire is not None, fire_t=fire,
                            offsets_s=None if fire is None else [round(fire-t, 2) for t in done_ts],
                            false_fire_before_first_done=None if fire is None or not done_ts
                            else bool(fire < done_ts[0])))
    probabilities = np.asarray(probabilities, np.float64)
    argmax = int(probabilities.argmax())
    return dict(done_ts=done_ts, max_probability=float(probabilities.max()),
                argmax_t=float(data['t'][argmax]),
                argmax_offsets_s=[round(float(data['t'][argmax])-t, 2) for t in done_ts],
                firings=out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--enabled', action='store_true')
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--history', type=int, default=16)
    parser.add_argument('--epochs', type=int, default=8)
    parser.add_argument('--lr', type=float, default=1e-3)
    parser.add_argument('--width', type=int, default=256)
    parser.add_argument('--hidden', type=int, default=64)
    parser.add_argument('--seed', type=int, default=20261017)
    parser.add_argument('--threads', type=int, default=8)
    args = parser.parse_args()
    if not args.enabled:
        parser.error('offline done probe default OFF')
    import torch
    torch.set_num_threads(args.threads)
    all_episodes = episodes(args.dataset)
    for data in all_episodes:
        data['command'] = command_features(data['action0'])
        data['skill_features'] = skill_onehot(data['skill'])
        data['full'] = np.concatenate([data['state'], data['skill_features'], data['command']], axis=1)
        data['compact'] = np.concatenate([data['skill_features'], data['command']], axis=1)
    train = [d for d in all_episodes if d['split'] == 'train']
    validation = [d for d in all_episodes if d['split'] == 'validation']
    train_y = np.concatenate([d['done'] for d in train])
    val_y = np.concatenate([d['done'] for d in validation])
    prior = float(train_y.mean())
    pos_weight = (1-prior)/prior
    report = dict(schema='ugrp.act18.done_offline.v1', dataset=str(args.dataset),
                  history=args.history, epochs=args.epochs, seed=args.seed,
                  train_episodes=len(train), validation_episodes=len(validation),
                  train_rows=len(train_y), validation_rows=len(val_y),
                  train_positive=int(train_y.sum()), validation_positive=int(val_y.sum()),
                  prior=prior, pos_weight=pos_weight,
                  feature_note='state252(4-tick issued-command context)+skill one-hot+14 causal command features; labels are recorded completion rows only',
                  models={})

    def evaluate(name, flat_probabilities, use_windows):
        result = dict(auc=auc(flat_probabilities, val_y),
                      mean_positive_probability=float(flat_probabilities[val_y.astype(bool)].mean()),
                      mean_negative_probability=float(flat_probabilities[~val_y.astype(bool)].mean()))
        pointer = 0; episodes_out = []
        for data in validation:
            n = len(data['done'])
            probs = flat_probabilities[pointer:pointer+n]; pointer += n
            episodes_out.append(dict(seed=data['seed'], **firing_report(data, probs)))
        result['episodes'] = episodes_out
        fires = sum(1 for e in episodes_out for f in e['firings'] if f['threshold'] == .9 and f['fired'])
        early = sum(1 for e in episodes_out for f in e['firings']
                    if f['threshold'] == .9 and f['false_fire_before_first_done'])
        result['fire_summary_threshold_0.9'] = dict(episodes_fired=fires, early_fires=early,
                                                   episodes=len(episodes_out))
        entries = [f for e in episodes_out for f in e['firings'] if f['threshold'] == .9 and f['persistence'] == 1]
        errors = [min(abs(o) for o in f['offsets_s']) for f in entries if f.get('offsets_s')]
        errors.sort()
        result['fire_summary_threshold_0.9_persistence_1'] = dict(
            episodes_fired=len(entries), episodes=len(episodes_out),
            early_fires=sum(1 for f in entries if f['false_fire_before_first_done']),
            timing_error_median_s=float(np.median(errors)) if errors else None,
            timing_error_p90_s=float(np.percentile(errors, 90)) if errors else None,
            timing_error_max_s=float(max(errors)) if errors else None)
        report['models'][name] = result
        print(name, 'auc', round(result['auc'], 4) if result['auc'] else None,
              'pos_p', round(result['mean_positive_probability'], 4), flush=True)

    mlp_predict = train_mlp(np.concatenate([d['full'] for d in train]), train_y,
                            args.seed, args.epochs, args.lr, args.width, pos_weight)
    evaluate('mlp_state_command', mlp_predict(np.concatenate([d['full'] for d in validation])), False)

    train_windows = np.concatenate([windows(d['compact'], args.history)[0] for d in train])
    train_mask = np.concatenate([windows(d['compact'], args.history)[1] for d in train])
    gru_predict = train_gru(train_windows, train_mask, train_y, args.seed, args.epochs,
                            args.lr, args.hidden, pos_weight)
    windows_val = np.concatenate([windows(d['compact'], args.history)[0] for d in validation])
    mask_val = np.concatenate([windows(d['compact'], args.history)[1] for d in validation])
    evaluate('gru_command_history', gru_predict(windows_val, mask_val), True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(out=str(args.out), models={k: (None if v['auc'] is None else round(v['auc'], 4))
                                                      for k, v in report['models'].items()})), flush=True)


if __name__ == '__main__':
    main()
