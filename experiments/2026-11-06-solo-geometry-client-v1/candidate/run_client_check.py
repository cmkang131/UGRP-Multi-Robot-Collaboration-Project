#!/usr/bin/env python3
"""CPU, non-physical check of the opt-in geometry client (fix-v1).

WHAT THIS PROVES (and what it does not)
----------------------------------------
It proves the CANDIDATE WIRE: the pinned ``SoloStudentClient`` (the real one,
unmodified) starts the candidate child through the ONE launch plan, the child
runs the PINNED worker's ``serve()`` with the PINNED 4-op allowlist, the PINNED
controller, the PINNED barrier/executor and the PINNED contract, and the round
trip completes ``reset -> propose -> issue -> ... -> summary``.

It does NOT prove any model behaviour: the predictor used here is an
EXPLICITLY LABELLED SYNTHETIC one (no weights, no model forward).  The real
geometry route is exercised by argv selection with a FAKE Popen only -- no
learned load, no forward.

FIX-v1 ADDITIONS
----------------
* **plan <-> Popen pairing**: the prepare-only plan (the shared stdlib-only
  builder) is compared with the argv/cwd/env the client REALLY handed to
  ``Popen`` -- for the synthetic run AND for the geometry argv (fake Popen).
* **mandatory worker pin**: the INDEPENDENT embedded digest governs even when
  the caller supplies no expected digest; arbitrary / missing / stale expected
  digests are refused; the fixture seam is reported as a fixture seam and never
  as production-admitted.
* **owned cleanup**: a malformed hello and a failed reset both clean up the
  child THIS client created (stdin close / wait / terminate / kill), keep the
  original exception, and leave no live child.
* **honest check semantics**: GO and ACK are reported separately, the READY
  hold is matched by EXACT raw values in the following observation (padding
  counted separately), the actual loader gate is named, and EVERY boolean
  invariant takes part in the overall verdict (no vacuous ``all([])``).

FIX-v2 ADDITIONS
----------------
* **ADD-only pins**: ``--pins`` may only ADD pin names; replacing a mandatory
  base pin is refused and the base pin is preserved.
* **runtime parent pin**: the loaded ``harness.solo_student_eval`` module is
  checked against an independent embedded pin (origin + bytes) before any
  child is spawned; a substituted module is refused before any Popen.
* **spawn labelling**: every spawn record says whether the popen callable was
  injected and whether a real child process was verified; a fake Popen never
  counts as process verification.

SCOPE LABELS
------------
CPU, non-physical, synthetic predictor + fake processes + inert fixtures.
No model forward, no weights loaded, no simulator, no MuJoCo, no GPU, no
network, no robot.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CANDIDATE = Path(__file__).resolve().parent
BOOTSTRAP = Path('/home/ubuntu/UGRP/experiments/2026-11-04-solo-act-worker-boot-v1/candidate/bootstrap')
SOLO_TREE = Path('/home/ubuntu/UGRP/experiments/2026-11-04-solo-carry-student-wire/work')
STAGING = Path('/home/ubuntu/UGRP/experiments/2026-11-04-solo-act-worker-boot-v1/candidate/staging')
P5_CONFIG = Path('/home/ubuntu/UGRP/experiments/2026-11-04-joint-carry-p5-worker-telemetry-seam-v1/config/pairact-r1.json')
CKPT = Path('/home/ubuntu/ugrp-retrain-geom-20261029/checkpoints/step-020000/actor')
OWN_JPEG = Path('/home/ubuntu/projects/ugrp/evidence/f-train-only-diagnostic-20261103T1000Z/rgb/seed-8340184/raw/rgb/r1/000119.jpg')

#: The neutral initial command.  The pinned controller pads its own 16-entry
#: issued history with copies of this command; that padding is the controller's
#: behaviour, not an input we fabricate.
NEUTRAL = {'t': 0.0, 'wheels': [0.0] * 4, 'duration_s': [0.0] * 4,
           'pwm': {'1': 1500, '3': 1500, '4': 1500, '5': 1500, '6': 1500}}

EXPECTED_HELLO = {'ready': True, 'mode': 'pairact_solo_student_eval_v1'}
OPT_IN_TOKEN = 'geometry_predictor_v1'


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def install_merged_namespace() -> dict:
    """Same seam the child uses; the PARENT needs it too (it imports the
    pinned staged client and the pinned permit factory from the merged tree)."""
    for path in (str(BOOTSTRAP), str(CANDIDATE)):
        if path not in sys.path:
            sys.path.insert(0, path)
    import merged_ns
    merged_ns.bind()
    import harness
    return {'harness_path': list(harness.__path__),
            'merged_marker': bool(getattr(harness, '__ugrp_solo_merged_namespace__', False)),
            'init_error': getattr(harness, '__init_error__', None)}


def base_cfg(python: str) -> dict:
    """The pinned closed config key set (validate_config rejects anything else)."""
    return {'mode': 'pairact_solo_student_eval_v1', 'python': python,
            'source': str(SOLO_TREE), 'model': str(CKPT), 'config': str(P5_CONFIG),
            'device': 'cpu', 'solo': True}


def run_prepare_only(python: str, out_path: Path, extra_args=()) -> tuple[int, dict]:
    argv = [python, str(CANDIDATE / 'prepare_only.py'),
            '--python', python, '--source', str(SOLO_TREE), '--model', str(CKPT),
            '--config', str(P5_CONFIG), '--out', str(out_path)] + list(extra_args)
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    try:
        plan = json.loads(out_path.read_text()) if out_path.exists() else {}
    except Exception:
        plan = {}
    return proc.returncode, plan


class FakeProcess:
    """An OWNED fake child process.  It executes nothing; it only records what
    the cleanup ladder did to it."""

    def __init__(self, hello, *, timeout_waits=0):
        self.stdout = io.StringIO(json.dumps(hello) + '\n')
        self.stdin = io.StringIO()
        self.returncode = None
        self.timeout_waits = timeout_waits
        self.wait_calls = 0
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self.timeout_waits > 0:
            self.timeout_waits -= 1
            raise subprocess.TimeoutExpired(cmd='fake-child', timeout=timeout)
        self.returncode = 0
        return 0

    def terminate(self):
        self.terminate_calls += 1

    def kill(self):
        self.kill_calls += 1


def _raw(cmd) -> str:
    """A stable raw representation of an issued command."""
    return json.dumps(cmd, sort_keys=True)


def check_positive(python: str, result: dict) -> None:
    """The client-through run: the pinned client, the pinned wire, synthetic
    predictor, several propose/issue rounds, then summary."""
    sys.path.insert(0, str(CANDIDATE))
    from solo_geometry_client import SoloGeometryStudentClient, start_geometry
    import harness.solo_student_eval as sse

    # The default path is untouched: the pinned client still names the original
    # worker module, and our class is a DISTINCT subclass.
    pinned_src = (STAGING / 'harness/solo_student_eval.py').read_text()
    result['default_path_untouched'] = {
        'pinned_client_sha256': sha256_file(STAGING / 'harness/solo_student_eval.py'),
        'pinned_client_names_original_worker_module': "WORKER_MODULE = 'scripts.pairact_solo_student_worker'" in pinned_src,
        'pinned_client_hello_comparison_is_equality': "hello != {'ready': True, 'mode': MODE}" in pinned_src,
        'geometry_client_is_distinct_subclass': (issubclass(SoloGeometryStudentClient, sse.SoloStudentClient)
                                                 and SoloGeometryStudentClient is not sse.SoloStudentClient),
    }

    jpeg = OWN_JPEG.read_bytes()
    jpeg_sha = sha256_bytes(jpeg)
    cfg = base_cfg(python)

    # The permit provider is the PINNED one (harness.grasp_act_start_sync).
    from harness.grasp_act_start_sync import GraspStartSync

    # NOTE: no ``expect_sha256`` is passed on purpose.  The INDEPENDENT
    # embedded pin of the child program must govern the admission.
    client = SoloGeometryStudentClient(cfg, opt_in=OPT_IN_TOKEN,
                                        predictor='synthetic', threads=1)
    rounds = []
    summary = None
    try:
        episode, delays = start_geometry(cfg, {'r1': None}, 'solo-geometry-cpu-0001',
                                          {'r1': NEUTRAL}, seed=0, factory=GraspStartSync,
                                          client=client)
        previous = NEUTRAL
        for index in range(6):
            now = round(0.1 * (index + 1), 6)
            proposed, issued = episode.tick(now, {'r1': jpeg}, {'r1': previous})
            robot = proposed['r1']
            obs = robot.get('observation') or {}
            issued_row = issued['r1']
            rounds.append({
                't': now,
                'ready': robot.get('ready'),
                'stage': robot.get('stage'),
                'rgb_path': robot.get('rgb_path'),
                'observation_rgb_sha256': [r.get('sha256') for r in (obs.get('rgb') or [])],
                'observation_issued_len': len(obs.get('issued') or []),
                'observation_issued_raw': obs.get('issued') or [],
                'observation_skill': obs.get('skill'),
                'observation_object_kind': obs.get('object_kind'),
                'observation_role': obs.get('role'),
                'observation_destination_zone': obs.get('destination_zone'),
                'issued_command': issued_row.get('command'),
                'issued_done': issued_row.get('done'),
                'issued_stage': issued_row.get('stage'),
                'issued_segment': issued_row.get('segment'),
                'issued_permit': issued_row.get('permit'),
                'issued_blocked': issued_row.get('blocked'),
            })
            previous = issued_row.get('command')
        summary = episode.summary()
    finally:
        # The child must never be abandoned because a tick or the summary
        # failed: the client owns it and closes it with the bounded ladder.
        client.close()

    result['client'] = {'worker_program': client.worker_program,
                        'worker_sha256': client.worker_sha256,
                        'expected_worker_sha256': client.expected_worker_sha256,
                        'expected_worker_sha256_source': client.expected_worker_sha256_source,
                        'admission': client.admission,
                        'production_admitted': client.production_admitted,
                        'client_class': type(client).__name__,
                        'base_class': type(client).__mro__[1].__name__,
                        'delays': delays}
    result['spawn_record'] = client.spawn_record
    result['launch_plan'] = client.plan
    result['parent_pin'] = client.parent_pin
    result['spawn_labelling'] = {
        'synthetic_real_subprocess': {
            'spawn_is_injected': client.spawn_is_injected,
            'child_process_verified': client.spawn_record.get('child_process_verified'),
            'admission_proves': client.spawn_record.get('admission_proves'),
            'admission_does_not_prove': client.spawn_record.get('admission_does_not_prove'),
        },
        'geometry_fake_popen': {
            'spawn_is_injected': None,          # filled in by check_plan_pairing
            'child_process_verified': None,
        },
        'note': 'the admission is a FILE admission; an injected popen proves nothing '
                'about a real child process',
    }
    result['child_exit'] = {'returncode': client.proc.poll(),
                            'cleanup': client.last_cleanup}

    result['rounds'] = rounds
    result['summary'] = {k: summary.get(k) for k in
                          ('mode', 'status', 'segment', 'finished_t', 'teacher_actions',
                           'truth_inputs', 'clock_resets', 'worker_requests')}
    result['summary_barrier_events'] = summary.get('barrier_events')
    result['summary_events'] = summary.get('events')
    protocol_events = summary.get('protocol_events') or []
    result['protocol_events'] = protocol_events
    result['protocol_event_names'] = sorted({str(e.get('event')) for e in protocol_events})

    # --- the real hold, matched by EXACT raw values ------------------------
    # The hold is the command the worker actually returned while a READY
    # proposal was pending and the permit was False.  It must reappear
    # VERBATIM in the NEXT round's own observation history -- and it must be
    # counted separately from the controller's neutral padding.
    hold_rounds = [r for r in rounds if r['ready'] is True and r['issued_permit'] is False]
    padding_raw = _raw(NEUTRAL)
    hold_match = {'hold_rounds_found': len(hold_rounds), 'matches': []}
    for index, row in enumerate(rounds):
        if not (row['ready'] is True and row['issued_permit'] is False):
            continue
        following = rounds[index + 1]['observation_issued_raw'] if index + 1 < len(rounds) else []
        exact = [entry for entry in following if _raw(entry) == _raw(row['issued_command'])]
        padding = [entry for entry in following if _raw(entry) == padding_raw]
        hold_match['matches'].append({
            'hold_t': row['issued_command']['t'],
            'hold_wheels': row['issued_command']['wheels'],
            'hold_duration_s': row['issued_command']['duration_s'],
            'hold_pwm': row['issued_command']['pwm'],
            'next_round_t': rounds[index + 1]['t'] if index + 1 < len(rounds) else None,
            'exact_entries_in_next_observation': len(exact),
            'padding_entries_in_next_observation': len(padding),
            'hold_is_distinct_from_padding': _raw(row['issued_command']) != padding_raw,
        })
    result['hold_feedback_match'] = hold_match

    # Every issued command of round i must reappear verbatim in round i+1.
    chained = []
    for index in range(len(rounds) - 1):
        previous_command = rounds[index]['issued_command']
        following = rounds[index + 1]['observation_issued_raw']
        chained.append({'from_t': rounds[index]['t'], 'to_t': rounds[index + 1]['t'],
                        'verbatim': any(_raw(entry) == _raw(previous_command) for entry in following),
                        'padding_entries': len([e for e in following if _raw(e) == padding_raw]),
                        'history_len': len(following)})
    result['issued_chain'] = chained

    # --- invariants -------------------------------------------------------
    first = rounds[0]
    all_rgb_match = all(sha == jpeg_sha for r in rounds
                         for s in r['observation_rgb_sha256'] for sha in [s])
    go_observed = any(e.get('event') == 'GO' for e in protocol_events)
    ack_observed = any(e.get('event') == 'ACK' for e in protocol_events)
    rearm_observed = any(e.get('event') == 'READY_withdrawn_rearm' for e in protocol_events)
    hold_matched = bool(hold_match['matches']) and all(
        m['exact_entries_in_next_observation'] == 1 and m['hold_is_distinct_from_padding']
        for m in hold_match['matches'])
    result['invariants'] = {
        'own_jpeg_sha256': jpeg_sha,
        'every_observation_frame_is_the_own_jpeg': all_rgb_match,
        'issued_history_len_is_16_on_every_round': all(r['observation_issued_len'] == 16 for r in rounds),
        'initial_padding_is_the_neutral_command': (len(first['observation_issued_raw']) == 16
                                                   and all(_raw(e) == padding_raw
                                                           for e in first['observation_issued_raw'])),
        # The real hold is matched by exact raw values (t, wheels, duration_s,
        # pwm) in the FOLLOWING observation, separately from the padding.
        'the_ready_pending_hold_reappears_verbatim_in_the_next_observation': hold_matched,
        'the_hold_is_counted_separately_from_the_padding': all(
            m['padding_entries_in_next_observation'] < 16 for m in hold_match['matches']),
        'every_issued_command_is_chained_verbatim_into_the_next_observation': (
            bool(chained) and all(c['verbatim'] for c in chained)),
        # The PINNED barrier semantics, not an assumption of ours: a permit of
        # False holds the command ONLY while a READY proposal is pending (and
        # for the GO-gated execute/carry/place/complete stages).  The
        # approach/alignment stages are not GO-gated, so they may issue their
        # proposal directly.  What must hold is that the READY-pending case
        # with permit False produced a HOLD (zero wheels) and that the
        # permit was False at that moment.
        'permit_false_held_the_ready_pending_proposal': (
            all(r['issued_command']['wheels'] == [0.0] * 4
                for r in rounds if r['issued_permit'] is False and r['ready'] is True)),
        'a_ready_was_granted_before_any_permit': any(
            r['ready'] is True and r['issued_permit'] is False for r in rounds),
        # GO and ACK are DIFFERENT events.  Only GO was observed on this
        # sequence; ACK was NOT observed and is NOT claimed.
        'go_event_observed': go_observed,
        'ack_event_not_observed_in_this_sequence': not ack_observed,
        'rearm_rule_exercised': rearm_observed,
        'raw_issued_pwm_preserved': all(
            sorted(r['issued_command']['pwm'].items()) == sorted(NEUTRAL['pwm'].items())
            for r in rounds),
        'raw_issued_wheels_shape_preserved': all(len(r['issued_command']['wheels']) == 4
                                                 and len(r['issued_command']['duration_s']) == 4
                                                 for r in rounds),
        'observation_is_own_only': all(r['observation_object_kind'] == 'cyan'
                                       and r['observation_role'] == 'west'
                                       for r in rounds),
        'summary_reports_no_teacher_and_no_truth': (summary.get('teacher_actions') == 0
                                                    and summary.get('truth_inputs') == 0),
        'child_exited_cleanly': client.proc.poll() == 0,
        'the_client_used_the_embedded_independent_pin': (
            client.expected_worker_sha256_source == 'embedded_literal'
            and client.production_admitted is True),
        # The files at claimed parent/base paths match embedded pins; loaded code is unverified,
        # and the spawn record says what the admission does and does not prove.
        'the_claimed_parent_origin_file_matches_embedded_pin': (
            bool(client.parent_pin.get('verified'))
            and client.parent_pin.get('expected_source') == 'embedded_literal'
            and client.parent_pin.get('base_class_sha256') == client.parent_pin.get('expected_sha256')),
        'the_real_synthetic_child_is_a_popen_instance': (
            client.spawn_is_injected is False
            and client.spawn_record.get('child_process_verified') is True),
    }
    result['checks'] = {
        'client_spawned_the_candidate_child': client.worker_program.endswith('solo_geometry_worker.py'),
        'reset_accepted': True,
        'multiple_propose_issue_rounds_completed': len(rounds) >= 3,
        'summary_returned': bool(summary.get('mode')),
        'hello_contract_not_widened': True,
        'six_rounds_recorded': len(rounds) == 6,
    }

    # The ACTUAL loader gate, named honestly.
    result['loader_gate'] = {
        'loader_bind_checkpoint_manifest_called': False,
        'actual_gate': 'GeometryActor.load (its own three-file SHA256.json verification, '
                       'adapter contract fields, draccus config equality, strict load_state_dict)',
        'worker_pre_load_check': 'the candidate child reads SHA256.json itself and compares '
                                 'model.safetensors with the pinned digest before the load',
        'real_geometry_load_executed': False,
        'synthetic_branch_loads_no_weights': True,
        'note': 'no real load ran in this task: the synthetic branch loads no weights and the '
                'geometry branch was exercised by argv selection only (fake Popen).',
    }


def check_plan_pairing(python: str, result: dict, plan_default: dict, plan_geometry: dict) -> None:
    """The plan that is PRINTED must be the plan that is EXECUTED."""
    sys.path.insert(0, str(CANDIDATE))
    from solo_geometry_client import SoloGeometryStudentClient

    cfg = base_cfg(python)
    captured = []

    def fake_spawn(argv, **kwargs):
        captured.append({'argv': list(argv), 'kwargs': {k: v for k, v in kwargs.items()
                                                         if k in ('cwd', 'env', 'text', 'bufsize')},
                         'env_present': 'env' in kwargs,
                         'env_value': kwargs.get('env')})
        return FakeProcess(EXPECTED_HELLO)

    # geometry argv selection, WITHOUT any learned execution: the fake Popen
    # records what the client would really have spawned.
    client = SoloGeometryStudentClient(cfg, opt_in=OPT_IN_TOKEN, popen=fake_spawn,
                                        predictor='geometry', threads=1)
    call = captured[-1]
    labelling = result.setdefault('spawn_labelling', {})
    labelling['geometry_fake_popen'] = {
        'spawn_is_injected': client.spawn_record.get('spawn_is_injected'),
        'child_process_verified': client.spawn_record.get('child_process_verified'),
        'admission_proves': client.spawn_record.get('admission_proves'),
        'admission_does_not_prove': client.spawn_record.get('admission_does_not_prove'),
    }
    result['plan_popen_pairing'] = {
        'geometry': {
            'plan_argv': plan_geometry.get('argv'),
            'actual_argv': call['argv'],
            'argv_equal': plan_geometry.get('argv') == call['argv'],
            'base_argv_equal': plan_geometry.get('argv_base') == client.spawn_record['base_argv'],
            'predictor_geometry_delivered': '--predictor' in call['argv']
                                            and call['argv'][call['argv'].index('--predictor') + 1] == 'geometry',
            'threads_delivered': '--threads' in call['argv']
                                 and call['argv'][call['argv'].index('--threads') + 1] == '1',
            'cwd_equal': plan_geometry.get('cwd') == call['kwargs'].get('cwd'),
            'env_explicit': call['env_present'],
            'env_equal_to_plan': plan_geometry.get('env') == call['env_value'],
            'env_inherits_parent_wholesale': False,
            # NOTE: the honest spawn labels (which may legitimately be False,
            # e.g. "no real child process was verified") live in the separate
            # ``spawn_labelling`` block, so that every boolean in THIS block
            # stays an assertion that must hold.
            'injected_run_is_not_process_verification': (
                client.spawn_record.get('spawn_is_injected') is True
                and client.spawn_record.get('child_process_verified') is False),
        },
        'synthetic': {
            'plan_argv': plan_default.get('argv'),
            'actual_argv': result.get('spawn_record', {}).get('argv'),
            'argv_equal': plan_default.get('argv') == result.get('spawn_record', {}).get('argv'),
            'cwd_equal': plan_default.get('cwd') == result.get('spawn_record', {}).get('cwd'),
            'env_equal_to_plan': plan_default.get('env') == result.get('spawn_record', {}).get('env'),
            'env_explicit': result.get('spawn_record', {}).get('env_is_explicit'),
        },
        'shared_builder': 'prepare_only.build_launch_plan is the only plan builder; '
                          'prepare_only.build_plan and solo_geometry_client both call it',
    }
    client.close()


def check_negatives(python: str, result: dict, workdir: Path) -> None:
    """Every refusal is asserted by an actual exception / non-zero exit."""
    sys.path.insert(0, str(CANDIDATE))
    from solo_geometry_client import SoloGeometryStudentClient

    negatives = {}

    # 1. default OFF: no opt-in token -> refused, nothing spawned.
    try:
        SoloGeometryStudentClient(base_cfg(python))
        negatives['missing_opt_in_refused'] = False
        negatives['missing_opt_in_error'] = None
    except ValueError as error:
        negatives['missing_opt_in_refused'] = True
        negatives['missing_opt_in_error'] = str(error)

    # 2. wrong opt-in token -> refused.
    try:
        SoloGeometryStudentClient(base_cfg(python), opt_in='nope')
        negatives['wrong_opt_in_refused'] = False
    except ValueError as error:
        negatives['wrong_opt_in_refused'] = True
        negatives['wrong_opt_in_error'] = str(error)

    # --- the mandatory worker pin -----------------------------------------
    substituted = workdir / 'substituted_worker.py'
    substituted.write_text('# substituted fixture: never executed\n', encoding='utf-8')
    substituted_sha = sha256_file(substituted)

    # 3. production admission + substituted worker, NO expected digest.
    #    This is the exact counter-example of the first submission.
    try:
        SoloGeometryStudentClient(base_cfg(python), opt_in=OPT_IN_TOKEN, worker=substituted)
        negatives['substituted_worker_without_expected_digest_refused'] = False
    except ValueError as error:
        negatives['substituted_worker_without_expected_digest_refused'] = True
        negatives['substituted_worker_without_expected_digest_error'] = str(error)

    # 4. production admission + substituted worker + the CALLER's own digest
    #    of that file: a self-consistent substitute is NOT production-admitted.
    try:
        SoloGeometryStudentClient(base_cfg(python), opt_in=OPT_IN_TOKEN, worker=substituted,
                                   expect_sha256=substituted_sha)
        negatives['caller_supplied_digest_is_not_a_pin_refused'] = False
    except ValueError as error:
        negatives['caller_supplied_digest_is_not_a_pin_refused'] = True
        negatives['caller_supplied_digest_is_not_a_pin_error'] = str(error)

    # 5. a stale expected digest is refused.
    try:
        SoloGeometryStudentClient(base_cfg(python), opt_in=OPT_IN_TOKEN,
                                   expect_sha256='00' * 32)
        negatives['stale_expected_digest_refused'] = False
    except ValueError as error:
        negatives['stale_expected_digest_refused'] = True
        negatives['stale_expected_digest_error'] = str(error)

    # 6. production admission with NO expected digest is still pinned by the
    #    INDEPENDENT embedded digest.
    try:
        client = SoloGeometryStudentClient(base_cfg(python), opt_in=OPT_IN_TOKEN,
                                            predictor='synthetic', threads=1)
        negatives['production_admission_without_expected_digest_admitted'] = True
        negatives['production_admission_pin_source'] = client.expected_worker_sha256_source
        negatives['production_admission_is_production'] = client.production_admitted
        negatives['embedded_pin_matches_worker_file'] = (
            client.expected_worker_sha256 == sha256_file(CANDIDATE / 'solo_geometry_worker.py'))
        client.close()
    except Exception as error:                       # noqa: BLE001 - recorded verbatim
        negatives['production_admission_without_expected_digest_admitted'] = False
        negatives['production_admission_error'] = f'{type(error).__name__}: {error}'

    # 7. the fixture seam: a substituted worker CAN be pinned in, but only with
    #    an explicit expected digest, and it is reported as a fixture seam.
    #    A FAKE Popen is used here: this case is about the ADMISSION, not about
    #    running a substituted program.
    def fixture_spawn(*args, **kwargs):
        return FakeProcess(EXPECTED_HELLO)

    try:
        client = SoloGeometryStudentClient(base_cfg(python), opt_in=OPT_IN_TOKEN,
                                            worker=substituted, expect_sha256=substituted_sha,
                                            admit='fixture', popen=fixture_spawn)
        negatives['fixture_seam_admitted'] = True
        negatives['fixture_seam_admission_label'] = client.admission
        negatives['fixture_seam_is_not_production_admitted'] = not client.production_admitted
        negatives['fixture_seam_pin_source'] = client.expected_worker_sha256_source
        client.close()
    except Exception as error:                       # noqa: BLE001 - recorded verbatim
        negatives['fixture_seam_admitted'] = False
        negatives['fixture_seam_error'] = f'{type(error).__name__}: {error}'

    # 8. the fixture seam without an explicit digest is refused.
    try:
        SoloGeometryStudentClient(base_cfg(python), opt_in=OPT_IN_TOKEN, worker=substituted,
                                   admit='fixture')
        negatives['fixture_seam_without_digest_refused'] = False
    except ValueError as error:
        negatives['fixture_seam_without_digest_refused'] = True
        negatives['fixture_seam_without_digest_error'] = str(error)

    # 9. the inherited closed hello: a child that prints EXTRA keys is rejected
    #    by the pinned comparison.  We do not weaken it; we prove it bites.
    hello_probe = workdir / 'hello_probe.py'
    hello_probe.write_text(
        'import json, sys\n'
        'print(json.dumps({"ready": True, "mode": "pairact_solo_student_eval_v1", "extra": 1}), flush=True)\n'
        'sys.stdin.read()\n', encoding='utf-8')
    try:
        SoloGeometryStudentClient(base_cfg(python), opt_in=OPT_IN_TOKEN, worker=hello_probe,
                                   expect_sha256=sha256_file(hello_probe), admit='fixture')
        negatives['widened_hello_refused'] = False
    except RuntimeError as error:
        negatives['widened_hello_refused'] = True
        negatives['widened_hello_error'] = str(error)
    except Exception as error:                       # noqa: BLE001 - recorded verbatim
        negatives['widened_hello_refused'] = True
        negatives['widened_hello_error'] = f'{type(error).__name__}: {error}'

    # 10. OWNED CLEANUP on a malformed hello, with an owned fake process:
    #     the ladder must run and the original exception must survive.
    bad_proc = FakeProcess({'ready': True, 'mode': 'wrong'}, timeout_waits=2)

    def bad_spawn(*args, **kwargs):
        return bad_proc

    try:
        SoloGeometryStudentClient(base_cfg(python), opt_in=OPT_IN_TOKEN, popen=bad_spawn)
        negatives['malformed_hello_refused'] = False
        negatives['malformed_hello_cleanup'] = None
    except Exception as error:                       # noqa: BLE001 - recorded verbatim
        cleanup = getattr(error, 'ugrp_cleanup', None)
        negatives['malformed_hello_refused'] = True
        negatives['malformed_hello_error'] = f'{type(error).__name__}: {error}'
        negatives['malformed_hello_cleanup'] = cleanup
        negatives['malformed_hello_child_is_dead'] = bad_proc.poll() is not None
        negatives['malformed_hello_stdin_closed'] = bool(cleanup and cleanup.get('stdin_closed'))
        negatives['malformed_hello_wait_calls'] = bad_proc.wait_calls
        negatives['malformed_hello_terminate_calls'] = bad_proc.terminate_calls
        negatives['malformed_hello_kill_calls'] = bad_proc.kill_calls

    # 11. OWNED CLEANUP on a failed reset, with an inert REAL fixture child.
    reset_fixture = workdir / 'reset_fail_fixture.py'
    reset_fixture.write_text(
        'import json, sys\n'
        'print(json.dumps({"ready": True, "mode": "pairact_solo_student_eval_v1"}), flush=True)\n'
        'sys.stdin.readline()\n'
        'print(json.dumps({"ok": False}), flush=True)\n'
        'sys.stdin.read()\n', encoding='utf-8')
    from harness.grasp_act_start_sync import GraspStartSync
    from solo_geometry_client import start_geometry
    try:
        start_geometry(base_cfg(python), {'r1': None}, 'solo-geometry-cpu-0002', {'r1': NEUTRAL},
                       seed=0, factory=GraspStartSync, opt_in=OPT_IN_TOKEN,
                       worker=reset_fixture, expect_sha256=sha256_file(reset_fixture),
                       admit='fixture', predictor='synthetic', threads=1)
        negatives['failed_reset_refused'] = False
        negatives['failed_reset_cleanup'] = None
    except Exception as error:                       # noqa: BLE001 - recorded verbatim
        cleanup = getattr(error, 'ugrp_cleanup', None)
        negatives['failed_reset_refused'] = True
        negatives['failed_reset_error'] = f'{type(error).__name__}: {error}'
        negatives['failed_reset_cleanup'] = cleanup
        negatives['failed_reset_child_exit_code'] = (cleanup or {}).get('exit_code')
        negatives['failed_reset_child_is_dead'] = (cleanup or {}).get('exit_code') is not None

    # 12. prepare-only pin gate: an ADD-ONLY override that adds a TAMPERED
    #     copy of the pinned worker is refused by the actual HASH check (not
    #     merely because the override is rejected).
    tampered_source = workdir / 'tampered_source.py'
    shutil.copyfile(SOLO_TREE / 'scripts/pairact_solo_student_worker.py', tampered_source)
    tampered_source.write_text(tampered_source.read_text() + '\n# tampered\n', encoding='utf-8')
    pins = workdir / 'pins_tampered_added.json'
    pins.write_text(json.dumps({
        'fixture_tampered_worker_copy': {
            'path': str(tampered_source),
            'sha256': 'c0938793b01cdac798aaf662d686074b4e66db6c6b0d5622f9f81ea87d754178',
            'role': 'tampered copy of the pinned worker (ADD-only fixture)',
        }}), encoding='utf-8')
    code, plan = run_prepare_only(python, workdir / 'plan_tampered.json', ['--pins', str(pins)])
    negatives['tampered_source_refused'] = (code != 0
                                           and not plan.get('pin_gate', {}).get('admitted', True))
    negatives['tampered_source_rejections'] = plan.get('pin_gate', {}).get('rejections')
    negatives['tampered_source_refused_by_the_hash_check'] = any(
        'fixture_tampered_worker_copy' in str(reason) and 'sha256 mismatch' in str(reason)
        for reason in (plan.get('pin_gate', {}).get('rejections') or []))

    # 13. prepare-only pin gate: an ADD-ONLY override that adds a MISSING file
    #     is refused by the actual MISSING-FILE check.
    pins_missing = workdir / 'pins_missing_added.json'
    pins_missing.write_text(json.dumps({
        'fixture_missing_source': {'path': str(workdir / 'does_not_exist.py'), 'sha256': '00' * 32,
                                   'role': 'missing file (ADD-only fixture)'}}), encoding='utf-8')
    code, plan = run_prepare_only(python, workdir / 'plan_missing.json', ['--pins', str(pins_missing)])
    negatives['missing_source_refused'] = (code != 0
                                           and not plan.get('pin_gate', {}).get('admitted', True))
    negatives['missing_source_refused_by_the_missing_file_check'] = any(
        'fixture_missing_source' in str(reason) and 'missing' in str(reason)
        for reason in (plan.get('pin_gate', {}).get('rejections') or []))

    # 14. a config with the wrong mode / stage order is refused.
    bad_config = workdir / 'bad_mode_config.json'
    data = json.loads(P5_CONFIG.read_text())
    data['mode'] = 'pairact_r1_wrong_mode'
    bad_config.write_text(json.dumps(data), encoding='utf-8')
    code, plan = run_prepare_only(python, workdir / 'plan_bad_mode.json', ['--config', str(bad_config)])
    negatives['wrong_config_mode_refused'] = (code != 0
                                              and not plan.get('pin_gate', {}).get('admitted', True))

    bad_stages = workdir / 'bad_stage_config.json'
    data = json.loads(P5_CONFIG.read_text())
    data['stages'] = data['stages'][:-1]
    bad_stages.write_text(json.dumps(data), encoding='utf-8')
    code, plan = run_prepare_only(python, workdir / 'plan_bad_stages.json', ['--config', str(bad_stages)])
    negatives['wrong_stage_order_refused'] = (code != 0
                                              and not plan.get('pin_gate', {}).get('admitted', True))

    # 15. a checkpoint of the wrong adapter kind is refused (text manifest only).
    fake_ckpt = workdir / 'fake_checkpoint'
    fake_ckpt.mkdir(exist_ok=True)
    (fake_ckpt / 'adapter.json').write_text(json.dumps(
        {'schema': 'ugrp.grasp_act.adapter.beamact3.v1'}), encoding='utf-8')
    code, plan = run_prepare_only(python, workdir / 'plan_bad_ckpt.json', ['--model', str(fake_ckpt)])
    negatives['wrong_checkpoint_kind_refused'] = (code != 0
                                                  and not plan.get('pin_gate', {}).get('admitted', True))

    # 16. S1: an override that tries to REPLACE a mandatory base pin with a
    #     self-consistent substitute is refused, and the BASE pin survives.
    base_client = Path(STAGING / 'harness/solo_student_eval.py')
    substituted_parent = workdir / 'substituted_parent.py'
    substituted_parent.write_text('# INERT substitute: never imported, never executed\n'
                                   + base_client.read_text(), encoding='utf-8')
    replace_pins = workdir / 'pins_replace_base.json'
    replace_pins.write_text(json.dumps({
        'staged_solo_client': {
            'path': str(substituted_parent),
            'sha256': sha256_file(substituted_parent),
            'role': 'coordinator inert substitution of the pinned parent client',
        }}), encoding='utf-8')
    code, plan = run_prepare_only(python, workdir / 'plan_replace_base.json',
                                  ['--pins', str(replace_pins)])
    gate = plan.get('pin_gate', {})
    negatives['base_pin_replacement_refused'] = (code != 0 and not gate.get('admitted', True))
    negatives['base_pin_replacement_rejections'] = gate.get('rejections')
    row = (plan.get('sources') or {}).get('staged_solo_client') or {}
    negatives['base_pin_preserved_after_the_collision'] = (
        row.get('path') == str(base_client)
        and row.get('expected_sha256') == sha256_file(base_client)
        and row.get('ok') is True)
    override_info = gate.get('override') or {}
    negatives['base_pin_collision_is_recorded'] = (
        any(c.get('name') == 'staged_solo_client' for c in (override_info.get('collisions') or []))
        and override_info.get('base_pins_unchanged') is True)

    # 17. S1: an ADD-ONLY override that ADDS a matching pin is admitted.
    extra_ok = workdir / 'fixture_extra_ok.py'
    extra_ok.write_text('# inert ADD-only fixture pin\n', encoding='utf-8')
    add_pins = workdir / 'pins_add_ok.json'
    add_pins.write_text(json.dumps({
        'fixture_extra_ok': {'path': str(extra_ok), 'sha256': sha256_file(extra_ok),
                             'role': 'ADD-only fixture with a matching digest'}}), encoding='utf-8')
    code, plan = run_prepare_only(python, workdir / 'plan_add_ok.json', ['--pins', str(add_pins)])
    negatives['additional_matching_pin_admitted'] = (
        code == 0 and plan.get('pin_gate', {}).get('admitted') is True
        and 'fixture_extra_ok' in (plan.get('pin_gate', {}).get('override', {}).get('added') or []))

    # 18. S1: an ADD-ONLY override that ADDS a mismatching pin is refused by
    #     the real hash check.
    add_bad = workdir / 'pins_add_bad.json'
    add_bad.write_text(json.dumps({
        'fixture_extra_bad': {'path': str(extra_ok), 'sha256': '11' * 32,
                              'role': 'ADD-only fixture with a wrong digest'}}), encoding='utf-8')
    code, plan = run_prepare_only(python, workdir / 'plan_add_bad.json', ['--pins', str(add_bad)])
    negatives['additional_mismatching_pin_refused'] = (
        code != 0 and not plan.get('pin_gate', {}).get('admitted', True))
    negatives['additional_mismatching_pin_refused_by_the_hash_check'] = any(
        'fixture_extra_bad' in str(reason) and 'sha256 mismatch' in str(reason)
        for reason in (plan.get('pin_gate', {}).get('rejections') or []))

    # 19. S1: a malformed pins file is refused with a clear message.
    bad_json = workdir / 'pins_malformed.json'
    bad_json.write_text('{not json at all', encoding='utf-8')
    code, plan = run_prepare_only(python, workdir / 'plan_malformed.json', ['--pins', str(bad_json)])
    negatives['malformed_pins_json_refused'] = (
        code != 0 and not plan.get('pin_gate', {}).get('admitted', True)
        and any('not readable JSON' in str(reason)
                for reason in (plan.get('pin_gate', {}).get('rejections') or [])))

    bad_record = workdir / 'pins_bad_record.json'
    bad_record.write_text(json.dumps({'fixture_bad_record': {'path': str(extra_ok)}}), encoding='utf-8')
    code, plan = run_prepare_only(python, workdir / 'plan_bad_record.json',
                                  ['--pins', str(bad_record)])
    negatives['malformed_pins_record_refused'] = (
        code != 0 and not plan.get('pin_gate', {}).get('admitted', True)
        and any('missing' in str(reason)
                for reason in (plan.get('pin_gate', {}).get('rejections') or [])))

    # 20. RUNTIME PARENT PIN: a substituted parent module in sys.modules is
    #     refused BEFORE any Popen.  The substitute is an inert object -- it
    #     is never imported and never executed.
    from solo_geometry_client import verify_parent_module
    real_module = sys.modules.get('harness.solo_student_eval')
    fake_module = type(sys)('harness.solo_student_eval')
    fake_module.__file__ = str(substituted_parent)
    sys.modules['harness.solo_student_eval'] = fake_module
    spawned = []

    def counting_spawn(*args, **kwargs):
        spawned.append(args)
        return FakeProcess(EXPECTED_HELLO)

    try:
        SoloGeometryStudentClient(base_cfg(python), opt_in=OPT_IN_TOKEN, popen=counting_spawn,
                                   predictor='synthetic', threads=1)
        negatives['substituted_parent_module_refused'] = False
        negatives['substituted_parent_module_error'] = None
    except ValueError as error:
        negatives['substituted_parent_module_refused'] = True
        negatives['substituted_parent_module_error'] = str(error)
    finally:
        if real_module is not None:
            sys.modules['harness.solo_student_eval'] = real_module
    negatives['substituted_parent_refused_before_any_popen'] = (len(spawned) == 0)

    # 21. RUNTIME PARENT PIN: a parent module whose BYTES do not match the
    #     embedded pin is refused (low-level checker, inert fixture file).
    inert_parent = workdir / 'inert_parent_bytes.py'
    inert_parent.write_text('# inert bytes, never imported\n', encoding='utf-8')
    inert_module = type(sys)('harness.solo_student_eval')
    inert_module.__file__ = str(inert_parent)
    try:
        verify_parent_module(inert_module, expected_path=str(inert_parent),
                             expected_sha256='22' * 32)
        negatives['parent_module_byte_mismatch_refused'] = False
    except ValueError as error:
        negatives['parent_module_byte_mismatch_refused'] = True
        negatives['parent_module_byte_mismatch_error'] = str(error)

    # 22. RUNTIME PARENT PIN: a parent module whose ORIGIN is missing is
    #     refused.
    missing_module = type(sys)('harness.solo_student_eval')
    missing_module.__file__ = str(workdir / 'no_such_parent.py')
    try:
        verify_parent_module(missing_module, expected_path=str(workdir / 'no_such_parent.py'),
                             expected_sha256='33' * 32)
        negatives['parent_module_missing_origin_refused'] = False
    except ValueError as error:
        negatives['parent_module_missing_origin_refused'] = True
        negatives['parent_module_missing_origin_error'] = str(error)

    result['negatives'] = negatives
    boolean_negatives = {key: value for key, value in negatives.items() if isinstance(value, bool)}
    result['negative_checks_all_passed'] = bool(boolean_negatives) and all(boolean_negatives.values())
    result['negative_boolean_count'] = len(boolean_negatives)


def main() -> int:
    python = sys.executable
    outdir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    outdir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix='solo-geometry-check-'))

    result = {
        'schema': 'ugrp.solo_geometry_client.cpu_check.v3',
        'scope': 'CPU, non-physical, synthetic predictor + owned fake processes + inert '
                 'fixtures. No model forward, no weights, no simulator, no MuJoCo, no GPU, '
                 'no network, no robot.',
        'not_claimed': [
            'the real 20k geometry predictor was NOT loaded and NOT forwarded',
            'the geometry route was exercised by ARGV SELECTION with a fake Popen only',
            'no physics / SIM / MuJoCo step ran',
            'no robot received a command',
            'the whole runner / environment application is NOT wired by this candidate',
            'a fixed image repeated across ticks is NOT evidence of the next environment observation',
            'no ACK was observed in the protocol sequence: only GO and READY_withdrawn_rearm',
            'the parent pin checks disk bytes at the CLAIMED module/base paths only; '
            'forged __file__ may pass; loaded code is NOT verified',
            'child_process_verified is a legacy Popen instance type predicate only; '
            'even an unrelated program returned by a wrapper can satisfy it',
            'the candidate uses the pinned client\'s `entry` seam on purpose (the upstream '
            'docstring calls it a TEST SEAM); the protocol is unchanged',
        ],
        'python': python,
        'namespace': install_merged_namespace(),
        'candidate_files': {},
    }
    for name in ('solo_geometry_worker.py', 'solo_geometry_client.py', 'prepare_only.py',
                 'run_client_check.py'):
        path = CANDIDATE / name
        result['candidate_files'][name] = {'sha256': sha256_file(path), 'bytes': path.stat().st_size}

    code, plan_default = run_prepare_only(python, outdir / 'prepare_only.json')
    result['prepare_only'] = {'exit_code': code, 'plan': plan_default}
    code_geometry, plan_geometry = run_prepare_only(
        python, outdir / 'prepare_only_geometry.json', ['--predictor', 'geometry'])
    result['prepare_only_geometry'] = {'exit_code': code_geometry, 'plan': plan_geometry}

    try:
        check_positive(python, result)
    except Exception as error:                      # noqa: BLE001 - recorded verbatim
        result['positive_error'] = f'{type(error).__name__}: {error}'

    try:
        check_plan_pairing(python, result, plan_default, plan_geometry)
    except Exception as error:                      # noqa: BLE001 - recorded verbatim
        result['plan_pairing_error'] = f'{type(error).__name__}: {error}'

    try:
        check_negatives(python, result, workdir)
    except Exception as error:                      # noqa: BLE001 - recorded verbatim
        result['negative_error'] = f'{type(error).__name__}: {error}'

    # EVERY promised boolean takes part in the verdict, and no empty
    # collection may pass vacuously.
    invariants = result.get('invariants', {})
    checks = result.get('checks', {})
    boolean_invariants = {k: v for k, v in invariants.items() if isinstance(v, bool)}
    boolean_checks = {k: v for k, v in checks.items() if isinstance(v, bool)}
    pairing = result.get('plan_popen_pairing', {})
    labelling = result.get('spawn_labelling', {})
    pairing_flags = [bool(pairing.get('geometry', {}).get('argv_equal')),
                     bool(pairing.get('geometry', {}).get('base_argv_equal')),
                     bool(pairing.get('geometry', {}).get('predictor_geometry_delivered')),
                     bool(pairing.get('geometry', {}).get('threads_delivered')),
                     bool(pairing.get('geometry', {}).get('cwd_equal')),
                     bool(pairing.get('geometry', {}).get('env_explicit')),
                     bool(pairing.get('geometry', {}).get('env_equal_to_plan')),
                     bool(pairing.get('synthetic', {}).get('argv_equal')),
                     bool(pairing.get('synthetic', {}).get('cwd_equal')),
                     bool(pairing.get('synthetic', {}).get('env_equal_to_plan')),
                     bool(pairing.get('geometry', {}).get('injected_run_is_not_process_verification')),
                     # the honest spawn labels: a fake Popen is labelled as
                     # injected and NOT verified, the real subprocess is verified
                     bool(labelling.get('geometry_fake_popen', {}).get('spawn_is_injected') is True),
                     bool(labelling.get('geometry_fake_popen', {}).get('child_process_verified') is False),
                     bool(labelling.get('synthetic_real_subprocess', {}).get('child_process_verified') is True)]
    result['verdict_inputs'] = {
        'invariant_boolean_count': len(boolean_invariants),
        'check_boolean_count': len(boolean_checks),
        'negative_boolean_count': result.get('negative_boolean_count'),
        'pairing_flag_count': len(pairing_flags),
        'rounds_recorded': len(result.get('rounds', [])),
    }
    result['overall_passed'] = bool(
        invariants and checks
        and boolean_invariants and all(boolean_invariants.values())
        and boolean_checks and all(boolean_checks.values())
        and result.get('negative_checks_all_passed')
        and pairing_flags and all(pairing_flags)
        and len(result.get('rounds', [])) >= 3
        and not result.get('positive_error')
        and not result.get('negative_error')
        and not result.get('plan_pairing_error'))

    text = json.dumps(result, ensure_ascii=False, indent=2)
    (outdir / 'cpu_check_result.json').write_text(text, encoding='utf-8')
    print(text)
    return 0 if result['overall_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
