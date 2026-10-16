"""Read saved ARM records only; emit small evaluation evidence, never controls."""
import hashlib
import json
import math
from pathlib import Path


def audit(root):
    root = Path(root)
    files = ('student_record.json', 'eval_only/referee_truth.jsonl',
             'eval_only/cooperative-dynamics.jsonl')
    hashes = {}
    for name in files:
        h = hashlib.sha256()
        with (root/name).open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
        hashes[name] = dict(sha256=h.hexdigest(), bytes=(root/name).stat().st_size)
    robots = json.loads((root/files[0]).read_text())['pair']['pair'][0]['robots']
    decisions = {}
    for rid, robot in robots.items():
        events = robot['events']
        rows = [e for e in events if e.get('event') == 'refix_decision']
        decisions[rid] = dict(stops=[dict(seg=e['seg'], own_request=e['own']['request'],
            partner_request=e['partner_request'], refix=e['refix'], sigma=e['sigma'],
            llm=e['llm']) for e in rows],
            relook_result=sum(e.get('event') == 'relook_result' for e in events),
            checkpoint_high_reobserved=sum(e.get('event') == 'checkpoint_high_reobserved' for e in events))
    plans = [e for e in robots['r1']['events'] if e.get('event') == 'synchronized_carry_plan']
    other = [e for e in robots['r2']['events'] if e.get('event') == 'synchronized_carry_plan']
    legs = []
    for p in plans:
        q = next(e for e in other if e['seg'] == p['seg'])
        end = p['sim_s']+.2+p['pulses']*p['period_s']+.1
        legs.append(dict(seg=p['seg'], start_s=p['sim_s'], end_s=end,
            axis='forward' if p['cmd']['forward'] else 'left', planned_m=p['distance_m'],
            nominal_m=p['pulses']*p['calibrated_step_m'], pulses=p['pulses'],
            clock_equal=all(p[k] == q[k] for k in ('sim_s','duration_s','period_s','pulses')),
            mirrored=all(p['cmd'][k] == -q['cmd'][k] for k in p['cmd']),
            truth=[], dynamics=[]))
    for name, key in ((files[1], 'truth'), (files[2], 'dynamics')):
        with (root/name).open() as stream:
            for line in stream:
                row = json.loads(line)
                for leg in legs:
                    if leg['start_s']-1e-8 <= row['t'] <= leg['end_s']+1e-8:
                        leg[key].append(row)
    for leg in legs:
        truth, dynamics = leg.pop('truth'), leg.pop('dynamics')
        beam = [r['items']['beam_1'] for r in truth]
        a,b = beam[0],beam[-1]
        leg.update(truth_n=len(truth), dynamics_n=len(dynamics),
            sampling_max_gap_s=max(b['t']-a['t'] for a,b in zip(truth,truth[1:])),
            delta_xy_m=[b['x']-a['x'],b['y']-a['y']],
            axial_progress_m=abs(b['x']-a['x']) if leg['axis']=='forward' else abs(b['y']-a['y']),
            held_all=all(r['held'] for r in beam),
            both_contacts_all=all(all(r['robots'][rid]['contacts']>0 for rid in ('r1','r2')) for r in dynamics),
            max_tilt_deg=max(r['cargo_tilt_deg'] for r in dynamics),
            min_z_m=min(r['z'] for r in beam))
    return dict(raw=str(root),files=hashes,decisions=decisions,legs=legs)


if __name__ == '__main__':
    import sys
    print(json.dumps(dict(scope='saved evidence only; sampled contact is not a guarantee',
        runs=[audit(p) for p in sys.argv[1:]]),indent=2))
