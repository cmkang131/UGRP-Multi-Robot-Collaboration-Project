"""Build the shared image cache and run one named fine-tune variant (torch env).

usage: train_run.py cache            # decode all frames once
       train_run.py <variant> [...]  # A_aug_only | C_mix_rgb | B_mix_perimg | B_mix_gray | F_floorlight_only
Variants (all start from seg-v2 weights; same steps/lr/seed):
  A_aug_only        original default TRAIN-episode frames only; strong photometric aug + label-guided floor recolour
  C_mix_rgb         static renders under 24 random floor/light/wall looks + floor_light_v1 + default, plus the same replay frames
  B_mix_perimg      C_mix_rgb data, per-image per-channel standardised input
  B_mix_gray        C_mix_rgb data, luminance-only standardised input
  F_floorlight_only static floor_light_v1 + default + replay (the 'fit one guess of the floor colour' ablation)
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import seg_ft
import seg_model as sm

OUT = Path('/Users/changmin/projects/ugrp/outputs/seg-lightfloor-20260929')
TRAIN_ROOT = OUT / 'train'
CACHE = OUT / 'cache' / 'mix'
VLR = Path('/Users/changmin/projects/ugrp/outputs/vision-loc-20260926/render')
N_PER_LOOK = 300
REPLAY_EVERY = 5


def items_all():
    items = []
    for d in sorted(TRAIN_ROOT.iterdir()):
        man = json.loads((d / 'manifest.json').read_text())
        for r in man['rows'][:N_PER_LOOK]:
            items.append((d / r['file'], d / r['label'], 'static:' + d.name))
    for i in range(8):
        ep = VLR / f'vl-train-s90{i + 1}'
        for fr, lb in sm.episode_items(ep, REPLAY_EVERY):
            items.append((fr, lb, 'replay'))
    return items


VARIANTS = {
    'A_aug_only': dict(kinds=('replay',), pre='rgb', recolour_p=.7, cast=.10, gamma=.40),
    'C_mix_rgb': dict(kinds=('static', 'replay'), pre='rgb', recolour_p=.3, cast=.06, gamma=.25),
    'B_mix_perimg': dict(kinds=('static', 'replay'), pre='perimg', recolour_p=.3, cast=.06, gamma=.25),
    'B_mix_gray': dict(kinds=('static', 'replay'), pre='gray_perimg', recolour_p=.3, cast=.06, gamma=.25),
    'F_floorlight_only': dict(kinds=('static:floor_light_v1', 'static:default', 'replay'), pre='rgb', recolour_p=0., cast=.03, gamma=.15),
}

if __name__ == '__main__':
    if sys.argv[1] == 'cache':
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        it = items_all()
        print(len(it), 'items')
        seg_ft.build_cache(it, CACHE)
        sys.exit()
    meta = json.loads(Path(str(CACHE) + '_meta.json').read_text())
    kinds = np.array([m['kind'] for m in meta])
    rng = np.random.default_rng(0)
    perm = rng.permutation(len(meta))
    val_all = set(perm[:int(.03 * len(meta))].tolist())
    for name in sys.argv[1:]:
        v = VARIANTS[name]
        pick = np.array([any(k == p or (p == 'static' and k.startswith('static:')) for p in v['kinds']) for k in kinds])
        train_idx = [i for i in range(len(meta)) if pick[i] and i not in val_all]
        val_idx = [i for i in sorted(val_all) if pick[i]]
        print(name, len(train_idx), 'train', len(val_idx), 'val', flush=True)
        seg_ft.train(CACHE, train_idx, val_idx, OUT / 'model' / name, pre=v['pre'], epochs=3, lr=3e-4, recolour_p=v['recolour_p'],
                     cast=v['cast'], gamma=v['gamma'], tag=name, log=lambda s: print(s, flush=True))
