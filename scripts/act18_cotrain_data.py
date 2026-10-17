"""Co-training dataset for act18-co: v7 jpeg TRAIN200 + act16w native 40-world dataset.

Both sources share state 252, action 14 and the 10 Hz command contract. A 2-dim
dataset-origin token is appended to observation.state (grasp/wait/regrasp/release
tokens already exist inside the recorded state). Images are unified to
current_full_v1 (single own RGB); native history slots use their newest frame.
No new recording, no ground truth, no evaluator state enters the policy input.
"""
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from act17_data import read, raw_image
from act17_compact_records import original_sha256
from act16w_runtime import sha256
from act18_policy import ReferenceDataset, extend_targets

SKILLS = ('grasp', 'wait', 'regrasp', 'release')
ORIGIN_V7 = 0
ORIGIN_NATIVE = 1
STATE_TOKEN_DIM = 2
BASE_ACTION_DIMS = 8
STD_FLOOR = .01


def origin_token(origin, state_token=True):
    if not state_token:
        return np.zeros(0, np.float32)
    return np.asarray([1.0, 0.0] if origin == ORIGIN_V7 else [0.0, 1.0], np.float32)


def _smooth_base(action, window):
    if window is None or window < 2:
        return np.array(action, dtype=np.float32, copy=True)
    kernel = np.ones(window, dtype=np.float64)/window
    out = np.array(action, dtype=np.float64, copy=True)
    for column in range(BASE_ACTION_DIMS):
        out[:, column] = np.convolve(action[:, column], kernel, mode='same')
    return out.astype(np.float32)


def native_episodes(root, split, chunk=20, smooth=5):
    manifest = read(Path(root)/'manifest.json')
    if manifest.get('schema') != 'ugrp.grasp_act.dataset.v1' or not manifest.get('complete'):
        raise ValueError('complete act16w native dataset required')
    episodes = []
    for episode in manifest['episodes']:
        if episode['split'] != split:
            continue
        folder = Path(root)/episode['path']
        with np.load(folder/'tensors.npz') as archive:
            state = archive['state'].astype(np.float32)
            action = archive['action'].astype(np.float32)
            image_index = archive['image_index'].astype(np.int64)
        metadata = read(folder/'samples.json')
        if len(metadata) != len(state) or action.shape[1] != 8:
            raise ValueError('native dataset layout mismatch')
        raw = action[:, 0, :]
        smoothed = _smooth_base(raw, smooth)
        targets, pad = extend_targets(smoothed, metadata, chunk)
        common = min(chunk, action.shape[1])
        if not np.array_equal(targets[:, :common, BASE_ACTION_DIMS:],
                              action[:, :common, BASE_ACTION_DIMS:]):
            raise ValueError('native co-training targets changed non-base columns')
        # The native shard stores one CHW image per recorded frame in images.npy;
        # image_index holds four history frame ids whose last entry is "now".
        for name, digest in episode['files'].items():
            if sha256(folder/name) != digest:
                raise ValueError('native shard file hash mismatch: '+name)
        images_path = folder/'images.npy'
        with np.load(folder/'tensors.npz', allow_pickle=False) as archive:
            image_count = int(archive['image_index'].max())+1
        image_shape = np.load(images_path, mmap_mode='r', allow_pickle=False).shape
        if image_shape[0] != image_count:
            raise ValueError('native image count mismatch')
        episodes.append(dict(seed=episode['seed'], split=split, state=state, action=targets,
                             action_is_pad=pad, image_index=image_index, images_path=str(images_path),
                             metadata=metadata, rows=len(state)))
    if not episodes:
        raise ValueError('native split has no episodes')
    return episodes


class CoTrainingDataset:
    """Episode-uniform mixture of the v7 reference view and the native 40-world set."""

    def __init__(self, v7_root, native_root, *, chunk=20, base_smooth_window=5,
                 native_weight=.5, state_token=True):
        if not 0 < native_weight < 1:
            raise ValueError('native weight must be within (0,1)')
        self.chunk = chunk
        self.native_weight = float(native_weight)
        self.state_token = bool(state_token)
        self.v7 = ReferenceDataset(v7_root, 'train', chunk=chunk,
                                   base_smooth_window=base_smooth_window)
        self.v7_root = Path(v7_root)
        self.native_root = Path(native_root)
        self.native = native_episodes(native_root, 'train', chunk=chunk, smooth=base_smooth_window)
        self.native_images = [np.load(episode['images_path'], mmap_mode='r', allow_pickle=False)
                              for episode in self.native]
        self.native_manifest_sha256 = original_sha256(self.native_root/'manifest.json')
        self.manifest = self.v7.manifest
        # combined statistics over TRAIN rows: state mean/std and action mean/std
        states = [shard['state'].astype(np.float64) for shard in self.v7.shards]
        states += [episode['state'].astype(np.float64) for episode in self.native]
        state = np.concatenate(states)
        actions = [shard['action'][:, 0, :].astype(np.float64) for shard in self.v7.shards]
        actions += [episode['action'][:, 0, :].astype(np.float64) for episode in self.native]
        action = np.concatenate(actions)
        action_std = np.maximum(action.std(axis=0), STD_FLOOR)
        state_std = np.maximum(state.std(axis=0), STD_FLOOR)
        self.stats = dict(state_mean=state.mean(axis=0).tolist(), state_std=state_std.tolist(),
                          action_mean=action.mean(axis=0).tolist(), action_std=action_std.tolist(),
                          scope='combined v7 TRAIN200 + act16w TRAIN32; std floor .01')
        self.state_dim = int(state.shape[1])+(STATE_TOKEN_DIM if state_token else 0)
        self.rows = len(self.v7)+sum(episode['rows'] for episode in self.native)
        self.starts = len(self.v7.episode_indices)+len(self.native)
        self.episode_origins = [ORIGIN_V7]*len(self.v7.episode_indices)
        self.episode_origins += [ORIGIN_NATIVE]*len(self.native)
        self.v7_state_mean = np.asarray(self.stats['state_mean'], np.float32)
        self.v7_state_std = np.asarray(self.stats['state_std'], np.float32)
        self.v7_action_mean = np.asarray(self.stats['action_mean'], np.float32)
        self.v7_action_std = np.asarray(self.stats['action_std'], np.float32)
        self.native_rows = np.asarray([episode['rows'] for episode in self.native], np.int64)
        self.native_cumsum = np.cumsum(self.native_rows)
        self.native_episode_scales = [np.arange(row_count, dtype=np.int64) for row_count in self.native_rows]

    def __len__(self):
        return self.rows

    def _token(self, origin):
        return origin_token(origin, self.state_token)

    def __getitem__(self, index):
        from harness.grasp_act_data import normalized_image
        if index < len(self.v7):
            shard_id, row = self.v7.index[index]
            shard = self.v7.shards[shard_id]
            frame = shard['frames'][shard['image_index'][row][-1]]
            image = normalized_image(raw_image(frame['path'], frame['sha256'], False))
            origin = ORIGIN_V7
            state = shard['state'][row]
            action = shard['action'][row]
            pad = shard['action_is_pad'][row]
        else:
            local = index-len(self.v7)
            episode_index = int(np.searchsorted(self.native_cumsum, local, side='right'))
            start = int(self.native_cumsum[episode_index-1]) if episode_index else 0
            row = local-start
            episode = self.native[episode_index]
            frame = np.asarray(self.native_images[episode_index][int(episode['image_index'][row][-1])])
            from PIL import Image
            frame = Image.fromarray(frame.transpose(1, 2, 0)).resize((640, 480), Image.BILINEAR)
            image = normalized_image(np.asarray(frame).transpose(2, 0, 1).copy())
            origin = ORIGIN_NATIVE
            state = episode['state'][row]
            action = episode['action'][row]
            pad = episode['action_is_pad'][row]
        normalized_state = (state-self.v7_state_mean)/self.v7_state_std
        normalized_state = np.concatenate([normalized_state, self._token(origin)])
        normalized_action = (action-self.v7_action_mean)/self.v7_action_std
        normalized_action[np.asarray(pad, bool)] = 0.
        return {'observation.images.own_history': image, 'observation.state': normalized_state.astype(np.float32),
                'action': normalized_action.astype(np.float32), 'action_is_pad': np.asarray(pad, bool).copy()}

    def sample(self, generator, batch_size, sampling):
        import torch
        if sampling != 'cotrain_v1':
            raise ValueError('declared co-training sampler required')
        selected = []
        for _ in range(batch_size):
            if torch.rand(1, generator=generator).item() < self.native_weight:
                episode = int(torch.randint(len(self.native), (1,), generator=generator))
                row = int(torch.randint(self.native[episode]['rows'], (1,), generator=generator))
                offset = int(self.native_cumsum[episode-1]) if episode else 0
                selected.append(len(self.v7)+offset+row)
            else:
                episode = int(torch.randint(len(self.v7.episode_indices), (1,), generator=generator))
                indices = self.v7.episode_indices[episode]
                selected.append(int(indices[int(torch.randint(len(indices), (1,), generator=generator))]))
        return selected

    def completion_priors(self, sampling):
        """Completion class fractions under the declared mixture measure."""
        if sampling != 'cotrain_v1':
            raise ValueError('declared co-training sampler required')
        totals = {skill: dict(mass=0., positive_mass=0., rows_N=0) for skill in SKILLS}
        # v7 episodes
        for indices in self.v7.episode_indices:
            mass = (1-self.native_weight)/len(self.v7.episode_indices)/len(indices)
            for index in indices:
                shard_id, row = self.v7.index[index]
                done = float(self.v7.shards[shard_id]['action'][row, 0, -1])
                skill = self.v7.metadata[index]['skill']
                if skill not in totals: continue
                totals[skill]['mass'] += mass; totals[skill]['positive_mass'] += mass*done
                totals[skill]['rows_N'] += 1
        for episode in self.native:
            mass = self.native_weight/len(self.native)/episode['rows']
            for row, metadata in enumerate(episode['metadata']):
                done = float(episode['action'][row, 0, -1])
                skill = metadata['skill']
                if skill not in totals: continue
                totals[skill]['mass'] += mass; totals[skill]['positive_mass'] += mass*done
                totals[skill]['rows_N'] += 1
        return {skill: {**value, 'positive_fraction': value['positive_mass']/value['mass'],
                        'source': 'combined mixture TRAIN h0 labels; not VAL'}
                for skill, value in totals.items() if value['rows_N'] and 0 < value['positive_mass'] < value['mass']}


class CoTrainingValidation:
    """Held-out v7 validation rows normalized with the combined TRAIN statistics.

    Used only for best-val checkpoint selection; the protocol VAL8 seeds are
    excluded by the caller, so VAL8 never selects the checkpoint.
    """

    def __init__(self, v7_root, stats, *, chunk=20):
        self.data = ReferenceDataset(v7_root, 'validation', chunk=chunk)
        self.chunk = chunk
        self.metadata = self.data.metadata
        self.state_mean = np.asarray(stats['state_mean'], np.float32)
        self.state_std = np.asarray(stats['state_std'], np.float32)
        self.action_mean = np.asarray(stats['action_mean'], np.float32)
        self.action_std = np.asarray(stats['action_std'], np.float32)
        self.token = origin_token(ORIGIN_V7)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        from harness.grasp_act_data import normalized_image
        shard_id, row = self.data.index[index]
        shard = self.data.shards[shard_id]
        frame = shard['frames'][shard['image_index'][row][-1]]
        image = normalized_image(raw_image(frame['path'], frame['sha256'], False))
        state = (shard['state'][row]-self.state_mean)/self.state_std
        state = np.concatenate([state, self.token]).astype(np.float32)
        action = (shard['action'][row]-self.action_mean)/self.action_std
        pad = np.asarray(shard['action_is_pad'][row], bool).copy()
        action[pad] = 0.
        return {'observation.images.own_history': image, 'observation.state': state,
                'action': action.astype(np.float32), 'action_is_pad': pad}
