"""Pinned release21-B runner; only the ACT12 observer switch differs in A/B."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0, str(ROOT))


def main():
    from scripts.run_grasp_act_release import run
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--episode', type=int, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--record-training', action='store_true')
    a = p.parse_args()
    records = ROOT/'experiments/2026-10-15-release-record'
    plan = json.loads(subprocess.check_output(['zstd', '-qdc', str(records/'record-plan.json.zst')]))
    profile = json.loads((records/'profile-B.json').read_text())
    result = run(plan['episodes'][a.episode], a.out, cap_s=180., **profile,
                 record_training=a.record_training,
                 recording_adapter='act12_observer_v1' if a.record_training else 'off')
    print(json.dumps({k:result.get(k) for k in ('status','release_success','release_outcome','input_audit')}))
    if result['status'] != 'complete' or not result.get('release_success'):raise SystemExit(1)


if __name__ == '__main__':main()
