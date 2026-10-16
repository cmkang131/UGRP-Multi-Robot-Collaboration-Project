"""Evaluation-only recorded-turn audit; never changes or feeds estimator inputs."""
from pathlib import Path
import sys,json,math,csv
from collections import Counter
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
EXP=Path(__file__).resolve().parents[1]
RAW=Path('/Users/changmin/projects/ugrp/outputs/rbpf-motion-gate-v1/baseline')
BASE=Path('/Users/changmin/projects/ugrp/outputs/rbpf-insertion-v1/on/prediction.json')
from harness.self_pulse_odom import PulseOdometry
from harness.self_map_prob import wrap

def rows(p):return [json.loads(l) for l in p.read_text().splitlines()]
def dump(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')

def main():
    commands=sorted(rows(RAW/'robots/r3/commands.jsonl'),key=lambda r:r['t'])
    truth=rows(RAW/'eval_only/trajectory.jsonl')
    times=np.array([r['t'] for r in truth]);actual=np.unwrap([r['robot_yaw_rad'] for r in truth])
    odom=PulseOdometry(commands[0]['t']);cursor=0;dr=[];variance=[0.];cumulative_q=[]
    def add_noise(delta,q):variance[0]+=float(q[2])
    odom.step_callback=add_noise
    for t in times:
        while cursor<len(commands) and commands[cursor]['t']<t-1e-8:
            odom.command(commands[cursor]);cursor+=1
        odom.advance(t);dr.append(odom.pose[2]);cumulative_q.append(variance[0])
    dr=np.unwrap(dr)
    prediction=json.loads(BASE.read_text());poses=prediction['poses']
    pt=np.array([p['t'] for p in poses]);est=np.unwrap([p['pose'][2] for p in poses])+actual[0]
    sample=lambda a,t:float(np.interp(t,times,a))
    estimate=lambda t:float(np.interp(t,pt,est))
    degrees=lambda x:float(np.degrees(x))
    turns=[]
    for i,c in enumerate(commands):
        if c.get('kind') not in ('drive','mecanum') or not c.get('turn',0):continue
        end=min(commands[i+1]['t'] if i+1<len(commands) else times[-1],times[-1])
        if turns and turns[-1]['last_command']==i-1 and turns[-1]['u']==c['turn']:
            turns[-1].update(end_s=end,last_command=i,count=turns[-1]['count']+1)
        else:turns.append(dict(start_s=c['t'],end_s=end,u=c['turn'],count=1,last_command=i))
    for row in turns:
        a,b=row['start_s'],row['end_s']
        row.pop('last_command')
        row.update(dr_delta_deg=degrees(sample(dr,b)-sample(dr,a)),gt_delta_deg=degrees(sample(actual,b)-sample(actual,a)),
            estimated_delta_deg=degrees(estimate(b)-estimate(a)),
            yaw_error_start_deg=degrees(wrap(estimate(a)-sample(actual,a))),
            yaw_error_end_deg=degrees(wrap(estimate(b)-sample(actual,b))))
        row['dr_excess_deg']=row['dr_delta_deg']-row['gt_delta_deg']
        ds=[d for d in prediction['decisions'] if a<d['t']<=b+1e-8]
        row['matching_reasons']=dict(Counter(d['reason'] for d in ds))
    # RBPF yaw propagation is additive; recreate pre-proposal yaw for each
    # recorded particle with stored resampling parent indices, no re-estimation.
    cloud=np.zeros(100);last_dr=0.;scans=[];last_scan_q=0.;initial_var=math.radians(2.)**2
    for d in prediction['decisions']:
        cur=sample(dr,d['t']);prior=wrap(cloud+wrap(cur-last_dr));last_dr=cur
        pe=d.get('particle_events')
        if pe:
            j=d['selected_before_resampling'];target=wrap(sample(actual,d['t'])-actual[0])
            needed=degrees(wrap(target-prior[j]))
            q=sample(cumulative_q,d['t'])
            sigma=math.sqrt(initial_var+q-last_scan_q+(1e-10 if d['matching_attempted'] else 0.))
            scans.append(dict(t=d['t'],reason=d['reason'],matching_attempted=d['matching_attempted'],
                prior_yaw_deg=degrees(prior[j]),needed_gt_yaw_correction_deg=needed,
                prior_yaw_sigma_deg=degrees(sigma),needed_prior_sigma=abs(math.radians(needed))/sigma,
                outside_rbpf_8deg=abs(needed)>8.,outside_graph_15deg=abs(needed)>15.,
                selected_search_boundary=pe[j].get('search_boundary'),
                overlap=pe[j].get('overlap'),residual_m=pe[j].get('residual_m'),
                posterior_yaw_error_deg=degrees(wrap(d['pose'][2]-target))))
            cloud=np.array([e['pose'][2] for e in pe])
            last_scan_q=q;initial_var=1e-10
            if d['resampled']:cloud=cloud[d['parent_indices']]
            assert abs(wrap(cloud[d['selected_after_resampling']]-d['pose'][2]))<1e-10
        else:cloud=prior
    result=dict(turns=turns,scans=scans,turn_totals={str(sign):{k:sum(t[k] for t in turns if np.sign(t['u'])==sign)
        for k in ('dr_delta_deg','gt_delta_deg','dr_excess_deg')} for sign in (-1,1)},
        rbpf_coarse_yaw_deg=8.,rbpf_fine_extension_max_deg=3.,
        graph_loop_window_deg=15.,qualifications=[
        'Turn run = consecutive issued nonzero-turn commands of same sign, ends at next command timestamp (includes inter-command tail).',
        'Original commands/GT/prediction timestamps interpolated only for evaluation.',
        'Required GT correction outside a window is necessary geometric exclusion, not proof widening fixes an already rotated own map.',
        'Graph switchable constraints run at finalization; egomap26 figure was frontend, so graph +/-15 cannot explain an online turn.'])
    dump(EXP/'results/turn-diagnosis.json',result)
    with (EXP/'results/turns.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(turns[0]));writer.writeheader();writer.writerows(turns)
    print('turn runs',len(turns),'nonzero commands',sum(r['count'] for r in turns))
    print('largest absolute DR excess',json.dumps(sorted(turns,key=lambda r:abs(r['dr_excess_deg']),reverse=True)[:8],indent=2))
    print('35-45 scans',json.dumps([s for s in scans if 35<=s['t']<=45],indent=2))
    print('outside counts',sum(s['outside_rbpf_8deg'] for s in scans if s['matching_attempted']),sum(s['matching_attempted'] for s in scans))
    assert 'mujoco' not in sys.modules
if __name__=='__main__':main()
