"""Inject a wrong neighbour in memory only; never writes the raw collection."""
import argparse
from pathlib import Path
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repo', type=Path, default=Path.cwd())
parser.add_argument('--loaded-root', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.repo.resolve()))

from scripts.final_pair_calibration_io import Inputs, load_collection
from harness.zone_final_pair_excitation import MAP_ID

root = args.loaded_root.resolve()


class WrongNeighbour(Inputs):
    def rows(self, path):
        data = super().rows(path)
        if path == root/MAP_ID/'eval_only/r1/pose.jsonl':
            for key in ('base_position_m', 'base_rotation'):
                data[2088][key] = data[2089][key]
        return data


load_collection(root, 'loaded', WrongNeighbour())
print('COUNTEREXAMPLE: load_collection accepted pose[2089] contents at pose[2088] clock/index')
