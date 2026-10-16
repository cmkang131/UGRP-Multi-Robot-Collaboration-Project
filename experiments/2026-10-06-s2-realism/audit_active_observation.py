"""s2v58 hypothetical-view ranking over sealed v56 belief records; no physics/GT."""
import argparse,bisect,copy,json,os,subprocess,time
from pathlib import Path
import numpy as np
from harness import zone_solo_cyan_active_observation as active
from harness import zone_solo_cyan_contract_v106 as c
from harness.owncam_localizer import LoadState
from harness import vision_loc_protocol as vp
from replay_sensor_consistency import RUNS,read,sha,global_factory,prior_factory
HERE=Path(__file__).resolve().parent
BASE=Path('/Users/changmin/projects/ugrp/outputs/s2-sensor-consistency-v56-20261008')


def audit(seed,out):
    started=time.monotonic();raw=RUNS[seed];src=BASE/f's{seed}-baseline'
    old=read(raw/'student_record.json');prediction=read(src/'prediction.json');b=read(raw/'bundle.json')
    for key,value in prediction['input_hashes'].items():assert sha(raw/key)==value
    assert prediction['pose_fields_sha256']==prediction['recorded_pose_fields_sha256']
    assert prediction['max_delta']==0 and not prediction['partial']
    r=(global_factory if seed>=1059 else prior_factory)(b)(c.hp.resolve(c.MAP_ID)[0],c.ROOT/c.CALIBRATION,c.CALIBRATION_SHA,**b['task'])
    pf=r.pose.provider.loc._pf;K=np.linalg.inv(vp.load_vis3()[0].mp.K_INV)
    clouds=np.load(src/'clouds.npz');poses=prediction['poses'];pts=[q['t'] for q in poses]
    measurements=prediction['measurements'];mts=[q['t'] for q in measurements]
    periodic=prediction['periodic'];periodic_t=[q['t'] for q in periodic]
    commands=old['commands'];ci=0;load=LoadState();servo={};charged=0.;last=-float('inf');count=0;rows=[]
    # Existing navigation pulse decisions are opportunity timestamps, not a
    # fabricated new closed-loop trajectory. No hypothetical view is injected.
    decisions=old['pulse_motion_model']['transformations']
    try:
        for d in decisions:
            now=d['t']
            while ci<len(commands) and commands[ci]['t']<=now+1e-8:
                q=commands[ci];load.command(q)
                if q['kind']=='initial_servo_command':servo={int(k):v for k,v in q['pulses'].items()}
                elif q['kind']=='arm':servo[q['servo_id']]=q['pulse']
                elif q['kind']=='look':servo[6]=q['pan_pulse']
                ci+=1
            mi=bisect.bisect_right(mts,now)-1
            if mi<0:continue
            m=measurements[mi]
            if m['posterior_ess']>=m['particle_count']/2 or now-last<active.LIMITS['min_interval_s']:continue
            last=now
            pi=max(0,bisect.bisect_right(periodic_t,now)-1);sample=periodic[pi]
            px=clouds[sample['key']];w=clouds[sample['key']+'w']
            report=poses[max(0,bisect.bisect_right(pts,now)-1)]
            pf.load.loaded=load.loaded
            ranking=active.rank(px,w,pf.column_model_for(servo),K,r.map,servo,load.loaded,report,r.pulse_profiles)
            selected=active.choose(ranking,now-commands[0]['t'],charged,count)
            if selected is not None:charged+=selected['added_s'];count+=1
            cov=np.cov(px[:,:2].T,aweights=w);eig=np.linalg.eigvalsh(cov)
            rows.append(dict(t=now,state=d['state'],loaded=load.loaded,trigger_t=m['t'],ess=m['posterior_ess'],n=m['particle_count'],
                belief_t=sample['t'],belief_age_s=now-sample['t'],covariance_principal_ratio=float(eig[-1]/max(eig[0],1e-300)),
                ranking=ranking,selected=None if selected is None else selected['name'],charged_s=charged,events=count))
        result=dict(seed=seed,physics_runs=0,gt_inputs=False,source_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            nice=os.getpriority(os.PRIO_PROCESS,0),wall_s=time.monotonic()-started,rows=rows,ess_triggers=sum(m['posterior_ess']<m['particle_count']/2 for m in measurements),
            query_count=len(rows),selected_count=count,added_s=charged,hypothetical=True,actual_active_views=0,
            off_exact=dict(max_delta=prediction['max_delta'],sealed_pose_sha256=prediction['pose_fields_sha256'],identity_attachment=True),
            sources={str(src/k):sha(src/k) for k in ('prediction.json','clouds.npz')},
            finite=all(np.isfinite([q['expected_reduction_nats'],q['expected_posterior_entropy_nats']]).all() for row in rows for q in row['ranking']))
        (out/f's{seed}.json').write_text(json.dumps(result,indent=2)+'\n')
        print(seed,'queries',len(rows),'selected',count,'wall',round(result['wall_s'],2),flush=True)
        return result
    finally:r.close();clouds.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    assert os.getpriority(os.PRIO_PROCESS,0)==0,'nice must be zero'
    a.output.mkdir(parents=True,exist_ok=False)
    plan=read(HERE/'active-observation-registration.json')
    rows=[audit(seed,a.output) for seed in plan['offline_seeds']]
    target=next(q for q in rows if q['seed']==1060)
    times=[q['t'] for q in target['rows'] if q['selected'] is not None]
    gates=dict(all_nine_valid=len(rows)==9,finite_expected_entropy=all(q['finite'] for q in rows),off_exact=True,
        s1060_action_before_124_8=any(t<plan['offline_gates']['s1060_action_before_s'] for t in times))
    result=dict(schema='ugrp.s2.active_observation.audit.v1',physics_runs=0,gt_inputs=False,gates=gates,passed=all(gates.values()),
        preregistration_sha256=sha(HERE/'active-observation-registration.json'),runs=[{k:v for k,v in r.items() if k!='rows'} for r in rows],
        s1060_hypothetical_selection_times=times,counterfactual_accuracy='not measurable from fixed old images',
        note='At recorded navigation pulse opportunities; nearest preceding 1s saved belief, current released pose/commands. Ranking sanity, not new-view closed-loop replay.')
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(gates),flush=True)
