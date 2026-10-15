from pathlib import Path
import json,collections,math,numpy as np
p=Path('/home/ugrp/ugrp-sim/ops-reviews/reloc15-93315-slip');a=[json.loads(l) for l in (p/'evaluation.jsonl').read_text().splitlines()];report=[]
for lo,hi in [(27.8,41),(41,47),(102,109),(109,118.3),(118.3,125.7)]:
 es=[r for r in a if lo<=r['t']<hi];wheel=collections.defaultdict(list);contacts=[]
 for r in es:
  for c in r['contacts']:
   if c.get('slip_xy_m_s') is not None:
    key=next(n.split('_roller_')[0] for n in c['names'] if '_roller_' in n)
    wheel[key].append([c['normal_N'],c['slip_xy_m_s']])
   if 'cargo_beam_1__bar' in c['names']:contacts.append(c)
 y=np.unwrap([r['yaw_rad'] for r in es]);dy=np.diff(y)/.1;acc=np.diff(dy)/.1
 report.append(dict(lo=lo,hi=hi,yaw_net_deg=float(np.degrees(y[-1]-y[0])),
  yaw_rate_abs_p50_p95_max_deg_s=np.degrees(np.quantile(abs(dy),[.5,.95,1])).tolist(),
  angular_acc_abs_p95_rad_s2=float(np.quantile(abs(acc),.95)),
  wheel_contact={k:dict(N=len(v),normal_N_p50=float(np.median(np.array(v)[:,0])),
     contact_slip_m_s_p50_p95=np.quantile(np.array(v)[:,1],[.5,.95]).tolist()) for k,v in wheel.items()},
  wheel_rates_rad_s_p50=np.median([r['wheel_qvel'] for r in es],axis=0).tolist(),
  wheel_motor_torque_Nm_max=float(np.max(np.abs([r['wheel_ctrl'] for r in es]))),
  beam_contact_sample_N=len(contacts),beam_max_moment_z_Nm=max([abs(c['moment_z_Nm']) for c in contacts],default=0)))
out=dict(scene_equal=True,replay_xyz_error_max=0.,segments=report,
 scope='sampled contact point tangent velocities including wheel and passive roller rotation; not wheel encoders used by controller',
 robot_mass_kg=1.1,cargo_mass_kg=.03,
 maximum_kinetic_drive_torque_per_wheel_Nm=.1176798*(.35-.1/1.2),
 maximum_four_wheel_yaw_moment_geometry_Nm=4*.1176798*(.35-.1/1.2)/.0325*.1255,
 qualification='v7 public roller mesh/contact and TT analogue uncalibrated; physical plausibility only, not proof of installed robot behavior')
(p/'slip-summary.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
