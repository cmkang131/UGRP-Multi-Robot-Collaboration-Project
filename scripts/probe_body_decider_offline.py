"""Offline check (Mac only, no simulation): saved own-RGB scenes -> the same
semantic state + candidate builder as body_controller=jev_v1 -> Jev / optional paid d1 via the Mac relay.

Validity rule is fixed in code before any answer is seen (see valid_set()).
Keys are read from the Mac Keychain into memory; never printed or stored.
"""
import argparse
import base64
import json
import statistics
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from harness import e2e_body_semantics as sem
from harness.body_decider_upstream import body, parse, LIQUID_URL
from harness.e2e_body_controller import BodyGate, INSTRUCTIONS, Client
from harness.jev_decider_eval import JEV_URL, JEV_MODEL
from harness.model_http import post

ROOT = Path(__file__).resolve().parents[1]
SEV = {'within': 0, 'slightly': 1, 'far': 2, 'unknown': 3}


class Dialogue:
    def __init__(self, complete):
        self.approved = True
        self.claims = {'r1', 'r2'}
        self.key = ['order-5', 'h', 1, 0] if complete is not None else None
        self.complete = complete

    def view(self, rid, now):
        return dict(transport_admitted=bool(self.complete))

    def allowed(self, key, now):
        return bool(self.complete)


def gate_for(scene):
    servo = {int(k): v for k, v in (scene['servo'] or {}).items()}
    robot = SimpleNamespace(beam_observation=scene['beam_observation'], servo=servo,
                            frame=SimpleNamespace(jpeg=base64.b64decode(scene['jpeg_b64'])),
                            goal=SimpleNamespace(explorer=SimpleNamespace(local_pose=scene['pose'])), packet=None)
    r1 = SimpleNamespace(packet=True if scene['t'] >= 66 else None)
    tr = SimpleNamespace(state=scene['phase'], robots={scene['rid']: robot}, queue=[], approach={}, dialogue=Dialogue(
        True if scene['phase'] == 'carry' else None), _carry=lambda now: False)
    profiles = json.loads((ROOT / 'configs/s2_v133_full_template.json').read_text())['pulse_calibration']['profiles']
    g = BodyGate(tr, {scene['rid']: robot}, None, profiles=profiles)
    approach=scene.get('carrier_approach') or {}
    tr.approach[scene['rid']]={k:approach[v] for k,v in [('station','station_own_m'),('grip','grip_own_m')] if v in approach}
    if approach.get('own_beam_age_s') is not None:tr.approach[scene['rid']]['last_seen']=scene['t']-approach['own_beam_age_s']
    mem=g.memory[scene['rid']];mem.key=(scene['phase'],0,0);mem.since=scene.get('phase_start',scene['t'])
    for h in scene.get('context_history',[]):
        a=h.get('carrier_approach') or {};distance=a.get('distance_m')
        mem.track.append((h['t'],distance))
    for c in scene['prev']:
        g.history[scene['rid']].append(c)
    for t, p in scene['poses']:
        g.poses[scene['rid']].append((t, p))
    return g


def strip(c):
    return {k: v for k, v in c.items() if k != 't'}


def menu_for(scene):
    g = gate_for(scene)
    rid, t = scene['rid'], scene['t']
    facts, _, _ = g.facts(rid, t)
    if scene['phase'] == 'grasp_lift':
        m = g.batch_menu('grasp_lift')
        if not facts['go_ack_complete']:m.pop('grasp_and_lift')
        return facts, {k: v[0] for k, v in m.items()}, 'grasp_and_lift', g
    if scene['phase'] == 'carry':
        return facts, {'carry_segment': 'carry the beam along the agreed route segment together with partner '
                       '(current GO/ACK complete)', 'hold_and_wait': 'keep holding the beam still and wait'}, 'carry_segment', g
    nxt = [strip(c) for c in scene['next'] if c['kind'] in ('mecanum', 'look')
           and (c['kind'] == 'look' or any(c.get(a) for a in ('forward', 'left', 'turn')))][:1]
    if not nxt and scene['phase'] != 'mapping':
        return None
    menu, plabel, facts = g.menu_direct(rid, t, nxt or [dict(kind='hold')])
    return facts, {k: v[0] for k, v in menu.items()}, plabel, g


def severity(words):
    return [SEV[w.split()[0]] if w.split()[0] in SEV else 0 for k, w in words.items()
            if k in ('grasp_distance', 'grasp_side_offset', 'beam_angle')]


def valid_set(scene, facts, cands, plabel, g):
    """Fixed before querying. Code proposal is valid; other candidates only if
    their code-predicted category change improves without worsening."""
    v = {plabel} if plabel in cands else set()
    if facts.get('strategy_switch_required'):
        return {k for k in cands if k.startswith('recover_')}
    if scene['phase'] == 'mapping':
        if facts['own_progress_last_5s'] == 'not moving':
            v |= {k for k in cands if k.startswith('back') or k.startswith('turn')}
        return v
    if scene['phase']=='grasp_lift' and not facts['go_ack_complete']:
        return {'wait_and_reobserve'}
    if scene['phase'] in ('grasp_lift', 'carry'):
        return v
    if 'fully visible' not in facts['beam']:
        v |= {k for k in cands if k.startswith('pan_camera') or k == 'hold_and_reobserve'}
        return v
    rid = scene['rid']
    _, grip, heading = sem.beam_state(g.robots[rid], scene['t'])
    try:
        before = sem.align_words(sem.align_errors(rid, grip, heading))
    except Exception:
        return v
    b = severity(before)
    if before['grasp_pose'] == 'inside grasp tolerance':
        v.add('hold_and_reobserve')
    for name in ('forward_short', 'back_short', 'turn_left_small', 'turn_right_small'):
        if name not in cands:
            continue
        p = sem.profile_of(name, g.profiles)
        a = severity(sem.predicted(rid, grip, heading, p))
        if all(x <= y for x, y in zip(a, b)) and any(x < y for x, y in zip(a, b)):
            v.add(name)
    return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--scenes', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--relay-url',default='http://127.0.0.1:18434/v1/body/decide')
    ap.add_argument('--backends',default='jev')
    a = ap.parse_args()
    tiers=a.backends.split(',')
    if not set(tiers)<= {'jev','liquid_d1'}:raise ValueError('PAID_BACKENDS_ONLY')
    scenes = json.loads(a.scenes.read_text())
    jobs, cases = [], []
    for i, s in enumerate(scenes):
        m = menu_for(s)
        if m is None:
            continue
        facts, cands, plabel, g = m
        state = sem.state_text(s['rid'], s['phase'], facts)
        valid = sorted(valid_set(s, facts, cands, plabel, g))
        cases.append(dict(scene=i, rid=s['rid'], t=s['t'], phase=s['phase'], frame_sha256=s['frame_sha256'],
                          state=state, candidates=cands, code_proposal=plabel, valid=valid))
        for tier in tiers:
            for r in range(a.reps):
                jobs.append((len(cases) - 1, tier, r, state, cands, s['jpeg_b64'] if tier == 'liquid_d1' else None))

    def run(job):
        ci, tier, r, state, cands, img = job
        client=Client(tier,f'{a.out.stem}-{ci}-{r}',url=a.relay_url)
        res=client.decide(state,cands,base64.b64decode(img) if img else None)
        row=dict(res,case=ci,tier=tier,rep=r)
        return row
    with ThreadPoolExecutor(2) as ex:
        rows = list(ex.map(run, jobs))
    summary = {}
    for tier in tiers:
        rs = [r for r in rows if r['tier'] == tier]
        ok = [r for r in rs if r['status'] == 'ok']
        val = [r for r in ok if r['choice'] in cases[r['case']]['valid']]
        agree = [r for r in ok if r['choice'] == cases[r['case']]['code_proposal']]
        per = {}
        for r in rs:
            ph = cases[r['case']]['phase']
            d = per.setdefault(ph, dict(N=0, valid=0, failed=0))
            d['N'] += 1
            d['failed'] += r['status'] != 'ok'
            d['valid'] += r['status'] == 'ok' and r['choice'] in cases[r['case']]['valid']
        lat = [r.get('latency_s',r.get('wall_s')) for r in ok]
        summary[tier] = dict(N=len(rs), ok=len(ok), valid=len(val), agree_code=len(agree),
                             latency_median_s=statistics.median(lat) if lat else None, by_phase=per,
                             cost_usd=sum(float((r.get('usage') or {}).get('cost') or 0) for r in ok),
                             input_tokens=sum(int((r.get('usage') or {}).get('input_tokens') or 0) for r in ok))
    a.out.write_text(json.dumps(dict(cases=cases, rows=rows, summary=summary), indent=1, ensure_ascii=False))
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
