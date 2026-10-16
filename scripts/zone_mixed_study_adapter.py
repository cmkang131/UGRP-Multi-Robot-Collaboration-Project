"""P02 composition entry point, not a registered/standalone trial runner.

The coordinator must pin this adapter and its dependencies in a new workflow
before physical execution. The frozen integration CLI remains pair-only.
"""
import copy
import json

from harness import zone_mixed_jobs as mixed
from harness.zone_mixed_host import MixedOwnCamTeamHost
from harness.zone_mixed_integration import MixedIntegratedTrial
from harness.zone_study_inputs import OrderSheetSource
from scripts import run_zone_study_integration as legacy

HostRobotLink = legacy.HostRobotLink
IntegratedTrial = MixedIntegratedTrial


class StudyTeamHost(legacy.StudyTeamHost, MixedOwnCamTeamHost):
    """Reuse the study clock/provider lifecycle with opt-in mixed host setup.

    Cooperative super() routes legacy StudyTeamHost.__init__ through
    MixedOwnCamTeamHost before the frozen OwnCamTeamHost constructor.
    """


def host_spec(scenario, episode, map_bundle):
    if episode.get('mixed_jobs_profile') is None:
        return legacy.host_spec(scenario, episode, map_bundle)
    from harness.zone_pair_executor import make_plan
    setup = scenario['eval']['setup']
    if (setup['contact_profile'] != 'cargo_noslip_v1' or episode['contact_profile'] != 'cargo_noslip_v1'
            or setup['weld'] != 'off'):
        raise legacy.zi.ContractViolation('study requires cargo_noslip_v1 and weld OFF in scenario and episode')
    mixed.order_bindings(scenario['orders'], setup['placements'])
    sheet = OrderSheetSource(scenario, map_bundle).sheet()
    contract = mixed.mixed_contract(scenario, episode, sheet)
    sheets = copy.deepcopy(episode['pair_order_sheets'])
    static = json.loads((legacy.ROOT / map_bundle['map_file']).read_text())
    for order in sheet['orders']:
        if order['required_robots'] > 1:
            make_plan(static, sheets[order['order_id']], order['destination_zone'])
    spec = {k: copy.deepcopy(episode[k]) for k in
            ('map', 'goal', 'extra_boxes', 'contact_profile', 'job_sim_limit_s')}
    spec.update(seed=episode['layout_seed'], order_sheet=sheet, mixed_jobs=contract,
                pair_policy=contract['constraints']['pair_policy'], pair_order_sheets=sheets,
                team_cargo=copy.deepcopy(episode['team_cargo']),
                pose_priors=copy.deepcopy(episode.get('pose_priors', {})))
    return spec


def placements_match(scenario, host):
    if not host.spec.get('mixed_jobs'):
        return legacy.placements_match(scenario, host)
    record = host.spec['mixed_jobs']
    mixed.validate_contract(record)
    bindings = mixed.order_bindings(host.spec['order_sheet']['orders'], scenario['eval']['setup']['placements'])
    if bindings != record['bindings'] or scenario['eval']['setup']['placements'] != record['setup_placements']:
        raise legacy.zi.ContractViolation('mixed scenario differs from host contract')
    rows = [{'item_id': oid, 'kind': o['kind'], 'pose_m': [*o['position_m'][:2], 0.]}
            for oid, o in host.objects.items() if 'position_m' in o]
    mixed.validate_inventory(record, [*rows, *host.spec['team_cargo']])
