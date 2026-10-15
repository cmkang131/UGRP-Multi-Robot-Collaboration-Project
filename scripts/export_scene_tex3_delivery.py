"""Small, source-linked final record; consume derived camera audit only."""
from pathlib import Path
import platform
from scripts.summarize_scene_tex3 import read, write, sha


def main():
    base = Path('/home/ugrp/ugrp-sim/runs')
    output = base/'scenetex3-delivery'
    output.mkdir(exist_ok=False)
    source = base/'scenetex3-r3-analysis'
    pairs = [('floor_light_textured_v1', 'native'), ('walls_floor_textured_v2', 'native'),
             ('walls_floor_textured_v3', 'native'), ('walls_floor_textured_v3', 'wall_no_mip_v1')]
    comparisons, tables = [], []
    for material, quality in pairs:
        a = read(source/(material+'--'+quality+'.json'))
        comparisons.append({'material': material, 'quality': quality, 'n': a['n'], 'classifier': a['classifier'],
            'drive_png': a['scopes']['drive']['png'], 'matches': a['matches'], 'segmentation': a['segmentation'],
            'paired': {enc: {k: v for k, v in row.items() if k in ('box_equal_v1', 'legacy_beam_semantic_equal_v1', 'positive_target_support')}
                       for enc, row in a['paired'].items()}, 'timing': a['timing'], 'timing_vs_native': a['timing_vs_native'],
            'occluded': a['occluded'], 'colour_intrusion': a['colour_intrusion']})
        if material == 'walls_floor_textured_v3':
            tables.append(read(source/(material+'--'+quality+'-rejection.json')))
    # Per-arm files retain full distributions. Split the compact record if it
    # crosses the existing storage cap; do not round results to fit it.
    for i, comparison in enumerate(comparisons):
        write(output/f'comparison-{i}.json', comparison)
    write(output/'rejection-table.json', {'decision': 'NOT_READY', 'round_budget': {'used': 3, 'maximum': 3},
        'candidates': tables, 'real_native_floor_reference': 'unavailable; derived real320x240 plate is not a matched floor reference',
        'reason': 'PNG/JPEG box parity restored, but per-pose floor features/matches not preserved; wall-contact inputs also regress',
        'raw_path': str(base/'scenetex3-r3-complete'),
        'reproduction': 'scripts/probe_scene_tex3.py + combine_scene_tex3.py + summarize_scene_tex3.py; exact commands retained in raw meta.json'})
    write(output/'summary.json', {'schema': 'ugrp.scenetex3_delivery.v1', 'decision': 'NOT_READY',
        'render_source_sha': '31286f8774e81a02aef016e95f3deb6edabff98e',
        'candidate': {'material': 'walls_floor_textured_v3', 'quality': 'wall_no_mip_v1', 'default': 'off',
                      'manifest_sha256': '521b6fa532222267061127bd373cfd0d6032b502f4508caf6c51aa349300698d'},
        'rounds': [read(base/('scenetex3-r'+str(i)+'-analysis')/'summary.json') for i in (1, 2, 3)],
        'comparison_files': [f'comparison-{i}.json' for i in range(4)],
        'rejection_table': '/Users/changmin/projects/ugrp-wt/scene-tex2/experiments/2026-10-16-scene-tex3/rejection-table.json',
        'selfmap_signal': str(base/'scenetex3-r3-selfmap-signal/summary.json'),
        'physics_steps': 0, 'model_calls': 0, 'Mac_render_calls': 0, 'Mac_GUI_calls': 0,
        'static_pair': 'atan(1/fx) base-yaw increment at SIM0; no physical motion, yaw-accuracy or task-success result',
        'tests': {'passed': 61, 'scope': 'Mac PNG/XML/pure sampling tests', 'seconds': 10.02},
        'pr': 'https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/527',
        'pooling': 'rounds/materials/qualities and gcp1 results never pooled; baseline media reused only with explicit source/hash links',
        'source_script_sha256': sha(Path(__file__))})
    write(output/'SHA256SUMS.json', {p.name: sha(p) for p in output.iterdir() if p.is_file()})


if __name__ == '__main__':
    if not platform.node().startswith('ugrp-sim-gcp2'):
        raise SystemExit('gcp2 only')
    main()
