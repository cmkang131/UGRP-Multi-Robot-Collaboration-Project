"""v6-family registration contract, separate from immutable v5h execution records.

2026-09-29 (manager decision): the v6 registration (PR #259, REGISTERED at
3c26acdd, six dev runs done) is a HISTORICAL record. It pins 72 source hashes
of that commit, so checking it against the current tree broke every later PR
that touched a pinned source. It is now audited only against the blobs of its
registration commit (``verify_v6_historical``), and ``load_config`` refuses
to prepare or run it from the current tree. New v6-family runs register their
own revision and bundle (v6b, v6c) and set ``CURRENT_REVISION``.

2026-09-29 (manager decision A, PR #256): the v6b DRAFT (PR #261, bundle v75,
opt-in ``stationary_bootstrap`` policies) is historical in the same way. It
pinned 73 source hashes of the tree, including the study runner and the
workflow catalog, so the B7 runner merge (bundle v77) could not land without
re-sealing it. Its bytes and the v75 offline replay records stay unchanged;
it is audited only against the blobs of its sealing commit 15793691. There is
no current v6-family draft on main (``CURRENT_REVISION = None``): ``contract``
and ``load_config`` refuse until the next draft (v6c, PR #263) sets its own
revision. A draft should be sealed last, right before registration.
"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

from harness.zone_pair_v6_policy import EXECUTION_BUNDLE_ID, POLICIES, REVISION_POLICIES

ROOT = Path(__file__).resolve().parents[1]
PREREG = ROOT/'experiments/2026-09-28-zone-pair-v6/prereg_v6.json'
PREREG_V6B = ROOT/'experiments/2026-09-28-zone-pair-v6b-boot/prereg_v6b.json'
V5H = ROOT/'experiments/2026-09-27-zone-pair-dev/prereg_v5h.json'
V6_REGISTRATION_COMMIT = '3c26acddec066adcd9164e6d2a6f51c1261c5f66'   # PR #259 REGISTERED conversion
V6B_DRAFT_COMMIT = '15793691b3af136769cdf0b090e722daddf80ab4'         # PR #261 last v6b DRAFT sealing
HISTORICAL_REVISIONS = {'v6': (PREREG, V6_REGISTRATION_COMMIT), 'v6b': (PREREG_V6B, V6B_DRAFT_COMMIT)}
HISTORICAL_STATUS = {'v6': 'REGISTERED', 'v6b': 'DRAFT'}
CURRENT_REVISION = None       # no current v6-family draft on main; v6c (PR #263) sets its own


def contract(revision=None):
    revision = CURRENT_REVISION if revision is None else revision
    if revision is None:
        raise ValueError('no current v6-family draft on main (v6 and v6b are historical; '
                         'the next draft sets CURRENT_REVISION)')
    if revision != CURRENT_REVISION:
        raise ValueError(f'{revision} is historical; audit it with verify_v6_historical')
    from scripts.zone_pair_grasp_contract import SOURCE_PATHS
    from scripts.zone_pair_dev_contract import scene_contract
    paths = (*SOURCE_PATHS,*scene_contract()['source_sha256'],
             'harness/zone_study_integration.py','harness/zone_pair_v6_policy.py','harness/zone_pair_relative.py',
             'harness/zone_pair_global.py','harness/owncam_recovery_v6.py',
             'harness/owncam_observability_v6.py','scripts/zone_pair_v6_contract.py',
             # Final review P3-4: control-path modules outside the v5h receipts.
             'harness/zone_own_sweep.py','harness/pair_owncam_approach.py','harness/owncam_drive.py',
             'scripts/run_m2_pair.py','scripts/study_owncam_pair_beam.py','harness/visual_arm.py',
             'harness/m1_owncam_delivery.py',
             # v6b start bootstrap and its executor hook.
             'harness/owncam_bootstrap_v6b.py','harness/zone_own_executor.py','harness/zone_pair_executor.py')
    paths = tuple(dict.fromkeys(paths))
    from harness.zone_pair_global import SCHEDULED_REOBSERVE
    from harness.zone_own_sweep import SWEEP_REOBSERVE_S
    from harness.zone_pair_align import MAX_LOOKS, MAX_TOTAL_LOOK_S
    from harness import owncam_bootstrap_v6b as boot
    return {'execution_bundle_id':EXECUTION_BUNDLE_ID,'policy_flags':{
        k:vars(POLICIES[k]) for k in REVISION_POLICIES[revision]},
        # Review 3: flag semantics are part of the registration. beam_relative
        # (A) now also removes PF convergence from the align stop conditions.
        'flag_definitions':{
            'posterior_relook':'B: posterior-preserving relook, observation quality receipts, blocked-pan cancel',
            'beam_relative':('A: own-view beam-relative align/close-in and pre-close shape report; separate '
                             'global safety envelope with planned safety looks; during align/pre-close the PF is '
                             'a reference only (no HIGH/convergence stop) while an object-anchored bound '
                             '(entry fix + ready relative view of the static beam) certifies wall/arm clearance'),
            'stationary_bootstrap':('v6b: equal-weight AMCL-default Gaussian prior on the static start_dock rows; '
                                    'no own arm/wheel command before an informative settled fix whose first arm '
                                    'transition the unchanged guard clears (or gate LOW); only camera pans in between, '
                                    'each checked by the unchanged guard at the mean plus a conservative collision-mass bound '
                                    'over all weighted particles (cell-inflated, <= 1 %; particle chance constraint); '
                                    'refused pans stay queued and are rechecked; non-finite reports never complete; '
                                    'completion '
                                    'only at the home pan after settle, with sigma within the guard cap; '
                                    'resample-move on the stationary belief after an accepted view (no dual samples); '
                                    'a rejected view '
                                    'never mutates the PF; 10 s stationary budget per motion job, then '
                                    'STATIONARY_BOOTSTRAP_NO_FIX, and a failed bootstrap never unlocks motion')},
        'bootstrap_constants':{'amcl_initial_std_xy_m':boot.AMCL_INITIAL_STD_XY_M,
                               'amcl_initial_std_yaw_rad':boot.AMCL_INITIAL_STD_YAW_RAD,
                               'pan_risk_bound':boot.PAN_RISK_BOUND,
                               'risk_cell_xy_m':boot.CELL_XY_M,'risk_cell_yaw_rad':boot.CELL_YAW_RAD,
                               'max_boot_frames':boot.BootstrapLocalizer.MAX_BOOT_FRAMES,
                               'move_steps':[list(s) for s in boot.BootstrapLocalizer.MOVE_STEPS],
                               'move_iters':boot.BootstrapLocalizer.MOVE_ITERS,
                               'settle_after_pan_s':boot.SETTLE_AFTER_PAN_S,
                               'fail_reason':boot.FAIL_REASON},
        'reobserve_budgets':{'high_recovery_s':SWEEP_REOBSERVE_S,
                             'scheduled_safety_look':dict(SCHEDULED_REOBSERVE),
                             # Final review: scopes are part of the registration.
                             'scope':('HIGH 복구와 align MAX_LOOKS/MAX_TOTAL_LOOK_S는 approach/reapproach/align '
                                      '진입 및 stored 재파지 시작 전에 초기화한다. v5h/b-only/a+b에 동일하게 적용하며 '
                                      '같은 단계의 재시도·relook 복귀는 초기화하지 않는다. 예정 look은 회당·job 전체 예산이다.'),
                             'align_max_looks':MAX_LOOKS,'align_max_total_look_s':MAX_TOTAL_LOOK_S,
                             'approach_look_fix_confirm_s':SCHEDULED_REOBSERVE['per_look_s']},
        'object_anchor_checks':('전역 envelope와 앵커 상한이 K_SIGMA에서 겹치지 않거나, 빔이 앵커 이후 발행 '
                                '명령의 도달 범위를 벗어나거나, 상대가 상태 채널 규격의 BEAM_MOTION_STATES '
                                '(aligning/하강 포함)를 알리면 앵커를 버린다.'),
        'relative_freshness':('동일 픽셀은 최초 관측 시각을 유지하고 현재 명령·시간 전파 track 상한을 사용한다. '
                              '거절된 입력은 유효 관측 캐시에 넣지 않는다.'),
        'qualification':'offline development; uncalibrated bounds; no physical inheritance',
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}


def verify_v6_historical(path=None, *, root=ROOT, commit=None, revision='v6'):
    """Audit a historical v6-family receipt at its registration commit (read-only).

    ``revision`` selects v6 (REGISTERED at 3c26acdd) or v6b (DRAFT sealed at
    15793691). The registration bytes must equal the committed blob, and every
    pinned source hash must match that commit's blob, not the current tree.
    """
    from scripts.zone_pair_registered_source import committed_blob
    if revision not in HISTORICAL_REVISIONS:
        raise ValueError(f'{revision!r} is not a historical v6-family revision')
    path = HISTORICAL_REVISIONS[revision][0] if path is None else path
    commit = HISTORICAL_REVISIONS[revision][1] if commit is None else commit
    relative = Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    if subprocess.run(['git', 'merge-base', '--is-ancestor', commit, 'HEAD'], cwd=root,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        raise ValueError(f'historical v6 registration commit {commit} is not in this history')
    blob = committed_blob(str(root), commit, relative)
    if Path(path).read_bytes() != blob:
        raise ValueError('historical v6 registration bytes differ from their registration commit')
    p = json.loads(blob)
    if p.get('registration_revision') != revision or p.get('status') != HISTORICAL_STATUS[revision]:
        raise ValueError(f'historical v6 registration is not the {HISTORICAL_STATUS[revision]} {revision} record')
    for source, expected in p['v6_contract']['source_sha256'].items():
        if hashlib.sha256(committed_blob(str(root), commit, source)).hexdigest() != expected:
            raise ValueError(f'historical v6 source hash mismatch at {commit}: {source}')
    return {'commit': commit, 'revision': p['registration_revision'], 'status': p['status'],
            'execution_bundle_id': p['execution_bundle_id'], 'sources': len(p['v6_contract']['source_sha256']),
            'qualification': 'historical provenance audit; not current-source execution admission'}


def load_config(args):
    p=json.loads(args.prereg.read_text());old=json.loads(V5H.read_text())
    revision=p.get('registration_revision')
    if revision is None or revision!=CURRENT_REVISION:
        if revision in HISTORICAL_REVISIONS:
            raise ValueError(f'v6 revision {revision!r} is historical: audit it with verify_v6_historical(); '
                             'it is never prepared or run from the current tree')
        raise ValueError(f'v6-family revision {revision!r} is not the current registration '
                         f'({CURRENT_REVISION!r})')
    # PR #259 DRAFT/REGISTERED admission path, applied to the current revision.
    if p.get('registration_version')!=6 or p.get('execution_source_sha') is not None or p.get('approval') is not None:
        raise ValueError('v6 registration contract changed')
    if p.get('status')=='DRAFT':
        if args.execute:
            raise ValueError('v6 DRAFT is prepare-only: execution source and approval are null')
        if p.get('execution_authorization') is not None or p.get('runnable') is not False:
            raise ValueError('v6 draft contract changed')
    elif p.get('status')=='REGISTERED':
        # 2026-09-28 dev registration: the same v5h admission path (late
        # coordinator envelope + live GitHub comment, verified by the driver).
        draft=p.get('draft_registration')
        if (p.get('runnable') is not True or not isinstance(draft,dict)
                or set(draft)!={'path','commit','sha256','registration_sha256'}):
            raise ValueError('v6 registered contract changed')
        from scripts.zone_pair_authorization import validate_authorization
        validate_authorization(p)
    else:
        raise ValueError('v6 registration status must be DRAFT or REGISTERED')
    for key in ('schema','labels','research_result','environment','inputs','criteria','planned_setdown',
                'limits','safety_coverage','timing','stage_rules','contact_profile_contract'):
        if p.get(key)!=old[key]:
            raise ValueError(f'v6 comparison must preserve v5h {key}')
    if p.get('v6_contract')!=contract(revision):
        raise ValueError('v6 source contract/hash mismatch')
    from scripts.zone_pair_dev_contract import scene_contract
    if p.get('scene_contract')!=scene_contract():
        raise ValueError('v6 scene contract/hash mismatch')
    if ('grasp_contract' in p or p.get('baseline_registration')!={
            'path':str(V5H.relative_to(ROOT)), 'sha256':hashlib.sha256(V5H.read_bytes()).hexdigest()}):
        raise ValueError('v6 must reference the frozen v5h baseline, not inherit its source contract')
    rows=p['runs']
    if len(rows)!=6 or len({r['id'] for r in rows})!=6 or len({r['seed'] for r in rows})!=2:
        raise ValueError('v6 requires two matched seeds times three conditions')
    for seed in {r['seed'] for r in rows}:
        group=[r for r in rows if r['seed']==seed]
        if {r['pair_policy'] for r in group}!=set(REVISION_POLICIES[revision]):
            raise ValueError('v6 ablation missing')
        for key in ('setup_beam_xyyaw','coarse_order_sheet','intervention'):
            if any(r[key]!=group[0][key] for r in group):
                raise ValueError('v6 matched seed configuration differs')
    case=next((r for r in rows if r['id']==args.run_id),None)
    if case is None:
        raise ValueError('run-id is not preregistered')
    if getattr(args,'pair_policy',None) not in (None,case['pair_policy']):
        raise ValueError('pair policy does not match registered case')
    if args.output.exists():
        raise ValueError('output must be new')
    if args.execute:
        import re
        from scripts.zone_pair_authorization import validate_authorization
        from scripts.run_zone_pair_dev import primary_root
        validate_authorization(p, execute=True, expected_source_sha=args.expected_source_sha,
                               run_id=args.run_id)
        if not args.expected_source_sha or not re.fullmatch('[0-9a-f]{40}', args.expected_source_sha):
            raise ValueError('--execute requires full --expected-source-sha')
        if args.lock_owner is None:
            raise ValueError('--execute requires --lock-owner')
        if not args.output.is_absolute() or not args.output.resolve().is_relative_to(primary_root() / 'outputs'):
            raise ValueError('physical raw output must be absolute under primary checkout outputs/')
    return p,copy.deepcopy(case)
