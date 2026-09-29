"""Floor / light / wall appearance specs for the seg-lightfloor study (pure python, no mujoco).

A "look" of the room = ground checker colours (rgb1, rgb2), a scale on the light colours, and a scale/tint on the wall
rgba.  `default` and `floor_light_v1` are the repository render profiles; everything else is a synthetic domain
randomisation draw.  Train draws and held-out draws use disjoint seed ranges AND disjoint hue/brightness regions
(see `HELD_OUT`), so held-out looks are new floor colours, not just new poses.
"""
from __future__ import annotations

import colorsys
import hashlib

import numpy as np

DEFAULT_LOOK = {'name': 'default', 'profile': 'default'}
FLOOR_LIGHT_LOOK = {'name': 'floor_light_v1', 'profile': 'floor_light_v1'}

# Held-out floor looks (never in any training draw): neutral light plain (no checker), warm beige checker, cool light-blue
# checker, a mid green-grey checker with low contrast, a near-white glossy-like floor.  rgb values are ground texture rgb1 / rgb2.
HELD_OUT = [
    {'name': 'ho_plain_grey', 'profile': 'floor_light_v1', 'rgb1': [.55, .55, .55], 'rgb2': [.55, .55, .55], 'light_scale': .3, 'wall_scale': 1.0},
    {'name': 'ho_warm_beige', 'profile': 'floor_light_v1', 'rgb1': [.60, .52, .40], 'rgb2': [.75, .66, .52], 'light_scale': .3, 'wall_scale': 1.0},
    {'name': 'ho_cool_lightblue', 'profile': 'floor_light_v1', 'rgb1': [.45, .58, .72], 'rgb2': [.62, .74, .86], 'light_scale': .3, 'wall_scale': 1.0},
    {'name': 'ho_green_lowcontrast', 'profile': 'floor_light_v1', 'rgb1': [.42, .50, .40], 'rgb2': [.47, .55, .44], 'light_scale': .3, 'wall_scale': 1.0},
    {'name': 'ho_near_white', 'profile': 'floor_light_v1', 'rgb1': [.72, .72, .70], 'rgb2': [.86, .86, .84], 'light_scale': .3, 'wall_scale': 1.0},
]
# A held-out WALL look (light walls, e.g. white boards) on the repository floor_light_v1 floor: tests whether robustness to floor
# colour was bought by ignoring wall colour.
HELD_OUT_WALL = {'name': 'ho_light_walls', 'profile': 'floor_light_v1', 'rgb1': [.36, .35, .34], 'rgb2': [.62, .61, .59], 'light_scale': .3, 'wall_scale': 2.4}


def train_looks(n: int, seed: int = 4242) -> list[dict]:
    """n synthetic random looks.  Mid/high floor brightness dominates (the real floor is lighter than the sim's), a minority is
    dark (so the default-like appearance is not forgotten)."""
    rng = np.random.default_rng(seed)
    out = []
    while len(out) < n:
        v1 = float(rng.uniform(.18, .80))                    # checker tone 1 brightness
        contrast = 1.0 if rng.random() < .2 else float(rng.uniform(1.08, 2.0))
        v2 = min(.95, v1 * contrast)
        hue, sat = float(rng.uniform(0, 1)), float(rng.uniform(0, .40))
        rgb1 = list(colorsys.hsv_to_rgb(hue, sat, v1))
        rgb2 = list(colorsys.hsv_to_rgb((hue + float(rng.uniform(-.03, .03))) % 1., sat, v2))
        look = {'name': f'tr{len(out):02d}', 'profile': 'floor_light_v1', 'rgb1': [round(c, 3) for c in rgb1], 'rgb2': [round(c, 3) for c in rgb2],
                'light_scale': round(float(np.exp(rng.uniform(np.log(.22), np.log(.45)))), 3),
                'wall_scale': round(float(np.exp(rng.uniform(np.log(.8), np.log(1.7)))), 3)}
        # keep clear of every held-out floor (RGB distance of the mean colour): the held-out draws must stay new
        mean = (np.array(look['rgb1']) + np.array(look['rgb2'])) / 2
        if any(np.linalg.norm(mean - (np.array(h['rgb1']) + np.array(h['rgb2'])) / 2) < .10 for h in HELD_OUT):
            continue
        out.append(look)
    return out


def look_sha(look: dict) -> str:
    import json
    return hashlib.sha256(json.dumps(look, sort_keys=True).encode()).hexdigest()
