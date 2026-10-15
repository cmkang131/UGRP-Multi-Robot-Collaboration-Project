"""Inspect saved XML and source bytes only. Never instantiate a simulator."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from harness.drive_model import DEFAULT_PARAMETERS as P, wheel_speed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('beam_runs',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();scenes=[]
    for p in sorted(args.beam_runs.glob('cohort-*/episode-*/raw/scene.xml')):
        root=ET.parse(p).getroot();joints=[];actuators=[];geometry=[]
        for j in root.iter('joint'):
            if '__wheel_' in j.get('name','') and j.get('name','').endswith('_joint'):
                joints.append(dict(j.attrib))
        for a in root.find('actuator'):
            if '__wheel_' in a.get('name','') and a.get('name','').endswith('_drive'):
                actuators.append(dict(tag=a.tag,**a.attrib))
        for b in root.iter('body'):
            if '__wheel_' in b.get('name','') and b.get('name','').endswith('_body'):
                xyz=list(map(float,b.get('pos').split()))
                geometry.append(dict(name=b.get('name'),pos=xyz,lx_plus_ly_m=abs(xyz[0])+abs(xyz[1])))
        assert len(joints)==len(actuators)==len(geometry)==12
        assert all(float(j['damping'])==P.damping_nm_s and float(j['frictionloss'])==0 for j in joints)
        assert all(a['tag']=='motor' and a['gear']=='1' for a in actuators)
        assert all(abs(g['lx_plus_ly_m']-P.lx_plus_ly_m)<1e-12 for g in geometry)
        scenes.append(dict(path=str(p.resolve()),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
                           wheel_damping_nm_s=P.damping_nm_s,wheel_lx_plus_ly_m=P.lx_plus_ly_m,
                           wheel_joints=len(joints),native_motors=len(actuators),defaults=len(root.findall('default'))))
    assert len(scenes)==40
    files=['sim/masterpi_drive_friction.py','sim/masterpi_drive_friction_v2.py',
           'sim/masterpi_drive_friction_v6.py','sim/masterpi_drive_friction_v7.py',
           'sim/v7_exact_speedups.py','sim/masterpi_dynamics_v2.py',
           'sim/camera_robot_port.py','sim/multi_masterpi_production.py']
    result=dict(scope='static source + 40 saved scene XML; runtime damping not measured',
                source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},
                scenes=scenes,confirmed_damping_nm_s=P.damping_nm_s,
                hypothetical_total_damping_nm_s=P.torque_cap_nm/P.omega0,
                unexplained_difference_nm_s=P.torque_cap_nm/P.omega0-P.damping_nm_s,
                unexplained_difference_in_model=False,
                predictions=[dict(u=u,omega_over_omega0=wheel_speed(u)[0]/P.omega0,
                                  nominal_over_prediction=u/(wheel_speed(u)[0]/P.omega0),
                                  measured=False) for u in (.35,.4)])
    args.out.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
