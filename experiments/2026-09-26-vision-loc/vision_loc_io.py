"""Episode tables, rounds, test registration and observation caches of the vision localization (shared helpers).

Used by ``vision_loc_cli.py`` (subcommands) and ``vision_loc_score.py`` (GT
metrics). Round 2 = ``episodes.json`` (vl-*), round 3 = ``episodes_v3.json``
(vl3-*, independent dev/test); each round has its own test registration and
its one registered test scoring (``ROUNDS``).
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path

import numpy as np

import vision_loc as vl

HERE = Path(__file__).resolve().parent
PRIMARY_OUT = Path('/Users/changmin/projects/ugrp/outputs/vision-loc-20260926')
RENDER_ROOT = Path(os.environ.get('VL_RENDER_ROOT', PRIMARY_OUT/'render'))
MAP_FILE = HERE/'maps'/'zone_wide_door_walls_v3_notags.json'


def sha_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


EPISODE_FILES = ('episodes.json', 'episodes_v3.json')        # round 2, round 3 (independent dev/test)
# Per round: the test registration and the one registered test scoring. Round 2 (vl-*) is closed: its test
# was scored once (results/metrics_test.json) and turned out not independent of train (overlap audit).
ROUNDS = {'vl': {'prereg': 'prereg.json', 'metrics': 'results/metrics_test.json'},
          'vl3': {'prereg': 'prereg_v3.json', 'metrics': 'results/metrics_test_v3.json'}}


def episodes_table() -> dict:
    """Both episode tables merged (episode ids are unique across rounds)."""
    eps = []
    for name in EPISODE_FILES:
        path = HERE/name
        if path.exists():
            eps += json.loads(path.read_text())['episodes']
    ids = [e['episode_id'] for e in eps]
    if len(set(ids)) != len(ids):
        raise SystemExit('duplicate episode ids across the episode tables')
    return {'episodes': eps}


def episode(ep: str) -> dict:
    for e in episodes_table()['episodes']:
        if e['episode_id'] == ep:
            return e
    raise SystemExit(f'unknown episode {ep!r}')


def split_of(ep: str) -> str:
    return episode(ep)['split']


def round_of(ep: str) -> str:
    prefix = ep.split('-', 1)[0]
    if prefix not in ROUNDS:
        raise SystemExit(f'episode {ep!r} belongs to no round')
    return prefix


def spawn_y(ep: str) -> float:
    return float(episode(ep)['spawn_y'])


def load_map() -> dict:
    return json.loads(MAP_FILE.read_text())


def load_json(path):
    return json.loads(Path(path).read_text()) if path else {}


def test_round(episodes) -> str | None:
    """The round of the test episodes in ``episodes`` (None: no test episode); mixing rounds is refused."""
    rounds = {round_of(e) for e in episodes if split_of(e) == 'test'}
    if len(rounds) > 1:
        raise SystemExit(f'test episodes of several rounds in one call: {sorted(rounds)}')
    return next(iter(rounds), None)


def require_frozen(episodes, *, checkpoint=None, config=None, calibration=None, needs=()):
    """Test episodes only with the pre-registered student: the round's prereg present and every frozen hash unchanged.

    ``needs`` names the inputs this subcommand uses ('checkpoint', 'config',
    'calibration'); each must be given for a test run (an omitted file would
    silently fall back to code defaults that differ from the frozen values).
    Round 3: only the registered test episodes (independence audit passed) run.
    """
    rnd = test_round(episodes)
    if rnd is None:
        return None
    path = HERE/ROUNDS[rnd]['prereg']
    if not path.exists():
        raise SystemExit(f'test refused: no {path.name} (register the gate and the frozen student first)')
    pre = json.loads(path.read_text())
    st = pre['student']
    unregistered = [e for e in episodes if split_of(e) == 'test' and e not in pre['test_episodes']]
    if unregistered:
        raise SystemExit(f'test refused: not registered test episodes {unregistered}')
    given = {'checkpoint': checkpoint, 'config': config, 'calibration': calibration}
    missing = [k for k in needs if given[k] is None]
    if missing:
        raise SystemExit(f'test refused: {missing} must be the registered files (no code defaults on test)')
    bad = [f for f, h in st['frozen_files_sha256'].items() if not (HERE/f).exists() or sha_file(HERE/f) != h]
    if checkpoint is not None and sha_file(checkpoint) != st['model']['sha256']:
        bad.append('checkpoint')
    if config is not None and sha_file(config) != st['config']['sha256']:
        bad.append('config')
    if calibration is not None and sha_file(calibration) != st['calibration']['sha256']:
        bad.append('calibration')
    if bad:
        raise SystemExit(f'test refused: differs from {path.name}: {bad}')
    return {'round': rnd, 'prereg': path.name, 'prereg_sha256': sha_file(path)}


OBS_SCHEMA = 'ugrp.vision_loc.obs.v2'
OBS_KINDS = {'vision': 'own frames only (inputs/frames.jsonl + frames/) through the segmentation network',
             'oracle': 'EVAL-ONLY teacher segmentation renders (diagnostic, never a student input)'}


def obs_provenance(kind: str, ep: str, obs_params: dict, *, config_path, checkpoint_sha256=None, infer_size=None) -> dict:
    """Provenance an observation cache must carry (checked again by ``load_obs`` before any use)."""
    if kind not in OBS_KINDS:
        raise ValueError(f'unknown observation kind {kind!r}')
    ep_dir = RENDER_ROOT/ep
    meta = {'schema': OBS_SCHEMA, 'kind': kind, 'source': OBS_KINDS[kind], 'episode': ep,
            'frames_jsonl_sha256': sha_file(ep_dir/'inputs'/'frames.jsonl'), 'obs_params': obs_params,
            'config_sha256': sha_file(config_path)}
    if kind == 'vision':
        if not checkpoint_sha256 or infer_size is None:
            raise ValueError('vision observations need the checkpoint hash and the inference size')
        meta.update(checkpoint_sha256=checkpoint_sha256, infer_size=[int(v) for v in infer_size])
    else:
        meta['labels_jsonl_sha256'] = sha_file(ep_dir/'eval_only'/'labels.jsonl')
    return meta


def save_obs(path: Path, frames_idx, obs_list, extra: dict):
    if Path(path).exists():
        raise SystemExit(f'refusing to overwrite {path}')
    if not obs_list:
        raise SystemExit(f'no frames for {path}')
    arr = {k: np.stack([getattr(o, k) for o in obs_list]) for k in ('b_kind', 'b_lo', 'b_hi', 't_kind', 't_lo', 't_hi')}
    arr['b_kind'] = arr['b_kind'].astype(np.int8)
    arr['t_kind'] = arr['t_kind'].astype(np.int8)
    for k in ('b_lo', 'b_hi', 't_lo', 't_hi'):
        arr[k] = arr[k].astype(np.float32)
    np.savez_compressed(path, frame=np.asarray(frames_idx, np.int32), columns=obs_list[0].columns, **arr,
                        meta=np.asarray(json.dumps(extra)))


def load_obs(path: Path, *, kind: str, episode: str, obs_params: Mapping, checkpoint_sha256: str | None = None,
             infer_size=None) -> tuple[dict, dict]:
    """Observation cache of one episode, refused unless its provenance matches the requested use.

    Checked: schema, observation kind (an oracle cache passed as vision observations
    is refused), episode, the episode's current ``inputs/frames.jsonl`` hash and the
    exact frame index sequence, the observation parameters and, for vision caches,
    the segmentation checkpoint hash and inference size.
    """
    z = np.load(path, allow_pickle=False)
    meta = json.loads(str(z['meta']))
    problems = []
    if meta.get('schema') != OBS_SCHEMA:
        problems.append(f"schema {meta.get('schema')!r} (regenerate the cache)")
    if meta.get('kind') != kind:
        problems.append(f"kind {meta.get('kind')!r} != {kind!r}")
    if meta.get('episode') != episode:
        problems.append(f"episode {meta.get('episode')!r} != {episode!r}")
    frames_path = RENDER_ROOT/episode/'inputs'/'frames.jsonl'
    if not frames_path.exists():
        problems.append(f'no {frames_path}')
    elif meta.get('frames_jsonl_sha256') != sha_file(frames_path):
        problems.append('frames.jsonl hash differs')
    elif [int(f) for f in z['frame']] != [int(r['frame']) for r in vl.read_jsonl(frames_path)]:
        problems.append('frame index sequence differs from frames.jsonl')
    if meta.get('obs_params') != json.loads(json.dumps(dict(obs_params))):
        problems.append('observation parameters differ')
    if kind == 'vision':
        if not checkpoint_sha256 or meta.get('checkpoint_sha256') != checkpoint_sha256:
            problems.append('segmentation checkpoint hash differs or was not given')
        if infer_size is None or meta.get('infer_size') != [int(v) for v in infer_size]:
            problems.append('inference size differs')
    if problems:
        raise SystemExit(f'observation cache {path} refused: {problems}')
    cols = z['columns']
    out = {}
    for i, f in enumerate(z['frame']):
        out[int(f)] = vl.ColumnObs(cols, z['b_kind'][i].astype(int), z['b_lo'][i].astype(float),
                                   z['b_hi'][i].astype(float), z['t_kind'][i].astype(int), z['t_lo'][i].astype(float),
                                   z['t_hi'][i].astype(float))
    return out, meta


def config_obs_params(cfg: Mapping) -> dict:
    return {**vl.DEFAULT_OBS, **cfg.get('obs', {})}


def config_infer_size(cfg: Mapping) -> tuple[int, int]:
    size = cfg.get('infer_size')
    if not (isinstance(size, (list, tuple)) and len(size) == 2 and all(isinstance(v, int) and v > 0 for v in size)):
        raise SystemExit(f'config needs infer_size [w, h] (positive integers), got {size!r}')
    return int(size[0]), int(size[1])
