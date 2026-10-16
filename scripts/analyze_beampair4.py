"""GCP-only pre-edit approach census; saved state is evaluation only."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

from scripts.audit_beampair1 import read, read_bytes, dump, ordered_funnel
from scripts.analyze_beampair1 import candidate_funnels, blockers


def quantiles(values):
    values = sorted(values)
    if not values:
        return None
    def q(p):
        x = (len(values)-1)*p
        i = int(x)
        return values[i] + (values[min(i+1, len(values)-1)]-values[i])*(x-i)
    return dict(N=len(values), min=values[0], p05=q(.05), p50=q(.5),
                p95=q(.95), max=values[-1])


def analyze(root, out, *, pattern='beampair3-gate-*-e645b34b/raw', host='gcp1', planned_n=40):
    if sys.platform != 'linux':
        raise RuntimeError('Analysis must run on GCP Linux')
    import harness
    harness.__path__.append('/home/ugrp/ugrp-sim/src/26f84d0f0ada1c33473c83cca2d3415ce51bd247/harness')
    from harness.grasp_act_visible_world import command_delta
    import mujoco
    out.mkdir(parents=True, exist_ok=False)
    all_runs, failures, approach_rows = [], [], []
    reasons = Counter()
    blocker_counts = Counter()
    for raw in sorted(root.glob(pattern)):
        result = read(raw/'result.json')
        plan = read(raw/'plan.json')
        ev = [json.loads(x) for x in read_bytes(raw/'eval-only.jsonl')[0].splitlines()]
        labels = {r: [json.loads(x) for x in read_bytes(raw/f'teacher-{r}.jsonl')[0].splitlines()]
                  for r in ('r1', 'r2')}
        origin = ev[0]['t']
        success = result['physical_success']
        failed = not success
        candidates = []
        for rid, teacher in result['teachers'].items():
            for e in teacher['search22_log']:
                for c in e.get('candidates', []):
                    reason = c.get('reason') or 'missing_reason'
                    reasons[reason] += 1
                    ds = blockers(c)
                    for d in ds:
                        blocker_counts[(reason, d.get('category'), d.get('id', d.get('object')))] += 1
                    candidates.append(dict(robot=rid, world_t=e['t'], reason=reason,
                        blocked_object=c.get('blocked_object', 'not_recorded'),
                        min_gap_m=c.get('min_gap_m'), blockers=ds))
        model = mujoco.MjModel.from_xml_path(str(raw/'scene.xml')) if failed else None
        state = mujoco.MjData(model) if failed else None
        rows = []
        for rid, ll in labels.items():
            by_t = {round(l['applied_command']['t'], 5): l for l in ll}
            for i, e in enumerate(ev):
                l = by_t.get(round(e['t'], 5))
                if l is None:
                    continue
                nxt = ev[min(i+1, len(ev)-1)]
                pose = e['robots'][rid]['pose']
                actual = [b-a for a, b in zip(pose[:2], nxt['robots'][rid]['pose'][:2])]
                value = l['applied_command']
                dx, dy, da = command_delta(value, .1, mode='search17_fixed_v1')
                co, si = math.cos(pose[2]), math.sin(pose[2])
                cmd = [co*dx-si*dy, si*dx+co*dy]
                norm = math.hypot(*cmd)*math.hypot(*actual)
                cosine = sum(a*b for a, b in zip(cmd, actual))/norm if norm else None
                band = next((m for m in e['visible_measurements'][rid]
                             if m['id'] == 'band_'+plan['roles'][rid]), None)
                target = [b-a for a,b in zip(pose[:2], e['beam']['ends'][plan['roles'][rid]][:2])]
                tn = math.hypot(*target)
                row = dict(seed=plan['seed'], robot=rid, success=success,
                    world_t=e['t'], elapsed_sim_s=e['t']-origin,
                    phase=l['teacher_phase'], assigned_end=plan['roles'][rid],
                    observed_ids=[m['id'] for m in e['visible_measurements'][rid]],
                    observed_band=band['id'] if band else None,
                    observed_distance_m=l.get('local_distance_m'),
                    observed_band_xy=band['xyz'][:2] if band else None,
                    wheels=value['wheels'], duration_s=value['duration_s'],
                    command_world_dx_m=cmd[0], command_world_dy_m=cmd[1],
                    command_yaw_rad=da, actual_world_dx_m=actual[0], actual_world_dy_m=actual[1],
                    command_actual_cosine=cosine,
                    command_toward_band_m=sum(a*b for a,b in zip(cmd,target))/tn,
                    actual_toward_band_m=sum(a*b for a,b in zip(actual,target))/tn,
                    evaluator_distance_m=tn,
                    evaluator_pose=pose,
                    evaluator_peer_distance_m=math.dist(pose[:2],e['robots']['r2' if rid=='r1' else 'r1']['pose'][:2]),
                    evaluator_beam_xy=e['beam']['pose'][:2],
                    evaluator_gripper_contacts=e['contacts'][rid])
                if failed:
                    state.qpos[:] = e['joints']
                    mujoco.mj_forward(model, state)
                    contacts = []
                    for contact in state.contact:
                        a,b = [model.geom(g).name or ('geom_'+str(g)) for g in contact.geom]
                        if a.startswith(rid+'__') != b.startswith(rid+'__'):
                            other = b if a.startswith(rid+'__') else a
                            if other not in ('floor', 'ground') and 'floor' not in other:
                                contacts.append(dict(geoms=[a,b],gap_m=float(contact.dist)))
                    row['eval_saved_qpos_contacts'] = contacts
                rows.append(row)
                if row['phase'] == 'approach':
                    approach_rows.append(row)
        info = dict(seed=plan['seed'], raw=str(raw), success=success, sim_s=result['sim_s'],
            roles=plan['roles'], cap_end=result['cap_end'],
            outcomes={r:t['outcome'] for r,t in result['teachers'].items()},
            phases={r:t['phase'] for r,t in result['teachers'].items()},
            candidates= candidate_funnels(result),
            events={r:t['events'] for r,t in result['teachers'].items()},
            approach_sample_N=sum(r['phase']=='approach' for r in rows),
            source_hashes={str(read_bytes(raw/n)[1]):read_bytes(raw/n)[2]
                for n in ('result.json','plan.json','eval-only.jsonl','teacher-r1.jsonl','teacher-r2.jsonl')})
        anyv=sum(e['visibility'][rid]['visible_probes']>0 for e in ev for rid in plan['roles'])
        meaningful=sum(e['visibility'][rid]['visible_probes']>=5 for e in ev for rid in plan['roles'])
        admitted=sum(any(m['id']=='band_'+plan['roles'][rid] for m in e['visible_measurements'][rid])
                     for e in ev for rid in plan['roles'])
        info['frame_funnel']=ordered_funnel(len(ev)*2,[('any_assigned_probe',anyv),
            ('meaningful_5_probes',meaningful),('measurement_admitted_not_held',admitted)])
        phase_sets=[{e.get('to') for e in t['events']} for t in result['teachers'].values()]
        counts=[sum(bool(v & set(names)) for v in phase_sets) for names in
                [('ready','pick','complete'),('pick','complete'),('complete',)]]
        info['event_funnel']=ordered_funnel(2,list(zip(
            ['own_ready','own_pick_go_ack','own_command_complete'],counts)))
        all_runs.append(info)
        if failed:
            dump(out/f'{plan["seed"]}-timeline.json', rows)
            dump(out/f'{plan["seed"]}-candidates.json', candidates)
            with (out/f'{plan["seed"]}-timeline.csv').open('w') as f:
                writer=csv.DictWriter(f, fieldnames=list(rows[0]))
                writer.writeheader();writer.writerows(rows)
            last6={}
            for rid in labels:
                rs=[r for r in rows if r['robot']==rid and r['elapsed_sim_s']>=result['sim_s']-6-1e-6]
                a,b=rs[0],rs[-1]
                last6[rid]=dict(N=len(rs),range=[a['elapsed_sim_s'],b['elapsed_sim_s']],
                    observed_distance=[a['observed_distance_m'],b['observed_distance_m']],
                    evaluator_displacement_m=math.dist(a['evaluator_pose'][:2],b['evaluator_pose'][:2]),
                    command_delta_sum=[sum(r[k] for r in rs) for k in ('command_world_dx_m','command_world_dy_m')],
                    command_actual_cosine=quantiles([r['command_actual_cosine'] for r in rs if r['command_actual_cosine'] is not None]),
                    observed_ids_counts=dict(Counter(r['observed_band'] for r in rs)),
                    nonzero_wheel_rows=sum(any(r['wheels']) for r in rs),
                    physical_contact_rows=sum(bool(r['eval_saved_qpos_contacts']) for r in rs),
                    physical_contact_names=dict(Counter(x for r in rs for c in r['eval_saved_qpos_contacts'] for x in c['geoms'])),
                    peer_distance_m=quantiles([r['evaluator_peer_distance_m'] for r in rs]),
                    beam_displacement_m=math.dist(a['evaluator_beam_xy'],b['evaluator_beam_xy']))
            failures.append(dict(seed=plan['seed'],last6=last6))
    groups={}
    for name, rs in [('success_runs', [r for r in approach_rows if r['success']]),
                     ('failure_runs', [r for r in approach_rows if not r['success']])]:
        groups[name]=dict(N=len(rs),
            command_actual_cosine=quantiles([r['command_actual_cosine'] for r in rs if r['command_actual_cosine'] is not None]),
            observed_distance_m=quantiles([r['observed_distance_m'] for r in rs if r['observed_distance_m'] is not None]),
            direction_opposed_N=sum((r['command_actual_cosine'] or 0)<0 for r in rs),
            command_away_band_N=sum(r['command_toward_band_m']<0 for r in rs),
            actual_away_band_N=sum(r['actual_toward_band_m']<0 for r in rs))
    dump(out/'rejection-table.json', dict(analysis_host=host, baseline_source_sha='e645b34beb4fa693ab4ddedfe77045ae26b46388',
        source_scope='pre-edit beampair3; no new gate measurement',
        episode_funnel=[dict(gate='submitted',entered=planned_n,cumulative_passed=len(all_runs),rejected=planned_n-len(all_runs)),
            dict(gate='both_align_and_joint_hold',entered=len(all_runs),cumulative_passed=sum(r['success'] for r in all_runs),rejected=sum(not r['success'] for r in all_runs))],
        candidate_first_rejections=dict(reasons),
        blocker_occurrences=[dict(reason=k[0],category=k[1],blocked_object=k[2],N=v) for k,v in blocker_counts.most_common()],
        approach_frame_distributions=groups, failures=failures, runs=all_runs,
        note='blocker occurrences may overlap within a candidate; directions per issued pulse and subsequent saved-state interval; qpos contacts are geometric snapshots only',
        reproduce=f'PYTHONPATH={Path(__file__).resolve().parents[1]} python3 {Path(__file__).resolve()} --root {root} --out NEW_OUTPUT --pattern {pattern!r} --host {host} --planned-n {planned_n}',
        analysis_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print(json.dumps(dict(N=len(all_runs),n=sum(r['success'] for r in all_runs),groups=groups,failures=failures)))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True);p.add_argument('--out', type=Path, required=True)
    p.add_argument('--pattern', default='beampair3-gate-*-e645b34b/raw')
    p.add_argument('--host', choices=['gcp1','gcp2'], default='gcp2')
    p.add_argument('--planned-n', type=int, default=40)
    a=p.parse_args();analyze(a.root,a.out,pattern=a.pattern,host=a.host,planned_n=a.planned_n)
