"""Opt-in, finite two-party GO handshake. Inputs are own software state/RGB decisions.

The fixed safety wire is identical in all four arms. It never carries prose,
poses, contacts or another robot's image. Dialogue remains in the study channel.
This in-process barrier is not a distributed consensus or grasp-success proof.
"""
import copy
import math

PAIR = ('r1', 'r2')
MODE = 'mutual_go_v1'
WINDOW_S = 10.
HANDSHAKE_S = 2 * WINDOW_S  # one fresh-response window for GO, one for ACK
MONITOR_S = 2.
SIGNAL_DELAY_S = .1
CHOICES = ('go', 'ack_go', 'held', 'grip_lost', 'unknown')


class Handshake:
    def __init__(self):
        self.claims, self.own, self.signals = {}, {}, []
        self.decisions, self.permits = [], []
        self.failure = None

    def claim(self, rid, call_id):
        if rid not in PAIR or not call_id or rid in self.claims or self.failure:
            return False
        self.claims[rid] = call_id
        return True

    def open(self, rid, epoch, now):
        if rid not in self.claims or self.failure:
            return False
        old = self.own.get(rid)
        if old and epoch <= old['epoch']:
            return False
        if type(epoch) is not int or epoch < 0 or not math.isfinite(now):
            raise ValueError('invalid own carry epoch/clock')
        self.own[rid] = dict(epoch=epoch, opened=now, go=None, ack=None,
                             last_response_at=None, committed=False)
        return True

    def _peer_go(self, rid, now):
        own = self.own.get(rid)
        return next((s for s in reversed(self.signals) if s['sender'] != rid and s['state'] == 'GO'
                     and own and s['epoch'] == own['epoch'] and s['at'] + SIGNAL_DELAY_S <= now), None)

    def view(self, rid, now):
        own = self.own.get(rid)
        peer = self._peer_go(rid, now)
        return dict(phase='aborted' if self.failure else 'unclaimed' if rid not in self.claims
                    else 'align_grasp' if own is None else 'carry' if own['committed'] else 'wait_go',
                    epoch=None if own is None else own['epoch'],
                    own_go_sent=bool(own and own['go']),
                    own_ack_sent=bool(own and own['ack']),
                    peer_signal='ABORT' if self.failure else 'GO' if peer else 'WAIT',
                    peer_go_ref=peer['ref'] if peer else None)

    def abort(self, rid, now, reason):
        if self.failure is None:
            self.failure = reason
            self.signals.append(dict(sender=rid, state='GRIP_LOST' if reason == 'OWN_RGB_GRIP_LOST'
                                     else 'ABORT', epoch=self.own.get(rid, {}).get('epoch'), at=now, ref=None))

    def decide(self, rid, action, *, call_id, requested_at, now, frame_t, frame_sha256, seen):
        """Only a released, validated response to its captured request may vote."""
        own = self.own.get(rid)
        choice = action['choice']
        valid_time = all(math.isfinite(t) for t in (requested_at, now, frame_t))
        fresh = valid_time and frame_t <= requested_at <= now and now-frame_t < WINDOW_S
        valid = (not self.failure and own is not None and fresh
                 and own['opened'] <= requested_at and action['epoch'] == own['epoch'] == seen['epoch']
                 and isinstance(frame_sha256, str) and len(frame_sha256) == 64)
        if valid:
            valid = now < (own['last_response_at']+WINDOW_S if own['committed'] else own['opened']+HANDSHAKE_S)
        reason = 'STALE_OR_CLOSED_PAIR_WINDOW'
        if valid and choice == 'go':
            valid = not own['committed'] and own['go'] is None
            if valid:
                own['go'] = call_id
                self.signals.append(dict(sender=rid, state='GO', epoch=own['epoch'], at=now, ref=call_id))
        elif valid and choice == 'ack_go':
            peer = self._peer_go(rid, requested_at)
            valid = (not own['committed'] and own['go'] is not None and own['ack'] is None
                     and peer is not None and action['peer_go_ref'] == seen['peer_go_ref'] == peer['ref'])
            if valid:
                own['ack'] = call_id
        elif valid and choice == 'held':
            valid = own['committed']
        elif valid and choice == 'grip_lost':
            self.abort(rid, now, 'OWN_RGB_GRIP_LOST')
        elif valid and choice == 'unknown':
            if own['committed']:
                self.abort(rid, now, 'OWN_RGB_GRIP_UNKNOWN')
        if valid and choice in ('go', 'ack_go', 'held'):
            own['last_response_at'] = now
        row = dict(robot_id=rid, call_id=call_id, action=copy.deepcopy(action), at=now,
                   requested_at=requested_at, frame_t=frame_t, frame_sha256=frame_sha256,
                   accepted=bool(valid), reason=None if valid else reason)
        self.decisions.append(row)
        return row

    def tick(self, now):
        if self.failure:
            return False
        for rid, own in self.own.items():
            until = own['last_response_at']+WINDOW_S if own['committed'] else own['opened']+HANDSHAKE_S
            if now >= until:
                self.abort(rid, now, 'PAIR_VISUAL_LEASE_EXPIRED' if own['committed'] else 'PAIR_GO_TIMEOUT')
                return False
        if set(self.claims) != set(PAIR) or set(self.own) != set(PAIR):
            return False
        rows = list(self.own.values())
        if (len({r['epoch'] for r in rows}) != 1 or not all(r['go'] and r['ack'] for r in rows)
                or any(now-r['last_response_at'] >= WINDOW_S for r in rows)):
            return False
        if not all(r['committed'] for r in rows):
            for row in rows:
                row['committed'] = True
            self.permits.append(dict(at=now, epoch=rows[0]['epoch'],
                claim_calls=copy.deepcopy(self.claims), go_calls={r:v['go'] for r,v in self.own.items()},
                ack_calls={r:v['ack'] for r,v in self.own.items()}))
        return True

    def allowed(self, rid, epoch):
        row = self.own.get(rid)
        return bool(not self.failure and row and row['epoch'] == epoch and row['committed'])

    def record(self):
        return copy.deepcopy(dict(mode=MODE, research_result=False, visual_detector='LLM own RGB judgement; unvalidated',
            claims=self.claims, signals=self.signals, decisions=self.decisions, permits=self.permits,
            failure=self.failure, physical_success=None))
