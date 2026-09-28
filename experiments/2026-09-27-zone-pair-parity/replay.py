"""Read-only decision replay. No simulator, renderer, learned model, or network.

M2 has no continuous saved PoseReport after approach. Its optional shadow pass
re-estimates ONLY saved RGB/issued commands; it is explicitly not an exact PF or
closed-loop counterfactual. Dev reports are replayed directly, without GT files.
Run with the existing simulation venv, OMP_NUM_THREADS=1, PYTHONDONTWRITEBYTECODE=1.
"""
from __future__ import annotations

import argparse
import base64
import bisect
import copy
import hashlib
import importlib.abc
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RAW = Path('/Users/changmin/projects/ugrp/outputs')
MAIN = '97f91cb040bf382973ce84b24b1ca8399e64a6fb'
V4 = '3790372dfdd8e9de894bad7414657461bc8ba91d'
V5 = '3839555dc0de0880f74a40c831044e2b5be2d2d7'
sys.path.insert(0, str(ROOT))


class Boundary(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'mujoco', 'torch', 'tensorflow', 'requests', 'httpx'}:
            raise ImportError('parity boundary forbids ' + fullname)


sys.meta_path.insert(0, Boundary())


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


class FrozenPairs(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Read the exact branch blobs; never checkout or overwrite runtime files."""
    def __init__(self, ref):
        self.ref, self.sources = ref, {}

    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith('harness.zone_pair_'):
            name = fullname.replace('.', '/') + '.py'
            self.sources[fullname] = git('show', f'{self.ref}:{name}') + '\n'
            return importlib.util.spec_from_loader(fullname, self, origin=f'{self.ref}:{name}')

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        exec(compile(self.sources[module.__name__], module.__spec__.origin, 'exec'), module.__dict__)


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def clean(x):
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if hasattr(x, 'item'):
        return clean(x.item())
    return x


def write(path, value):
    Path(path).write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def report(frame):
    from harness.owncam_pose_source import PoseReport
    r = frame['report']
    vals = {k: v for k, v in r.items() if k != 'xyyaw'}
    if r['initialized']:
        vals.update(zip(('x_m', 'y_m', 'yaw_rad'), r['xyyaw']))
    else:
        vals.update(std_xy_m=math.inf, std_yaw_rad=math.inf)
    return PoseReport(**vals)


def observation(root, rid, frame):
    obs = read(root / 'inputs' / rid / f"{frame['frame']:05d}.json")
    data = (root / obs['image_file']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == obs['sha256'] == frame['sha256']
    obs['image'] = base64.b64encode(data).decode()
    return obs


def phase_at(events, now, default='approach'):
    state, seg = default, 0
    for e in events:
        t = e.get('sim_s', e.get('sim_time_s'))
        if t > now + 1e-6:
            break
        if e['event'] == 'state':
            state = e['state']
            seg = e.get('seg', seg)
    return state, seg


def make_ep(rid, static, plan, rep, servo, obs, state, gate):
    from harness.zone_own_guards import SweepGuard
    own = NS(robot_id=rid, now=rep.t_est, last_report=rep, last_obs=obs,
             servo=servo, guard=SweepGuard(static), gate=gate)
    ctl = NS(state=state, seg=0, driver=NS(state='drive'), beam_grasp_confirmed=False)
    ep = NS(own=own, controller=ctl, plan=plan, arguments={'role': 'end_neg' if rid == 'r1' else 'end_pos'},
            aborts=[], logs=[])
    ep.abort = lambda t, reason: ep.aborts.append({'sim_s': t, 'reason': reason})
    ep.log = lambda robot, event, now, **kw: ep.logs.append({'robot': robot, 'event': event, 'sim_s': now, **kw})
    return ep


def gate_profile(state):
    from harness.zone_own_guards import GATE_LOADED, GATE_UNLOADED
    return GATE_UNLOADED if state in ('approach', 'reapproach', 'wait_approach') else GATE_LOADED


def dev_run(root, ref):
    from harness.zone_own_guards import UncertaintyGate, SweepGuard, OwnPose
    from harness.zone_pair_admission import readiness_snapshot
    from harness.zone_pair_guards import PairCommandGuard
    from scripts import run_m2_pair as m2
    robots, calls = read(root / 'robots.json'), read(root / 'api_calls.json')
    pair = read(root / 'pair_records.json')
    static = read(root / 'inputs/static.json')['map']
    events, commands = rows(root / 'events.jsonl'), rows(root / 'commands.jsonl')
    manifest = read(root / 'manifest.json')
    index = read(root / 'artifacts.sha256.json')
    used = ['robots.json', 'api_calls.json', 'inputs/static.json', 'events.jsonl',
            'commands.jsonl', 'pair_records.json', 'manifest.json']
    result = {'id': root.name, 'raw_root': str(root), 'source_sha': manifest['source']['source_sha'],
              'judge_ref': ref, 'mode': 'saved_self_reports_direct', 'robots': {}, 'hashes': {}}
    for name in used:
        digest = sha(root / name)
        assert digest == index[name]['sha256']
        result['hashes'][name] = digest
    for rid in ('r1', 'r2'):
        frames = robots[rid]['frames']
        ack = next(x for x in calls if x['robot_id'] == rid and x['api'] == 'pair_carry')
        now = ack['sim_s']
        gate = UncertaintyGate()
        for f in frames:
            if f['t'] >= now - 1e-6: break
            rep = report(f)
            gate.update(f['t'], rep.initialized, rep.std_xy_m, rep.std_yaw_rad)
        f = next(f for f in reversed(frames) if f['t'] < now - 1e-6)
        obs = observation(root, rid, f)
        ex = NS(last_report=report(f), last_obs=obs, gate=gate, mode='m1', robot_id=rid,
                stopped=None, job=None, servo={int(k): v for k, v in f['commanded_servo'].items()},
                holding=lambda: {'answer': 'no'})
        rr = {'actual_admission': ack, 'replayed_admission': readiness_snapshot(ex, now),
              'admission_context': 'saved no active job, open gripper; order checked separately by recorded ack',
              'first_postapproach_gate_reject': None, 'm2_at_actual_stop': {}, 'guard_replay': []}
        for e in events:
            if e['robot_id'] == rid and e['detail'].get('reason') == 'SWEEP_TRANSITION_BLOCKED':
                g = e['detail']['guard']; p = g['own_estimate']
                po = OwnPose(p['x_m'], p['y_m'], p['yaw_rad'], p['std_xy_m'], p['std_yaw_rad'])
                guard = SweepGuard(static)
                rr['guard_replay'].append({'sim_s': e['sim_s'], 'receipt': g,
                    'recomputed': guard.transition_diagnostic(g['current_pwm'], g['target_pwm'], po, loaded=g['loaded'])})
        pr = next((p for p in pair if rid in p.get('robots', {})), None)
        pe = pr['robots'][rid]['events'] if pr else []
        actual_stops = [e for e in events if e['robot_id'] == rid and e['event'] in ('job_failed', 'failed')]
        rr['actual_stops'] = actual_stops
        if pr:
            if ref == V5:
                from harness.zone_pair_align import relook_reason, ranked_look_pans
                from harness.zone_pair_geometry import PairSweepGuard
                entries=[e for e in pe if e['event']=='state' and e['state']=='align']
                rr['v5_first_align_entry_relook_s']=entries[0]['sim_s'] if entries else None
                rr['v5_first_in_align_relook']=None
                for af in frames:
                    state,_=phase_at(pe,af['t'])
                    if state!='align':continue
                    reason=relook_reason(report(af),af['t'])
                    if reason:
                        sg=PairSweepGuard(SweepGuard(static),pr['plan']['beam_geometry'],
                                          'end_neg' if rid=='r1' else 'end_pos')
                        choices=ranked_look_pans(static,report(af),{int(k):v for k,v in af['commanded_servo'].items()},sg)
                        rr['v5_first_in_align_relook']={'sim_s':af['t'],'reason':reason,'report':af['report'],
                            'frame_id':af['frame_id'],'safe_static_pan_candidates':choices,
                            'scope':'trigger on old trace only; new RGB after changed wrist trajectory unavailable'}
                        break
            gate = UncertaintyGate()
            ep = None
            for f in frames:
                state, seg = phase_at(pe, f['t'])
                gate.set_profile(gate_profile(state))
                rep = report(f)
                gate.update(f['t'], rep.initialized, rep.std_xy_m, rep.std_yaw_rad)
                if f['t'] < now or state in ('approach', 'reapproach', 'wait_approach', 'failed', 'done'): continue
                obs_stub = {'frame_id': f['frame_id'], 'sim_time': f['t']}
                if ep is None:
                    ep = make_ep(rid, static, pr['plan'], rep, {}, obs_stub, state, gate)
                    cg = PairCommandGuard(ep)
                ep.own.last_report, ep.own.last_obs = rep, obs_stub
                ep.controller.state, ep.controller.seg = state, seg
                ep.own.now = f['t']
                # No synthetic motion, no reset recovery claim: only ordinary phase gate.
                if state not in ('pregrasp_look',):
                    ok = cg.before_control(f['t'])
                    if not ok:
                        rr['first_postapproach_gate_reject'] = {'sim_s': f['t'], 'phase': state,
                            'frame_id': f['frame_id'], 'sha256': f['sha256'], 'report': f['report'],
                            'reason': ep.aborts[-1]['reason'], 'gate': gate.as_dict()}
                        break
            # Read the actual terminal own event (not evaluation) and original JPEG.
            terminal = next((e for e in pe if e['event'] == 'state' and e.get('state') == 'failed'), None)
            stop = next((e for e in actual_stops if e.get('job_kind') == 'pair_carry'), None)
            tstop = terminal['sim_s'] if terminal else (stop['sim_s'] if stop else frames[-1]['t'])
            fs = [f for f in frames if f['t'] <= tstop + 1e-6]
            f = fs[-1]; obs = observation(root, rid, f)
            state, seg = phase_at([e for e in pe if e != terminal], tstop)
            rr['m2_at_actual_stop'] = {'sim_s': tstop, 'last_causal_frame_s': f['t'],
                'frame_id': obs['frame_id'], 'sha256': obs['sha256'], 'phase': state,
                'extra_pose_gate_exists_in_m2_manipulation': False,
                'grip_view_m2': m2.grip_view_m2(obs['image']),
                'beam_obs': {k:v for k,v in m2.ob2.observe_beam(obs['image'], f['commanded_servo']).items() if k != 'provenance'},
                'interpretation': 'local predicate only; no unrecorded continuation or future lift outcome inferred'}
            beam = rr['m2_at_actual_stop']['beam_obs']
            rr['m2_at_actual_stop']['align_command_if_full_end_visible'] = (
                m2.ob.align_command(beam) if beam.get('visible') and beam.get('end_visible') else None)
            if root.name == 'dev05' and rid == 'r1':
                # Reconstruct the exact command queue from the last own beam fit.
                # The rejected command itself was not logged as an issued command.
                from scripts.zone_teacher import ArmSequence
                from harness.zone_pair_geometry import PairSweepGuard
                st = next(e for e in pe if e['event']=='state' and e['state']=='grasp')
                be = next(e for e in reversed(pe) if e['event']=='beam_obs' and e['sim_s']<=st['sim_s'])
                bf = next(x for x in reversed(frames) if x['t']<=st['sim_s']+1e-6)
                initial = {int(k):v for k,v in bf['commanded_servo'].items()}
                emitted=[]
                port=NS(apply=lambda c,t:emitted.append(dict(c)))
                arm=ArmSequence(port,initial)
                ctl=NS(grip_base=be['grip_base_m'],arm=arm,set=lambda *a,**kw:None,
                       fail=lambda *a,**kw:(_ for _ in ()).throw(AssertionError(a)))
                m2.study.PairStudent._queue_grasp(ctl,st['sim_s'])
                issued=[c for c in commands if c.get('robot_id',c.get('robot'))==rid
                        and st['sim_s'] < c['t'] < tstop and c['kind'] in ('arm','look')]
                for t in sorted({c['t'] for c in issued}): arm.tick(t+0.0001)
                simple=lambda c:{k:v for k,v in c.items() if k not in ('t','robot','robot_id','after_abort')}
                assert emitted==[simple(c) for c in issued], (len(emitted),len(issued),next(((i,a,simple(b)) for i,(a,b) in enumerate(zip(emitted,issued)) if a!=simple(b)),None), emitted[-5:], [simple(c) for c in issued[-5:]])
                before=len(emitted); arm.tick(tstop)
                rejected=emitted[before:]
                gate=UncertaintyGate(gate_profile('grasp'));gate.state='ok'
                ep=make_ep(rid,static,pr['plan'],report(f),{int(k):v for k,v in f['commanded_servo'].items()},obs,'grasp',gate)
                cg=PairCommandGuard(ep); checked=cg.check(tstop,rejected)
                rr['grasp_command_replay']={'matched_issued_commands':before,'reconstructed_unissued_batch':rejected,
                    'checked_output':checked,'aborts':ep.aborts,'attached':cg.carrying_beam,
                    'scope':'same saved pose/PWM and reconstructed next arm queue; not altered v5 phase trajectory'}
            # v5 exact preclose path: rebuild from saved anchor RGB, then own commands.
            if ref in (V4, V5):
                ready = next((e for e in pe if e['event'] == 'preclose_beam_guard' and e.get('reason') == 'BEAM_UNCERTAIN'), None)
                if ready:
                    t = ready['sim_s']; f = next(f for f in reversed(frames) if f['t'] <= t + 1e-6)
                    obs = observation(root, rid, f); rep = report(f)
                    gate = UncertaintyGate(gate_profile('wait_close')); gate.state = 'ok'
                    ep = make_ep(rid, static, pr['plan'], rep, {int(k):v for k,v in f['commanded_servo'].items()}, obs, 'wait_close', gate)
                    cg = PairCommandGuard(ep)
                    anchors = [e for e in pe if e['event'] == 'beam_standoff' and e.get('accepted') and e['sim_s'] <= t]
                    anchor = anchors[-1]; af = next(x for x in frames if x['frame_id'] == anchor['frame_id'])
                    ao = observation(root, rid, af); servo = {int(k):v for k,v in af['commanded_servo'].items()}
                    assert cg.beam_track.observe_standoff(ao, servo, 0)
                    for c in commands:
                        if c.get('robot_id', c.get('robot')) != rid or not af['t'] < c['t'] <= t: continue
                        cg.beam_track.command(c, servo)
                        if c['kind'] == 'arm': servo[int(c['servo_id'])] = c['pulse']
                        if c['kind'] == 'look': servo[6] = c['pan_pulse']
                    accepted = cg.preclose_check(t, obs)
                    rr['preclose_replay'] = {'accepted': accepted, 'sim_s': t, 'frame_id': f['frame_id'],
                        'anchor_frame_id': af['frame_id'], 'anchor_sha256': af['sha256'],
                        'track': cg.beam_track.beam, 'logs': ep.logs,
                        'pose_gate_context': 'recorded gate ok and fresh shared relook; no threshold changed'}
        result['robots'][rid] = rr
    return result


def m2_run(root, shadow=False):
    from harness.zone_pair_executor import make_plan
    from harness.zone_pair_geometry import PairSweepGuard
    from harness.zone_own_guards import SweepGuard, OwnPose, UncertaintyGate
    from harness.zone_pair_admission import readiness_snapshot
    from harness.zone_pair_guards import PairCommandGuard
    from harness.owncam_pose_source import OwnCamPoseSource
    from harness.zone_pair_vision import valid_frame
    import cv2
    import numpy as np
    meta = read(root / 'result.json')
    # Strict allow-list. Evaluation labels are attached only by collect() after replay.
    conf = {k: meta[k] for k in ('seed','stage','map','order_sheet','source_sha','approach_driver','claims','contact_profile','weld')}
    del meta
    static = json.loads(git('show', f"{conf['source_sha']}:maps/zones/{conf['map']}.json"))
    calibration_path = 'experiments/2026-09-26-zone-owncam-loop-v2/calibration_loop_v2.json'
    calibration_blob = git('show', f"{conf['source_sha']}:{calibration_path}") + '\n'
    params = json.loads(calibration_blob)['params']
    commands, inputs, events = rows(root/'commands.jsonl'), rows(root/'inputs.jsonl'), rows(root/'events.jsonl')
    hashes = read(root/'hashes.json')
    out = {'id': str(root.relative_to(RAW)), 'source_sha': conf['source_sha'],
           'contact_profile': conf['contact_profile'], 'weld':conf['weld'], 'robots': {},
           'hashes': {n:sha(root/n) for n in ('result.json','inputs.jsonl','commands.jsonl','events.jsonl')},
           'direct_report_replay': 'insufficient_evidence: no continuous self PoseReport/covariance; localizer-eval excluded',
           'shadow_scope': 'saved-frame and command-event clock; current shared PF; not exact original PF or closed-loop rollout'}
    assert all(hashes[n] == h for n,h in out['hashes'].items())
    try:
        plan = make_plan(static, conf['order_sheet'], 'B')
        out['static_plan_admission'] = 'pass'
    except ValueError as e:
        out['static_plan_admission'] = str(e)
        # Geometry is a static catalogue, never reconstructed from a world/eval.
        from sim.zone_cargo import instances
        spec = instances([{'item_id':'beam','kind':'long_beam','pose':[0,0,0]}])[0].spec()
        bar = next(p for p in spec.parts if p.name == 'bar')
        plan = {'route': [[0,0],[3.2,.05]], 'beam_geometry': {'center_m':bar.center,'half_extents_m':bar.size,
                'grasps': {g.role:{'xyz_m':g.grip_xyz,'yaw_rad':g.approach_yaw} for g in spec.grasps}}}
    for rid in ('r1','r2'):
        fs = [x for x in inputs if x['robot']==rid]
        cs = [x for x in commands if x['robot']==rid]
        es = [x for x in events if x['robot']==rid]
        rr = {'saved_frames':len(fs), 'commands':len(cs), 'first_static_plan_reject':out['static_plan_admission'],
              'max_frame_gap_s':max((b['sim_time']-a['sim_time'] for a,b in zip(fs,fs[1:])), default=0),
              'first_admissible_shadow_frame':None, 'first_shadow_postapproach_gate_reject':None,
              'first_shadow_geometry_reject':None, 'verified_jpegs':0}
        if not shadow:
            out['robots'][rid]=rr; continue
        pose_source=OwnCamPoseSource(static, params, seed=conf['seed'])
        gate=UncertaintyGate(); ep=None; cg=None; ci=0
        geom=PairSweepGuard(SweepGuard(static),plan['beam_geometry'],'end_neg' if rid=='r1' else 'end_pos')
        admitted=False
        for f in fs:
            now=f['sim_time']; state,seg=phase_at(es,now)
            while ci<len(cs) and cs[ci]['t'] < round(now, 4) - 1e-8:
                pose_source.on_command(cs[ci]); ci+=1
            blob=(root/'inputs'/f['file']).read_bytes()
            assert hashlib.sha256(blob).hexdigest()==f['sha256']; rr['verified_jpegs']+=1
            rgb=cv2.cvtColor(cv2.imdecode(np.frombuffer(blob,np.uint8),cv2.IMREAD_COLOR),cv2.COLOR_BGR2RGB)
            rep=pose_source.on_frame(now,rgb)
            obs={'image':base64.b64encode(blob).decode(),'robot_id':rid,'camera':'robot_cam','sim_time':now,
                 'frame_id':int(Path(f['file']).stem.split('-')[-1]),'sha256':f['sha256'],
                 'actuator_state':{'servo_pulses':f['own_pose_commands']}}
            servo={int(k):v for k,v in f['own_pose_commands'].items()}
            assert servo==pose_source.servo, (root,rid,now,'commanded PWM mismatch')
            gate.set_profile(gate_profile(state)); gate.update(now,rep.initialized,rep.std_xy_m,rep.std_yaw_rad)
            if not admitted and state=='approach' and gate.ok:
                ex=NS(last_report=rep,last_obs=obs,gate=gate,mode='m1',robot_id=rid,stopped=None,job=None,
                      servo=servo,holding=lambda:{'answer':'no'})
                receipt=readiness_snapshot(ex,now)
                if receipt['state']=='available':
                    rr['first_admissible_shadow_frame']={'sim_s':now,'frame_id':obs['frame_id'],'receipt':receipt}
                    admitted=True
            if ep is None:
                ep=make_ep(rid,static,plan,rep,servo,obs,state,gate);cg=PairCommandGuard(ep)
            ep.own.last_report,ep.own.last_obs,ep.own.servo,ep.own.now=rep,obs,servo,now
            ep.controller.state,ep.controller.seg=state,seg
            detail={'sim_s':now,'phase':state,'frame_id':obs['frame_id'],'sha256':obs['sha256'],'report':rep.as_dict()}
            if state not in ('approach','reapproach','pregrasp_look','done','failed') and rr['first_shadow_postapproach_gate_reject'] is None:
                if not cg.before_control(now):
                    rr['first_shadow_postapproach_gate_reject']={**detail,'reason':ep.aborts[-1]['reason']}
            if admitted and rep.initialized and rr['first_shadow_geometry_reject'] is None:
                p=OwnPose.from_report(rep)
                # A current-volume reject is a necessary transition failure. Do not invent future PWM.
                attached=state in ('grasp','wait_lift','lift','wait_carry','carry','wait_lower','lower','wait_open')
                clear,wall=geom.arm_clearance(servo,p,loaded=attached)
                chassis,cwall=geom.chassis_clearance(p)
                if min(clear,chassis)<0:
                    rr['first_shadow_geometry_reject']={**detail,'arm_clearance_m':clear,'arm_wall':wall,
                        'chassis_clearance_m':chassis,'chassis_wall':cwall,'attached_assumption_main':attached,
                        'scope':'current-volume necessary predicate; not full command dispatch/recovery outcome'}
            if rr['first_shadow_postapproach_gate_reject'] and rr['first_shadow_geometry_reject']:
                break
        out['robots'][rid]=rr
    return out


def main():
    p=argparse.ArgumentParser(); p.add_argument('--mode',choices=['dev','m2'],required=True)
    p.add_argument('--ref',default=MAIN);p.add_argument('--run',type=Path);p.add_argument('--shadow',action='store_true')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert a.output.resolve().is_relative_to(OUT) or a.output.resolve().is_relative_to(Path('/tmp').resolve())
    sys.meta_path.insert(0,FrozenPairs(a.ref))
    if a.mode=='dev':
        roots=[a.run] if a.run else [q for pat in ('zone-pair-dev-v2-*','zone-pair-dev-v3-*','zone-pair-dev-v4-*') for root in sorted(RAW.glob(pat)) for q in sorted(root.glob('dev*')) if (q/'robots.json').exists()]
    else:
        roots=[a.run] if a.run else [f.parent for n in ('zone-m2-pair-20260926','zone-m2-pair-kiro-20260926') for f in sorted((RAW/n).rglob('result.json')) if 'tensorboard' not in str(f) and read(f).get('evaluation_only',{}).get('success_gt') is True]
    result={'schema':'ugrp.zone_pair_parity.v1','judge_ref':a.ref,'physics_steps':0,'model_calls':0,
            'eval_used_for_control':False,'runs':[]}
    for root in roots:
        print('REPLAY',root,flush=True)
        r=dev_run(root,a.ref) if a.mode=='dev' else m2_run(root,a.shadow)
        # Scoring labels are appended only after predicates have returned.
        r['posthoc_label']=read(root/'result.json').get('evaluation_only',{}).get('success_gt') if a.mode=='m2' else read(root/'result.json').get('physical_success')
        result['runs'].append(r);write(a.output,result)
    result['blocked_modules_not_imported']=not any(n in sys.modules for n in ('mujoco','torch','tensorflow'))
    write(a.output,result)


if __name__=='__main__': main()
