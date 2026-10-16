"""Search9 command comparison on saved visible inputs, never a physical rollout.

The 86367b4b baseline is checked against every recorded command. Search8 and
search9 then consume the same measurements and recorded applied-command history.
Only the prefix before divergence is on-policy. Full-stream difference counts are
explicitly counterfactual shadow outputs, not executed commands or new outcomes.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from types import ModuleType
from harness.grasp_act_contract import IssuedClock
from harness.grasp_act_input_audit import AuditedTeacherInput, new_input_audit
from harness.grasp_act_start_sync import GraspStartSync
from harness.grasp_act_visible_world import VisibleWorld
from scripts.replay_grasp_act_nominal_handoff import verified
from scripts.replay_grasp_act_recovery import KW, BASELINE, ROOT
from scripts.run_grasp_act_teacher import audit_visible_input
from sim.grasp_act_teacher_v3 import VisibleOnlyGraspTeacher

SEARCH8 = '793865d20475098f96f6966edf8ea1ccba058f6d'


def pinned(sha):
    source = subprocess.check_output(['git', 'show', f'{sha}:sim/grasp_act_teacher_v3.py'], cwd=ROOT, text=True)
    module = ModuleType('pinned_' + sha[:8])
    exec(compile(source, sha + '/grasp_act_teacher_v3.py', 'exec'), module.__dict__)
    return module.VisibleOnlyGraspTeacher


def replay(raw, baseline, search8):
    proof = []
    plan = json.loads(verified(raw, 'plan.json', proof)); result = json.loads(verified(raw, 'result.json', proof))
    assert result['source_sha'] == BASELINE and result['weld'] == 'off' and result['self_pose_source'] == 'issued'
    labels = {r: [json.loads(l) for l in verified(raw, f'teacher-{r}.jsonl' +
              ('.zst' if (raw/f'teacher-{r}.jsonl.zst').exists() else ''), proof).splitlines()] for r in plan['roles']}
    # Drop evaluator truth before creating any controller input.
    inputs = [{'t': v['t'], 'measurements': v['visible_measurements']}
              for l in verified(raw, 'eval-only.jsonl.zst', proof).splitlines() if (v := json.loads(l))]
    previous = {r: labels[r][0]['clean_teacher_command'] for r in labels}
    models = {r: VisibleWorld(r, e) for r, e in plan['roles'].items()}
    groups = [{r: cls(r, e, previous[r]['pwm'], **KW, **extra) for r, e in plan['roles'].items()}
              for cls, extra in ((baseline, {}), (search8, {'approach_recovery':'approach_recovery_v1'}),
                                (VisibleOnlyGraspTeacher, {'approach_recovery':'approach_recovery_v2'}))]
    clocks = [{r: IssuedClock() for r in labels} for _ in groups]
    syncs = [GraspStartSync(plan['roles'], result['grasp_start_delays_s']) for _ in groups]
    audit = new_input_audit(True, 'issued'); maximum = 0.
    counts = {'baseline_to_search9':0, 'search8_to_search9':0}
    first = {k:None for k in counts}; digests = [hashlib.sha256() for _ in groups]
    for i, row in enumerate(inputs):
        now = row['t']; worlds = {}
        for r in labels:
            audit_visible_input(audit, row['measurements'][r])
            worlds[r] = AuditedTeacherInput(models[r].observe(row['measurements'][r], now), audit)
        ticks = []
        for k, teachers in enumerate(groups):
            permits = syncs[k].tick({r:t.prepare_signal(worlds[r], now) for r,t in teachers.items()}, now)
            tick = {}
            for r,t in teachers.items():
                skill = 'wait' if t.phase == 'ready' and not permits[r] else 'grasp'
                elapsed = clocks[k][r].observe((skill,t.end,t.handoff), now, previous[r]['pwm'])
                t.skill_started = now-elapsed['skill_elapsed_s']
                cmd, done = t.step(worlds[r], now, permit_pick=permits[r]); tick[r] = (cmd, done, t.phase)
                digests[k].update(json.dumps(tick[r], sort_keys=True).encode())
                if k == 0:
                    expected = labels[r][i]['clean_teacher_command']
                    delta = max(abs(a-b) for a,b in zip(cmd['duration_s'], expected['duration_s'])); maximum = max(maximum,delta)
                    assert all(cmd[x] == expected[x] for x in ('t','wheels','pwm')) and delta <= 1e-12, (raw,i,r,'command')
                    assert done == labels[r][i]['done'] and t.phase == labels[r][i]['teacher_phase'], (raw,i,r,'phase')
                # All branches receive recorded actual command history. Past
                # a changed output this is a shadow test, not a new trajectory.
                t.remember_applied(labels[r][i]['applied_command'])
                if done:t.done_recorded = True
            ticks.append(tick)
        for j,key in enumerate(counts):
            changed = [r for r in labels if ticks[j][r][0] != ticks[2][r][0]]
            counts[key] += len(changed)
            if changed and first[key] is None:
                first[key] = {'tick':i, 'elapsed_sim_s':now-inputs[0]['t'], 'robots':changed,
                              'reference':{r:ticks[j][r] for r in changed},
                              'candidate':{r:ticks[2][r] for r in changed},
                              'candidate_choice':{r:groups[2][r].approach_choice for r in changed}}
        for r in labels:
            previous[r] = labels[r][i]['applied_command']; models[r].issue(previous[r])
    return {'episode':int(raw.parent.name[-3:]), 'saved_success':result['physical_success'],
            'baseline_commands_verified':len(inputs)*len(labels), 'saved_libm_max_duration_delta_s':maximum,
            'shadow_changed_commands':counts, 'first_divergence':first,
            'command_digests':dict(zip(('baseline','search8','search9'),[d.hexdigest() for d in digests])),
            'input_audit':audit, 'raw_proof':proof}


def main():
    p = argparse.ArgumentParser(); p.add_argument('--run',type=Path,required=True); p.add_argument('--out',type=Path,required=True); a=p.parse_args()
    baseline, old = pinned(BASELINE), pinned(SEARCH8); rows = []
    for raw in sorted(a.run.glob('cohort-*/episode-*/raw')):
        row = replay(raw,baseline,old); rows.append(row)
        print(row['episode'], row['shadow_changed_commands'], flush=True)
    assert len(rows)==40 and sum(r['saved_success'] for r in rows)==34
    success = [r for r in rows if r['saved_success']]
    summary = {'schema':'ugrp.grasp_act.search9_replay.v1','baseline_sha':BASELINE,'search8_sha':SEARCH8,
               'baseline_commands_verified':sum(r['baseline_commands_verified'] for r in rows),
               'successful_command_N':sum(r['baseline_commands_verified'] for r in success),
               'successful_shadow_changed_commands':{k:sum(r['shadow_changed_commands'][k] for r in success) for k in rows[0]['shadow_changed_commands']},
               'successful_changed_indices':{k:[r['episode'] for r in success if r['shadow_changed_commands'][k]] for k in rows[0]['shadow_changed_commands']},
               'invisible_measurements':sum(r['input_audit']['invisible_measurements'] for r in rows),
               'held_world_reads':sum(r['input_audit']['held_world_reads'] for r in rows),
               'scope':'baseline exact recorded-command validation; fixed-recorded-input shadow counts; after first divergence off-policy, never physical success; no World, rendering, physics or remote connection',
               'rows':rows}
    a.out.write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))


if __name__ == '__main__':main()
