"""v349 strong-rule body skills; same own-input filters, zero model requests.

Nav2-style replan/recovery ordering is adapted to the existing bounded skills.
Maps and pose estimates are never cleared or replaced by evaluator state.
Gemma remains a message writer; this module only consumes protocol admission.
"""
import copy
import hashlib
import math

from harness.e2e_body_skills import SkillsBodyGate
from harness.e2e_body_controller import stop_like

BACKEND = 'code_v1'
PARAMS = dict(recovery='replan_scan_backup_opposite_detour', repeat_limit=3,
              terminal_recheck_s=.6, progress_m=.03, progress_heading_deg=5., history=10,
              own_motion_only=True, provider_calls=0)
WAIT = ('hold_and_reobserve', 'wait_and_reobserve', 'hold_and_wait')


def compose(bundle, enabled=False):
    if not enabled:
        return ()
    if bundle['execution_bundle_id'] != 'e2e18-v344':
        raise ValueError('CODE_BODY_REQUIRES_BOUNDED_V344_PARENT')
    bundle.update(body_code_parent='e2e18-v344', body_code_parameters=copy.deepcopy(PARAMS),
                  execution_bundle_id='e2e18-v349', workflow_version='7.242.0', schema='ugrp.e2e_ownmap_live.v349')
    bundle['e2e_options']['body_backend'] = BACKEND
    return ('harness/e2e_body_code.py', 'configs/simulation_workflows.d/e2e18_v349.json')


def parent_for_validation(bundle):
    if (bundle.get('body_code_parent') != 'e2e18-v344' or bundle.get('body_code_parameters') != PARAMS
            or bundle['e2e_options'].get('body_backend') != BACKEND or bundle['execution_bundle_id'] != 'e2e18-v349'):
        raise ValueError('REGISTERED_CODE_BODY_REQUIRED')
    parent = copy.deepcopy(bundle)
    parent['execution_bundle_id'] = parent.pop('body_code_parent')
    parent.pop('body_code_parameters'); parent['e2e_options']['body_backend'] = 'liquid_d1'
    return parent


def no_progress(row):
    if row.get('status') != 'ok' or row.get('outcome') == 'interrupted':
        return True
    if row.get('own_translation_m', 0) >= PARAMS['progress_m'] or row.get('own_rotation_deg', 0) >= PARAMS['progress_heading_deg']:
        return False
    delta = row.get('distance_change_m')
    return ('visual_after' in row and row.get('visual_before') == row['visual_after']
            and (delta is None or delta >= -.01))


class CodeBodyGate(SkillsBodyGate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.replan_counts = {}
        self.terminal_attempts = {}

    def annotate_outcomes(self, rid, facts):
        pose = facts['own_pose_estimate']
        for row in self.memory[rid].history:
            if 'pose_before' in row and 'own_translation_m' not in row:
                old = row['pose_before']
                row['own_translation_m'] = round(math.dist(old[:2], pose[:2]), 4)
                row['own_rotation_deg'] = round(abs(math.degrees(math.atan2(math.sin(pose[2]-old[2]), math.cos(pose[2]-old[2])))), 2)
        facts.update(self.memory[rid].context(self.last_now))

    def context(self, rid, now):
        facts = super().context(rid, now)
        self.annotate_outcomes(rid, facts)
        goal = self.robots[rid].goal
        n = getattr(goal.explorer, 'navigator', None)
        facts['own_navigation'] = dict(finished=bool(getattr(n, 'finished', False)),
            failed=bool(getattr(n, 'failed', False)), phase=getattr(n, 'phase', None),
            goal_stage=getattr(goal, 'stage', None), goal_done=bool(getattr(goal, 'done', False)))
        d = getattr(self.tr, 'dialogue', None)
        if d is not None and hasattr(d, 'trial'):
            facts['partner_recent_messages'] = [dict(id=e.get('message_id'), sender=e.get('sender'),
                text=(e.get('body') or {}).get('text', ''), delivered_at_sim_s=e.get('delivered_at_sim_s'),
                age_s=None if e.get('delivered_at_sim_s') is None else now-e['delivered_at_sim_s'])
                for e in d.trial.channel.inbox(rid, now_sim_s=now)]
        return facts

    def terminal_mapping(self, rid, now):
        if self.tr.state != 'mapping' or rid not in ('r1', 'r2'):
            return False
        robot = self.robots[rid]; goal = robot.goal
        n = getattr(goal.explorer, 'navigator', None)
        clearance = getattr(self.tr, 'arm_clearance', None)
        return (n is not None and n.finished and not n.failed and not n.phase
                and not getattr(n, 'sweep_pending', None) and not getattr(n, 'view_active', False)
                and getattr(goal, 'stage', None) == 'explore' and not goal.done and robot.packet is None
                and not (clearance and clearance.busy(rid))
                and not any(r == rid for _, r, _ in self.tr.queue)
                and now >= self.tr.robot_queue_until.get(rid, 0.))

    def restart_frontiers(self, rid, now):
        """Expire target suppression only; retain observed obstacles and own pose."""
        explorer = self.robots[rid].goal.explorer; n = explorer.navigator
        expired = dict(blacklist=len(n.blacklist), visited=len(n.visited))
        n.blacklist.clear(); n.visited.clear(); n.reset_action()
        n.target = n.frontier = n.requested_goal = None
        n.path = []; n.locked = n.finished = n.static_mode = False
        n.goal_started = n.progress_time = n.progress_xy = None
        n.best_distance = math.inf; n.next_frontier_ns = 0
        n.initial_scan_used = False
        explorer.plan = None; explorer.last_plan_t = -math.inf
        self.replan_counts[rid] = self.replan_counts.get(rid, 0)+1
        self.tr.event(now, 'body_terminal_frontier_replan', robot_id=rid, expired_suppression=expired,
                      count=self.replan_counts[rid], map_and_pose_preserved=True)

    def recovery(self, rid, now, facts):
        primary = super().recovery(rid, now, facts)
        if primary is not None:
            return primary
        # The original three strategies are not a terminal mission state.
        # Continue a bounded RoundRobin over safe opposite-side viewpoints,
        # preferring an untried side. Do not reset the failure/history evidence.
        from harness import e2e_body_semantics as sem
        names = self.detours(facts)
        tried = facts['recovery_strategies_tried']
        names.sort(key=lambda k: ('recover_'+k in tried,
            sum(h.get('choice') == 'recover_'+k for h in facts['recent_decisions'])))
        for name in names:
            side = name.removeprefix('detour_')
            script = [(i*.2, sem.pulse('strafe_'+side+'_small')) for i in range(4)]
            if all(self.motion_safe(c, facts) and self.map_safe(rid, c) for _, c in script):
                return 'recover_'+name, (f'Try the next safe {side} viewpoint after the wide-view/standoff/pan sequence; '
                    'replan from own RGB without declaring success.', ('script', 1., script))
        return None

    def menu_direct(self, rid, now, proposal):
        menu, plabel, facts = super().menu_direct(rid, now, proposal)
        if self.terminal_mapping(rid, now):
            menu.pop('follow_own_path', None)
            menu['replan_frontier'] = ('Retry frontier planning on the next own RGB; expire only old target suppression, '
                'retain measured map/pose; if still exhausted, choose a bounded scan/backup/detour.', ('script', .6, []))
            facts['terminal_mapping_recovery'] = True
            # Keep the common maximum of six candidates.
            if len(menu) > 6:
                redundant = next((k for k in reversed(menu) if k.startswith('scan_')), None)
                if redundant is not None:
                    menu.pop(redundant)
        return menu, plabel, facts

    def prepare_decision(self, rid, now, kind, menu, proposal, facts):
        facts = copy.deepcopy(facts)
        self.annotate_outcomes(rid, facts)
        history = facts['recent_decisions']
        failed = [h.get('choice') for h in history if no_progress(h)]
        facts['same_stage_failure_memory'] = [
            f"t={h['t']:.2f} {h.get('choice')}: {h.get('outcome', 'next observation')}; "
            f"view {h.get('visual_before')} -> {h.get('visual_after')}; target change {h.get('distance_change_m')} m; "
            f"own translation {h.get('own_translation_m')} m. No confirmed progress."
            for h in history if no_progress(h)]
        # Remove repeated no-progress alternatives; a required safety hold is
        # never removed just to force movement.
        repeated = (history[-1].get('choice') if len(history) >= 3
                    and len({h.get('choice') for h in history[-3:]}) == 1
                    and all(no_progress(h) for h in history[-3:]) else None)
        safe = {k: v for k, v in menu.items() if not isinstance(v[1], tuple)
                or all(self.motion_safe(c, facts) and self.map_safe(rid, c) for _, c in v[1][2])}
        must_wait = facts['partner_stop'] or 'slipping' in facts['own_grip'] or (facts['holding_command'] and not facts['go_ack_complete'])
        if repeated in safe and len(safe) > 1 and not must_wait:
            safe.pop(repeated)
        if not safe:
            safe = {k: v for k, v in menu.items() if k in WAIT}
        if not safe:
            raise ValueError('CODE_BODY_REQUIRES_SAFE_WAIT_OR_SKILL')
        wait = next((k for k in WAIT if k in safe), None)
        reason = 'bounded_current_goal'
        choice = None
        if must_wait:
            choice, reason = wait, 'own_grip_or_partner_or_agreement_hold'
        elif facts.get('terminal_mapping_recovery'):
            key = self.memory[rid].key
            state = self.terminal_attempts.setdefault(rid, dict(key=key, tried=[]))
            if state['key'] != key:
                state.update(key=key, tried=[])
            scans = [k for k in safe if k.startswith('scan_')]
            ordered = ['replan_frontier', *scans, 'back_off_and_replan', *self.detours(facts)]
            choice = next((k for k in ordered if k in safe and k not in state['tried']), None)
            if choice is None:
                state['tried'].clear()
                choice = next((k for k in ordered if k in safe), wait)
            reason = 'terminal_frontier_bounded_recovery'
        elif facts.get('strategy_switch_required'):
            choice = next((k for k in safe if k.startswith('recover_')), wait)
            reason = 'ordered_no_progress_recovery'
        elif kind in ('grasp_close', 'grasp_lift', 'set_down', 'camera_view', 'relook_pose', 'carry'):
            if kind in ('grasp_lift', 'carry') and (not facts['go_ack_complete'] or self.hazard(facts)):
                choice = wait
            else:
                choice = next((k for k, v in safe.items() if v[1] == 'execute'), wait)
            reason = 'admitted_phase_skill'
        else:
            blocked = self.hazard(facts) or facts.get('blocked_persistently') or facts['left_right_loop']
            if self.tr.state == 'align' and facts['visual_category'] in ('clipped', 'too_close'):
                choice = next((k for k in ('back_off_and_replan', 'recover_wide_view') if k in safe), None)
                reason = 'widen_clipped_own_view'
            if (choice is None and self.tr.state == 'align' and facts['visual_category'] == 'not_visible'
                    and facts['own_map']['standoff'] is None):
                choice = next((k for k in safe if k.startswith('scan_') and k not in failed[-2:]), None)
                reason = 'search_last_seen_direction'
            if choice is None and not blocked and proposal in safe and proposal not in failed[-2:] and proposal not in WAIT:
                choice = proposal
            if choice is None:
                # Prefer the side away from a seen peer; after an unsuccessful
                # side use the opposite. Back up before repeating both sides.
                ordered = (['back_off_and_replan'] if facts['left_right_loop'] else [])
                ordered += self.detours(facts) + ['back_off_and_replan']
                if not blocked:
                    ordered = [k for k in safe if k.startswith(('scan_', 're_observe', 'move_camera'))] + ordered
                choice = next((k for k in ordered if k in safe and k not in failed[-4:]), None)
                if choice is None:
                    choice = next((k for k in safe if k not in WAIT), wait)
                reason = 'blocked_or_failed_skill_recovery'
        if choice is None:
            choice, reason = wait, 'no_progress_skill_available'
        if choice is None:
            raise ValueError('NO_SAFE_CODE_CHOICE')
        facts.update(code_proposal=choice, code_rule=reason, removed_repeated_choice=repeated,
                     decision_backend=BACKEND, selection_policy='strong rules after shared safety filtering; no provider')
        return safe, choice, facts

    @staticmethod
    def detours(facts):
        side = facts['peer_in_own_rgb'].get('direction')
        away = 'right' if side == 'left' else 'left'
        other = 'left' if away == 'right' else 'right'
        return ['detour_'+away, 'detour_'+other]

    def query_decision(self, rid, kind, state, candidates, menu, proposal, facts):
        jpeg = self.image(rid)
        return dict(status='ok', choice=proposal, model_choice=None, provider_called=False, tier=BACKEND, model=None,
                    wall_s=0., latency_s=0., usage=dict(cost=0., input_tokens=0, output_tokens=0),
                    image_sha256=hashlib.sha256(jpeg).hexdigest() if jpeg else None,
                    selection=dict(rule=facts['code_rule'], backend=BACKEND))

    def decide(self, rid, now, kind, menu, proposal_label=None, facts=None):
        choice, ready = super().decide(rid, now, kind, menu, proposal_label, facts)
        pending = self.memory[rid].pending
        if pending is not None:
            pending['pose_before'] = list(self.robots[rid].goal.explorer.local_pose)
        if self.rows[-1]['facts'].get('terminal_mapping_recovery') and choice is not None:
            self.terminal_attempts[rid]['tried'].append(choice)
            if choice == 'replan_frontier':
                self.restart_frontiers(rid, now)
        return choice, ready

    def _robot(self, rid, now, moves):
        # Upstream hold is normally not a decision trigger. Terminal mapping is
        # the bounded exception, only while this gate owns locomotion.
        if not moves and rid not in self.units and rid not in self.pending and self.terminal_mapping(rid, now):
            menu, proposal, facts = self.menu_direct(rid, now, [])
            choice, ready = self.decide(rid, now, 'motion', menu, proposal, facts)
            if choice is not None:
                self.pending[rid] = dict(ready_at=ready, label=choice, executor=menu[choice][1])
        return super()._robot(rid, now, moves)

    def summary(self):
        result = super().summary()
        result.update(body_backend=BACKEND, decisions=len(self.rows), calls=0, provider_calls=0,
                      latency_median_s=None, latency_max_s=None, sim_hold_total_s=0.,
                      cost_usd=0., reported_cost_usd=0., cost_known_calls=0, cost_unknown_calls=0,
                      terminal_frontier_replans=self.replan_counts)
        return result
