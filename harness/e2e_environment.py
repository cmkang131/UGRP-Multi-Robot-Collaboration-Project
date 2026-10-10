"""Privileged setup registry for the new one-beam map. No provider admission."""
import copy
import json
from pathlib import Path
from harness.zone_final_environment import digest, sha

ROOT = Path(__file__).resolve().parents[1]
MAP_ID = 'zone_wide_door_e2e_b80_v1'
REGISTRY = 'configs/e2e_environment_v1.json'
SCENARIO = 'configs/zone_study_dev/e2e_one_beam_ownmap.json'


def resolve(*, root=ROOT):
    root = Path(root)
    row = json.loads((root/REGISTRY).read_text())
    mapped = json.loads((root/row['file']).read_text())
    parent = json.loads((root/row['parent_file']).read_text())
    expected = copy.deepcopy(parent)
    expected.update(map_id=MAP_ID, version=6)
    expected['regions']['zone_B']['half_extents_m'] = [.40, .70]
    if (mapped != expected or sha(root/row['file']) != row['sha256']
            or digest(mapped) != row['static_map_sha256']
            or sha(root/row['parent_file']) != row['parent_sha256']):
        raise ValueError('E2E_MAP_PARENT_OR_GEOMETRY_MISMATCH')
    # Camera/robot source provenance is reused; localization calibration and
    # historical transport success are explicitly NOT admitted on this new map.
    calibration = 'configs/calibration/zone_final_v3_contract.json'
    contract = json.loads((root/calibration).read_text())
    contract.update(status='UNMEASURED_NEW_MAP', maps={MAP_ID:digest(mapped)})
    row.update(calibration_contract=calibration, calibration_contract_sha256=sha(root/calibration))
    return mapped, row, contract
