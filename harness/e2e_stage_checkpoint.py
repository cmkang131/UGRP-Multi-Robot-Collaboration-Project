"""Causal own-input replay recipes; no simulator imports or GT controller input.

The recipe is a checkpoint, not a full mjSTATE_INTEGRATION save. Historical
occupancy cells were not logged: rebuild them from accepted own JPEGs and issued
commands, check recorded estimates, then hash the reconstructed map. Never use
final-map nodes which can have received future loop corrections.
"""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path

ROBOTS = ('r1', 'r2', 'r3')
SCHEMA = 'ugrp.e2e_stage_checkpoint.v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode()).hexdigest()


def rows(path):
    with Path(path).open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def at_or_before(values, t, key='t', max_gap=.61):
    selected = [r for r in values if float(r[key]) <= t+1e-7]
    if not selected or t-float(selected[-1][key]) > max_gap:
        raise ValueError('CHECKPOINT_SAMPLE_MISSING_OR_STALE')
    return selected[-1]


def prepare(raw, *, stage='align', cutoff=None):
    """Offline TEST_SETUP_GT extraction, returned separately from own_inputs."""
    raw = Path(raw)
    if stage not in ('align', 'mapping'):
        raise ValueError('UNKNOWN_STAGE')
    events = json.loads((raw/'transport-trace.json').read_text())
    align = next((e['t'] for e in events if e.get('event') == 'phase' and e.get('state') == 'align'),None)
    if cutoff is None and align is None:raise ValueError('EXPLICIT_MAPPING_CUTOFF_REQUIRED')
    cutoff = float(align if cutoff is None else cutoff)
    if cutoff < 0 or (stage == 'align' and abs(cutoff-align) > 1e-7) or (stage == 'mapping' and align is not None and cutoff >= align):
        raise ValueError('STAGE_CUTOFF_MUST_PRECEDE_SELECTED_CONTROL')
    source = json.loads((raw/'bundle.json').read_text())
    own = {}; manifests = {}
    origins = []
    for rid in ROBOTS:
        paths = {key:raw/f'robots/{rid}/{key}.jsonl' for key in ('commands','frames','ownmap')}
        logs = {k:rows(p) for k,p in paths.items()}
        accepted = [r for r in logs['ownmap'] if r['t'] <= cutoff+1e-7]
        if not accepted: raise ValueError('NO_ACCEPTED_OWN_RGB:'+rid)
        if any(r.get('stall_odometry',{}).get('counts',{}).get('us_zero',0) for r in accepted):
            raise ValueError('HISTORICAL_RANGE_CORRECTION_CANNOT_REPLAY_RGB_ONLY:'+rid)
        frames = {f['frame_id']:f for f in logs['frames']}
        origin = round(frames[accepted[0]['frame_id']]['sim_time']-accepted[0]['t'], 8)
        origins.append(origin)
        commands = []
        for row in logs['commands']:
            t = round(row['t']-origin,8)
            # At the cutoff, capture precedes control. Do not replay its commands.
            if t < cutoff-1e-8:
                action = {k:v for k,v in row.items() if k != 't'}
                commands.append(dict(t=t, action=action))
        selected_frames = []
        for row in accepted:
            f = frames[row['frame_id']]
            if f['sha256'] != row['sha256']: raise ValueError('OWN_RGB_LEDGER_MISMATCH')
            selected_frames.append(dict(t=row['t'],frame_id=f['frame_id'],sha256=f['sha256'],path=f['path'],
                expected_pose=row['pose_own_m'],expected_B_sha256=digest(row['remembered_B']),
                expected_beam_sha256=digest(row.get('own_beam'))))
        own[rid] = dict(commands=commands,frames=selected_frames)
        manifests.update({str(p.relative_to(raw)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.values()})
    if len(set(origins)) != 1: raise ValueError('SOURCE_CLOCKS_DISAGREE')
    absolute = cutoff+origins[0]
    truth = at_or_before(rows(raw/'eval_only/referee_truth.jsonl'),absolute,max_gap=.051)
    poses = {r:at_or_before(rows(raw/f'eval_only/{r}/trajectory.jsonl'),absolute,max_gap=.051) for r in ROBOTS}
    for name in ('scene.json','bundle.json','transport-trace.json','eval_only/referee_truth.jsonl',
                 *(f'eval_only/{r}/trajectory.jsonl' for r in ROBOTS)):
        manifests[name] = hashlib.sha256((raw/name).read_bytes()).hexdigest()
    scene=json.loads((raw/'scene.json').read_text())
    fingerprint={k:scene.get(k) for k in ('static_map_sha256','geometry_map_id','robot_model','robot_xml_sha256','contact_solver_profile','cargo')}
    setup = dict(scene_fingerprint=fingerprint,label='TEST_SETUP_GT',controller_feedback=False,robots=poses,beam=truth['items']['beam_1'],
                 reference='robot body origin xyz/yaw; beam origin xy/yaw and inertial COM z',
                 approximation='zero velocities and roll/pitch; arm initialized from issued pulses, not measured joints')
    recipe = dict(schema=SCHEMA,source_run=raw.parent.name,stage=stage,cutoff_s=cutoff,source_origin_s=origins[0],
        source_bundle=source,own_inputs=own,setup_only=setup,source_files=manifests,
        E2E_success_eligible=False,historical_grid_hash_available=False)
    recipe['checkpoint_sha256'] = digest(recipe)
    return recipe


def verify_recipe(recipe):
    payload = {k:v for k,v in recipe.items() if k != 'checkpoint_sha256'}
    if recipe['schema'] != SCHEMA or digest(payload) != recipe['checkpoint_sha256']:
        raise ValueError('CHECKPOINT_HASH_MISMATCH')


def own_map_record(robot):
    e = robot.goal.explorer
    # Include sparse occupancy + floor provenance, graph and own transform.
    def normalize(v):
        if hasattr(v,'tolist'):return normalize(v.tolist())
        if isinstance(v,dict):return [[normalize(k),normalize(x)] for k,x in sorted(v.items(),key=lambda p:repr(p[0]))]
        if isinstance(v,(tuple,list)):return [normalize(x) for x in v]
        if isinstance(v,set):return sorted((normalize(x) for x in v),key=repr)
        if hasattr(v,'__dict__'):return normalize(vars(v))
        return v
    return dict(grid=normalize(vars(e.grid)),latest=normalize(e.latest),
                local_pose=e.local_pose.tolist(),map_to_odom=e.map_to_odom.tolist(),
                memory=normalize(robot.goal.snapshot()))


def replay(recipe, raw, *, robot_factory=None, grasp_once='off'):
    """Rebuild source robot state from own inputs, never pass setup_only to it.

    Returns live robots and a verification receipt. Any estimate mismatch aborts
    before a physics backend is constructed. RGB bytes must match the ledger.
    """
    import numpy as np
    from PIL import Image
    from scripts.run_e2e_ownmap_live import make_robots
    verify_recipe(recipe)
    source = copy.deepcopy(recipe['source_bundle'])
    from harness.e2e_perception_fast import install as perception_install
    perception_install(source['e2e_options'].get('perception_fast','off'))
    import cv2
    cv2.setNumThreads(1)
    robots = (robot_factory or make_robots)(source)
    from harness.e2e_explore_idle import install as idle_install
    from harness.e2e_boundary_lifecycle import install as lifecycle_install
    idle_install(robots,source['e2e_options'].get('explore_idle','off'))
    lifecycle_install(robots,source['e2e_options'].get('boundary_lifecycle','off'))
    from harness.e2e_observation_cadence import configure
    from harness.e2e_mapping_cadence import period
    for robot in robots.values():configure(robot.goal,'on_v1',period(source['e2e_options'].get('mapping_cadence','off'),'mapping'))
    for robot in robots.values():robot.grasp_once=grasp_once
    receipt = {}
    for rid in ROBOTS:
        robot = robots[rid];saved = recipe['own_inputs'][rid]
        # Initial commands precede first capture. Later same-tick frames precede commands.
        events = [(c['t'],0 if c['t']==0 else 2,i,'command',c) for i,c in enumerate(saved['commands'])]
        events += [(f['t'],1,i,'frame',f) for i,f in enumerate(saved['frames'])]
        max_error = 0.;n = 0
        for t,_,_,kind,row in sorted(events):
            if kind == 'command':
                action = copy.deepcopy(row['action'])
                if action['kind'] == 'initial_servo_command':
                    robot.servo.update({int(k):v for k,v in action['pulses'].items()})
                else:robot.commanded(action,t)
                continue
            path = (Path(raw)/row['path']).resolve()
            if not path.is_relative_to(Path(raw).resolve()):raise ValueError('RGB_PATH_OUTSIDE_RAW')
            jpeg = path.read_bytes()
            if hashlib.sha256(jpeg).hexdigest() != row['sha256']:raise ValueError('RGB_HASH_MISMATCH:'+rid)
            obs = dict(frame_id=row['frame_id'],sim_time=t,sha256=row['sha256'],image=base64.b64encode(jpeg).decode())
            robot.receive(obs,np.asarray(Image.open(io.BytesIO(jpeg)).convert('RGB')))
            error = float(np.max(np.abs(np.asarray(robot.goal.explorer.local_pose)-row['expected_pose'])))
            max_error=max(max_error,error);n+=1
            if error > 1e-6 or digest(robot.goal.entities.get('B')) != row['expected_B_sha256']:
                raise ValueError(f'OWN_REPLAY_MISMATCH:{rid}:frame={row["frame_id"]}:pose_error={error}')
            if digest(robot.beam) != row['expected_beam_sha256']:
                raise ValueError(f'OWN_BEAM_REPLAY_MISMATCH:{rid}:frame={row["frame_id"]}')
        state = own_map_record(robot)
        encoded = json.dumps(state,sort_keys=True,allow_nan=False)
        restored = json.loads(encoded)
        if digest(state) != digest(restored):raise ValueError('OWN_MAP_ROUNDTRIP_MISMATCH')
        receipt[rid] = dict(accepted_frames=n,max_recorded_pose_error=max_error,map_sha256=digest(state),
            roundtrip_sha256=digest(restored),historical_grid_hash_available=False,
            historical_estimates_matched=True,issued_servo=dict(robot.servo))
    return robots,receipt
