"""Pure XML/profile and timing receipts for pair dev; no MuJoCo/model import."""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS_PREREG = ROOT / 'experiments/2026-09-27-zone-pair-dev/prereg_DRAFT.json'


def profile_contract():
    """Execute the unchanged base + cargo XML transforms to resolve options.

    The minimal named geoms satisfy the base transform's geometry contract.
    This is an option probe, never a compiled scene or contact validation.
    No timestep default is supplied: the selected profile must set it.
    """
    from sim.dispatch_contact_profile import contact_profile
    from sim.zone_cargo_contact import apply, base_profile, profile_record

    name = 'cargo_noslip_v1'
    root = ET.Element('mujoco')
    ET.SubElement(root, 'option')
    world = ET.SubElement(root, 'worldbody')
    names = [f'{r}__{side}_finger' for r in ('r1', 'r2', 'r3') for side in ('left', 'right')]
    for geom in [*names, 'team_beam_geom', 'dispatch_box_geom']:
        ET.SubElement(world, 'geom', name=geom)
    xml = apply(contact_profile(ET.tostring(root, encoding='unicode'), base_profile(name)), name)
    option = ET.fromstring(xml).find('option')
    dt = Decimal(option.attrib['timestep'])
    if not dt.is_finite() or dt <= 0:
        raise ValueError('profile timestep must be positive and finite')
    value = {'profile': name, 'base_profile': base_profile(name), 'cargo_profile': profile_record(name),
             'method': 'dispatch contact_profile then cargo apply on static XML option probe; no physics',
             'timestep_s': float(dt), 'noslip_iterations': int(option.attrib['noslip_iterations']),
             'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
                               ('sim/dispatch_contact_profile.py', 'sim/zone_cargo_contact.py')}}
    value['sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                               allow_nan=False).encode()).hexdigest()
    return value


def timing_contract(previous, timestep_s):
    """Keep SIM duration/20 Hz GT; scale the old wall budget by physics steps."""
    d = lambda v: Decimal(str(v))
    dt, old_dt = d(timestep_s), d(previous['environment']['timestep_s'])
    old = previous['limits']
    period = d('.05')
    sample_steps = int((period / dt).to_integral_value(rounding=ROUND_CEILING))
    period = sample_steps * dt
    # Preserve v1's 0.1 ms numerical margin beyond one sampling period + step.
    slack = d(previous['criteria']['max_sample_gap_s']) - d('.05') - old_dt
    sim_steps = int((d(old['sim_s']) / dt).to_integral_value(rounding=ROUND_CEILING))
    old_steps = int((d(old['sim_s']) / old_dt).to_integral_value(rounding=ROUND_CEILING))
    scale = d(sim_steps) / d(old_steps)
    wall = d(old['wall_s']) * scale
    cleanup = d(old['outer_wall_timeout_s']) - d(old['wall_s'])
    limits = {**old, 'wall_s': float(wall), 'outer_wall_timeout_s': float(wall + cleanup)}
    timing = {'gt_sample_steps': sample_steps, 'gt_sample_period_s': float(period),
              'sample_gap_slack_s': float(slack), 'max_sample_gap_s': float(period + dt + slack),
              'contact_observation_every_steps': 1, 'max_physics_steps': sim_steps,
              'previous_timestep_s': float(old_dt), 'previous_max_physics_steps': old_steps,
              'physics_step_multiplier': float(scale), 'outer_cleanup_s': float(cleanup),
              'coverage_rule': 'round((sim_end_s - simulator_start_s) / applied timestep_s); initial observation is not a step',
              'wall_basis': 'previous wall_s * (new max_physics_steps / previous max_physics_steps); '
                            'conservative step-count budget, not measured throughput or completion prediction; '
                            'SIM horizon and GT/video rates unchanged; outer cleanup allowance unchanged'}
    return timing, limits
