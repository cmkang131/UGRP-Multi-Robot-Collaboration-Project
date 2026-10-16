"""Verify saved prediction provenance, lineage rebuild and final scoring only."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import odom_grid_replay as base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    root = args.source
    verified = []
    for condition in ('prob', 'rbpf30', 'rbpf100'):
        for seed in (911, 912, 913):
            for robot in ('r1', 'r2'):
                case = root/condition/f's{seed}-{robot}'
                grid = json.loads((case/'grid.json').read_text())
                summary = json.loads((case/'summary.json').read_text())
                assert all(json.loads((case/'off_golden.json').read_text()).values())
                hashes = json.loads((case/'prediction_hashes.json').read_text())
                for file, expected in hashes.items():
                    assert base.sha(case/file) == expected, file
                ledger = base.read_rows(case/'map_ledger.jsonl')
                assert len(ledger) == grid['frames']
                rebuilt = base.OdomGrid(robot)
                hit, miss = rebuilt.hit, rebuilt.miss
                for row in ledger:
                    w = row.get('insertion_weight', 1.)
                    rebuilt.hit, rebuilt.miss = hit*w, miss*w
                    rebuilt.insert(base.transform([row['camera']], row['pose'])[0],
                                   [base.transform(s, row['pose']) for s in row['segments']])
                assert rebuilt.export()['cells'] == grid['cells'], (condition, seed, robot, 'lineage_grid')
                covariance = base.read_rows(case/'covariance.jsonl')
                assert all(np.linalg.eigvalsh(row['covariance']).min() >= -1e-10 for row in covariance)
                scene = Path(next(x['path'] for x in summary['sources'] if x['path'].endswith('scene.xml'))).parent
                obstacles = json.loads((scene/'inputs/static_map.json').read_text())['obstacles']
                rects = np.array([list(o['center_m'])+list(o['half_extents_m']) for o in obstacles if o.get('kind') == 'wall'])
                direct, _ = base.quality(base.transform(rebuilt.occupied_points(), summary['origin_eval_only']), rects, base.wall_samples(rects))
                for key in ('precision_015', 'wall_coverage', 'wall_error_rmse_m', 'occupied_cells'):
                    assert direct[key] == summary['final'][key], (condition, seed, robot, key)
                if condition != 'prob':
                    particles = json.loads((case/'final_particles.json').read_text())
                    assert len(particles) == int(condition[4:])
                    assert abs(sum(p['weight'] for p in particles)-1.) < 1e-10
                    chosen = particles[grid['selected_particle']]
                    assert chosen['cells'] == grid['cells'] and chosen['history'] == ledger
                verified.append({'case': case.name, 'condition': condition, 'off_golden': True,
                                 'prediction_hashes': True, 'lineage_grid_exact': True,
                                 'covariance_psd': True, 'final_quality_exact': True})
    base.dump(root/'verification.json', {'verified': verified, 'script_sha256': base.sha(Path(__file__))})
    print(f'{len(verified)} cases: off bytes, prediction hashes, exact lineage rebuild, PSD and final map quality verified')


if __name__ == '__main__':
    main()
