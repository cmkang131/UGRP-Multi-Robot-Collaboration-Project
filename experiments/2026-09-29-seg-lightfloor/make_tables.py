"""Collect the small result files of the study into analysis/ and print the README tables (numpy only).

usage: make_tables.py   (reads /Users/changmin/projects/ugrp/outputs/seg-lightfloor-20260929/{eval,summary,model,b1})
"""
import json, shutil, sys, hashlib
from pathlib import Path
O = Path('/Users/changmin/projects/ugrp/outputs/seg-lightfloor-20260929')
HERE = Path(__file__).resolve().parent
A = HERE / 'analysis'
A.mkdir(exist_ok=True)

DEV = [('baseline seg-v2', 'dev_segv2_none'), ('seg-v2 + gain 0.4 (inference)', 'dev_segv2_gain0.4'), ('seg-v2 + per-image stretch (inference)', 'dev_segv2_stretch'),
       ('A aug-only fine-tune', 'dev_A_aug_only'), ('B perimg input', 'dev_B_mix_perimg'), ('B gray input', 'dev_B_mix_gray'),
       ('F floor_light only (small)', 'dev_F_floorlight_only'), ('F2 floor_light only (8k)', 'dev_F2_floorlight_8k'), ('C mixture', 'dev_C_mix_rgb'), ('C2 mixture + far-wall', 'dev_C2_mix_far')]
LOOKS = ['default', 'floor_light_v1', 'tr00', 'tr07', 'tr15', 'ho_plain_grey', 'ho_warm_beige', 'ho_cool_lightblue', 'ho_green_lowcontrast', 'ho_near_white', 'ho_light_walls']


def dev_table():
    print('| model | ' + ' | '.join(LOOKS) + ' |')
    print('|---|' + '---:|' * len(LOOKS))
    for name, f in DEV:
        p = O / 'eval' / f'{f}.json'
        if not p.exists():
            continue
        r = json.loads(p.read_text())['results']
        print(f'| {name} | ' + ' | '.join(f"{r[l]['iou_wall']:.2f}" if l in r else '-' for l in LOOKS) + ' |')
        shutil.copy(p, A / p.name)


B1 = [('baseline seg-v2 (B1 cohort)', 'base_floor_light_v1'), ('seg-v2 + per-image stretch (inference only)', 'inf_stretch'), ('A aug-only fine-tune', 'A_fl'), ('B per-image standardised input', 'B_mix_perimg_fl'), ('B luminance-only input', 'B_mix_gray_fl'), ('F2 floor_light-only fine-tune (8k)', 'F2_fl'),
      ('C mixture (480x360)', 'C_fl'), ('C mixture (640x480 inference)', 'C640_fl'), ('C2 mixture + far-wall', 'C2_fl')]


def b1_table(kind):
    print(f'| model | pass (9 cp) | pass (7 mid) | pooled 7-mid pos p50/p90 (cm) | yaw p90 (deg) | fail | flagged | failing checkpoints |')
    print('|---|---:|---:|---|---:|---:|---:|---|')
    for name, key in B1:
        if key is None:
            continue
        p = O / 'summary' / f'{key}_{kind}.json'
        if not p.exists():
            continue
        e = next(iter(json.loads(p.read_text()).values()))
        pm = e['pooled_mid']
        bad = ', '.join(f"cp{k}({c['pos_p90_cm']:.1f} cm{'' if c['flagged_rate']>=.5 else ', silent'})" for k, c in e['checkpoints'].items() if not c['pass'])
        print(f"| {name} | {e['n_pass_all9']}/9 | {e['n_pass_mid7']}/7 | {100*pm['pos_p50']:.1f} / {100*pm['pos_p90']:.1f} | {pm['yaw_p90']:.2f} | {100*pm['fail_rate']:.1f}% | {100*pm['flagged_rate']:.1f}% | {bad or '-'} |")
        shutil.copy(p, A / p.name)


HO = ['ho_plain_grey', 'ho_warm_beige', 'ho_cool_lightblue', 'ho_green_lowcontrast', 'ho_light_walls', 'tr07']


def ho_table():
    print('| model | ' + ' | '.join(HO) + ' |')
    print('|---|' + '---:|' * len(HO))
    for name, pre in (('baseline seg-v2', 'base'), ('C mixture', 'C'), ('F2 floor_light-only (8k)', 'F2')):
        cells = []
        for h in HO:
            p = O / 'summary' / f'{pre}_{h}_p20.json'
            if not p.exists():
                cells.append('-'); continue
            e = next(iter(json.loads(p.read_text()).values()))
            cells.append(f"{e['n_pass_all9']}/9, p90 {100*e['pooled_mid']['pos_p90']:.1f} cm, flagged {100*e['pooled_mid']['flagged_rate']:.0f}%")
            shutil.copy(p, A / p.name)
        print(f'| {name} | ' + ' | '.join(cells) + ' |')


if __name__ == '__main__':
    print('\n### B1 held-out floors p20'); ho_table()
    print('### dev wall IoU'); dev_table()
    for kind in ('p20', 'search'):
        print(f'\n### B1 floor_light_v1 {kind}'); b1_table(kind)
