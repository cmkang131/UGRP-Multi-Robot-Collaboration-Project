import pathlib,json,subprocess,collections,math,numpy as np,hashlib
from harness.selfmap5_registration import MultiFrameEvidence
from harness.selfmap4_geometry import StaticRegistration,static_input
from harness.reloc12_registration import ransac_hypotheses
p=pathlib.Path('/home/ugrp/ugrp-sim/runs/reloc12-r1-raw-smooth-93571-a82bc72e/raw')
def rows(name):
 q=p/name
 b=q.read_bytes() if q.exists() else subprocess.check_output(['zstd','-dc',str(q)+'.zst'])
 return [json.loads(l) for l in b.splitlines()]
tr=rows('trace.jsonl');gt={round(r['t'],6):r for r in rows('eval_only/trajectory.jsonl')}
reg=StaticRegistration(static_input()[0]);counts=collections.Counter();accepted=[];details=[]
for row in tr:
 s=row['static_registration'];rej=s['reloc10_diagnostics']['rejection_reasons']
 if any(k in rej for k in ['no_sensor_update','pf_unresolved','cluster_mass','xy_covariance','yaw_covariance','geometry']):continue
 x=s['reloc12']['replay'];m=MultiFrameEvidence();m.frames=x['frames']
 a=ransac_hypotheses(m,reg.pf.landmark_map.edges,x['own_odometry_pose'],np.asarray(s['covariance']));counts[str(a['candidate_count'])]+=1
 match=False
 if a['unique']:
  q=a['candidates'][0];pf=s['world_pose'];match=math.dist(q[:2],pf[:2])<=.15 and abs((q[2]-pf[2]+math.pi)%(2*math.pi)-math.pi)<=math.radians(10)
 if match:
  g=gt.get(round(row['t'],6));pf=s['world_pose']
  accepted.append(dict(t=row['t'],xy_m=math.dist(pf[:2],g['robot_xyz_m'][:2]),yaw_deg=math.degrees(abs((pf[2]-g['robot_yaw_rad']+math.pi)%(2*math.pi)-math.pi))))
 details.append(dict(t=row['t'],candidate_count=a['candidate_count'],unique=a['unique'],agrees_with_PF=match,search_complete=a['search_complete']))
out=dict(scope='offline RANSAC replay of saved smooth buffers, not a new physical smooth run',source_sha='ff1ccf27a43fe73d9b49dac82caf26a4584060d0',evaluated=len(details),candidate_counts=dict(counts),PF_agree_accept_N=len(accepted),accepted=accepted,details=details)
path=pathlib.Path('/home/ugrp/ugrp-sim/ops-reviews/reloc12/smooth-ransac-replay.json');path.write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('details','accepted')}))
