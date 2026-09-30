"""Read-only combination pin for the separate, unregistered P03 candidate."""
from pathlib import Path

from harness.vision_loc_protocol import (
    ROOT, ProtocolError, canonical, file_sha256, load_config, load_json, sha256_bytes,
)

PROVIDER_PIN_FILE = ROOT / 'configs/vision_loc_provider_p03.json'


def provider_runtime_contract(*, map_id, calibration=None, cfg=None, root=ROOT) -> dict:
    """Read-only P03 combination pin; no model bytes are loaded or executed.

    The candidate C_mix_rgb is preparation only. It cannot be selected by a
    cfg override while retaining seg-v2 camera/robot validation labels.
    """
    root = Path(root)
    path = root / PROVIDER_PIN_FILE.relative_to(ROOT)
    pin = load_json(path)
    active = pin['active']
    if map_id not in active['map_ids'] or (calibration is not None and calibration != active['motion_calibration']):
        raise ProtocolError('P03 model/robot/render/camera combination is not pinned for this map/calibration')
    cfg = load_config() if cfg is None else cfg
    for key, value in active['model'].items():
        if cfg['model'].get(key) != value:
            raise ProtocolError(f'P03 model {key} differs from the active seg-v2 pin; C_mix_rgb is preparation only')
    hashes = {rel: file_sha256(root / rel) for rel in active['files_sha256']}
    if hashes != active['files_sha256']:
        raise ProtocolError('P03 pinned model/robot/render/camera source hash mismatch')
    registry = load_json(root / 'configs/model_artifacts.json')
    artifact = next((a for a in registry['artifacts'] if a['id'] == active['model']['artifact_id']), None)
    if artifact is None or artifact['status'] != 'available' or artifact['release']['tag'] != active['model']['release']:
        raise ProtocolError('active segmentation Release is missing from model_artifacts')
    entry = next((f for f in artifact['files'] if f['path'] == active['model']['entrypoint']), None)
    if entry is None or (entry['sha256'], entry['bytes']) != (active['model']['sha256'], active['model']['bytes']):
        raise ProtocolError('active segmentation Release file/hash differs from worker pin')
    from harness.zone_study_pose_delay_p03 import delay_contract
    return {'schema': pin['schema'], 'pin_file_sha256': file_sha256(path), 'active': active,
            'model_release_spec': artifact['release'], 'model_registry_entry_sha256': sha256_bytes(canonical(artifact)),
            'delay': delay_contract(cfg['sim_time_charge']), 'candidate_opt_in': pin['candidate_opt_in'],
            'verification': 'contract only; Release download/load and final calibration not verified in P03'}
