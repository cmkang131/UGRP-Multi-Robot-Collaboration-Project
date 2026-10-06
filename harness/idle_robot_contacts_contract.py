"""2026-10-06 user decision: freeze is S2 solo exploratory DEV only.

This guard belongs to execution-bundle admission, not PR #407's preserved
standalone physics diagnostics. Missing/off stays byte-neutral. No GT inputs.
"""
import re

OPTION = 'freeze_v1'


def validate(bundle):
    option = bundle.get('options', {}).get('idle_robot_contacts', 'off')
    if option == 'off':
        return option
    if option != OPTION:
        raise ValueError('IDLE_CONTACTS_UNKNOWN_OPTION')
    identity = re.fullmatch(r'zone-s2-realism-v(\d+)', bundle.get('execution_bundle_id', ''))
    task = bundle.get('task', {})
    rid = task.get('robot_id')
    # Later explicit user instruction authorizes one fresh-seed S2 DEV probe
    # recorded before execution. This is not a research preregistration waiver.
    dev_probe_registration = (identity is not None and int(identity[1]) >= 119
        and bundle.get('preregistered_run') is True
        and bundle.get('registration_kind') == 's2-dev-probe'
        and bundle.get('stage_probe') == 'pick'
        and ((bundle.get('user_authorization') == '2026-10-06-s1042-site-check'
              and bundle['options'].get('site_check') == 'real_floor_v1')
             or (int(identity[1]) >= 120
                 and bundle.get('user_authorization') == '2026-10-06-grasp-reference-probe'
                 and bundle['options'].get('hold_check') == 'inhand_rgb_v1'
                 and bundle['options'].get('site_check') == 'off')))
    required = dict(scenario='S2', transport='solo', cargo='cyan', admission='dev-pilot',
                    cohort_role='FUNCTIONAL_DEV', active_robot_ids=[rid])
    dev_full_registration = (identity is not None and int(identity[1]) >= 121
        and bundle.get('preregistered_run') is True
        and bundle.get('registration_kind') == 's2-dev-full'
        and bundle.get('stage_probe') == 'place'
        and bundle.get('user_authorization') == '2026-10-07-s2-full-dev-light'
        and bundle['options'].get('dev_grasp_policy') == 'log_only_v1'
        and bundle['options'].get('hold_check') == 'inhand_rgb_v1'
        and bundle['options'].get('site_check') == 'off')
    allowed = (identity is not None and int(identity[1]) >= 118
        and bundle.get('schema') == 'ugrp.s2_realism_bundle.v'+identity[1]
        and bundle.get('check') == 's2-realism-dev'
        and all(bundle.get(k) == v for k,v in required.items())
        and rid in ('r1','r2','r3')
        and set(task) == {'robot_id','pickup_slot','destination','passage_id','seed'}
        and bundle.get('research_result') is False
        and bundle.get('confirmation_sample') is False
        and (bundle.get('preregistered_run') is False or dev_probe_registration or dev_full_registration)
        and bundle.get('dev_light') is True
        and bundle['options'].get('drive_profile') == 'masterpi_drive_friction_v7'
        and bundle['options'].get('roller_collision', 'mesh') == 'mesh')
    if not allowed:
        raise ValueError('IDLE_CONTACTS_S2_SOLO_EXPLORATORY_DEV_ONLY: no S3, pair, research, or preregistered run')
    return option


def policy():
    return dict(option=OPTION,decision_date='2026-10-06',scope='S2 solo exploratory DEV only',
        forbidden=['S3','pair_transport','research','preregistered_run'],
        default='off',pool_results=False,comparison_metrics=['wall_per_sim'],
        evidence_pr=407,evidence_sha='2d3ab0591ce5e3619a2ff735a9d9893b1199c1c2',
        equivalence='mesh+freeze 9/10: solo and bump pass; pair-beam fails; not mission success',
        caveat='sleeping static/internal contacts are absent from readouts; no S2 full-transport equivalence claim')
