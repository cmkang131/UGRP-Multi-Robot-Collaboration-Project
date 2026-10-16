from pathlib import Path
import hashlib,json,math,shutil,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from harness.drive_model import CommandDriveModel,DriveParameters,wheel_speed
from sim.visible_belief import rates
out=Path(__file__).resolve().parent
analysis=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/odometry-scale/damping_analysis.md')
scene=Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/beam-gate-752b0cbb/raw/grasp-search-gate40-gcp-752b0cbb/cohort-016/episode-016/raw/scene.xml')
v7=ROOT/'experiments/2026-10-06-drive-friction/v7-results.json'
files=[analysis,scene,v7,Path('/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/odometry-scale/scripts/m3.py')]
root=ET.parse(scene).getroot();robot=next(b for b in root.iter('body') if b.get('name')=='r1__robot');wheel=next(b for b in robot.iter('body') if b.get('name')=='r1__wheel_fl_body')
mass=sum(float(i.get('mass')) for i in robot.iter('inertial'))
parts={'reflected_body_mass_m_r2_over_4':mass*.0325**2/4,'hub_y_axis':float(wheel.find('inertial').get('diaginertia').split()[1]),'joint_armature':float(wheel.find('joint').get('armature')),'rigid_carried_rollers_upper':0.}
for b in wheel.findall('body'):
 i=b.find('inertial');pos=list(map(float,b.get('pos').split()));j=list(map(float,i.get('diaginertia').split()))
 parts['rigid_carried_rollers_upper']+=float(i.get('mass'))*(pos[0]**2+pos[2]**2)+max(j)
p=DriveParameters();rows=[]
saved=json.loads(v7.read_text())['rows']
no_contact=next(r for r in saved if r['run']=='v7-motion-no_contact-u035')
for r in saved:
 if r['run'] in ('v7-empty-forward-u035','v7-empty-forward-u050','v7-empty-forward-u100'):
  u=r['normalized_wheel_command'][0];w=sum(r['steady_wheel_rad_s'])/4;pred=wheel_speed(u)[0]
  rows.append(dict(run=r['run'],u=u,omega=w,measured_ratio=w/p.omega0,predicted_ratio=pred/p.omega0,relative_error=pred/w-1,residual_loss_nm=p.torque_cap_nm*(u-p.kinetic_fraction)-p.damping_nm_s*w))
xbar=sum(r['omega'] for r in rows)/3;ybar=sum(r['residual_loss_nm'] for r in rows)/3
b1=sum((r['omega']-xbar)*(r['residual_loss_nm']-ybar) for r in rows)/sum((r['omega']-xbar)**2 for r in rows)
fit={'tau_c_nm':ybar-b1*xbar,'b1_nm_s':b1,'n':3,'parameters':2,'residual_degrees_of_freedom':1}
def pulse(params):
 m=CommandDriveModel(params);active=m.delta([.35]*4,[.1]*4,.1)[0];coast=m.delta([0.]*4,[0.]*4,1.)[0]
 return dict(I_eff=params.effective_inertia_kg_m2,active_m=active,coast_m=coast,total_m=active+coast,final_omega=m.angular_speeds)
r=rates(drive_model_deadband_v1=True)
model=CommandDriveModel();dist=sum(model.delta([.35]*4,[.07]*4,.1)[0] for _ in range(200));steady=wheel_speed(.35)[0]*p.wheel_radius_m
result=dict(scope='saved numeric data and XML arithmetic only; no physics, rendering, remote or model calls',parameters=vars(p),sources=[dict(path=str(f.resolve()),sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in files],steady=rows,no_contact=dict(run=no_contact['run'],measured_ratio=sum(no_contact['steady_wheel_rad_s'])/4/p.omega0,source_prediction=p.torque_cap_nm*(.35-p.kinetic_fraction)/p.damping_nm_s/p.omega0),contact_fit=fit,inertia=dict(terms_kg_m2=parts,sum_kg_m2=sum(parts.values()),chosen_kg_m2=p.effective_inertia_kg_m2,qualification='rounded upper-side estimate, rigid carried rollers; actual mecanum coupling/load not identified'),isolated_pulse=pulse(p),inertia_sensitivity=[pulse(DriveParameters(effective_inertia_kg_m2=x)) for x in [.0002,.000385]],repeated_duty=dict(pulse_s=.07,period_s=.1,repetitions=200,m1_ratio=dist/(200*.07*.35*p.omega0*p.wheel_radius_m),relative_to_contact_steady=dist/(200*.07*steady)),m2_rates=dict(axial=r[0],lateral=r[1],yaw=r[2],yaw_measured_reference=1.03,yaw_relative_error=r[2]/1.03-1,yaw_loss_ratio_verified=False,axial_acceptance_mm=[12.6,13.2],axial_measured_reference_mm=12.9),limits=['steady three points are fit data, not held out','pulse includes passive coast after .1 s command','yaw/lateral independent loss and hardware not verified','no body GT gains applied to the new model'])
(out/'calibration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
shutil.copyfile(analysis,out/'damping_analysis.md')
print(json.dumps({k:result[k] for k in ['contact_fit','isolated_pulse','repeated_duty','m2_rates']},indent=2))
