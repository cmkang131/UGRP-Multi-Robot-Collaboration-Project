"""GCP saved-only carry scoring with the actual run's logged budget limits."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
from scripts.analyze_reloc13_carry import analyze as previous
from scripts.analyze_reloc11_selfmap import rows, obj


def analyze(folder):
    report=previous(folder);raw=folder/'raw'
    stop=obj(folder/'SUPERVISOR_STOP.json')
    if stop:
        report['supervisor_stop']=stop
        report['termination_category']='supervisor_stop'
        report['termination_reason']=stop.get('reason') or 'supervisor_stop_requires_review'
    elif not report.get('termination_reason'):
        report['termination_reason']='running' if report['status']=='running' else 'unclassified_requires_review'
    truth={round(r['t'],5):r for r in rows(raw/'eval-only.jsonl')}
    values=[]
    for r in rows(raw/'teacher-commands.jsonl'):
        m=r.get('map_pose',{});e=truth.get(round(r['t'],5),{});s=m.get('sigma_m_m_rad')
        if not s or e.get('map_pose_error_yaw_rad') is None:continue
        limits=m['budget_limits'];trigger=max(s[:2])>=limits['xy_m'] or s[2]>=limits['yaw_rad']
        values.append(dict(t=r['t'],phase=r['phase'],yaw_deg=abs(math.degrees(e['map_pose_error_yaw_rad'])),
            xy_m=e['map_pose_error_xy_m'],trigger=trigger))
    positives=[r for r in values if r['yaw_deg']>=20]
    report['pose_error'].update(true_yaw_over20_N=len(positives),
        trigger_recall=sum(r['trigger'] for r in positives)/len(positives) if positives else None,
        max_untriggered_yaw_deg=max((r['yaw_deg'] for r in values if not r['trigger']),default=None),
        missed_over20_by_phase=dict(Counter(r['phase'] for r in positives if not r['trigger'])))
    scene=(raw/'scene.xml').read_text() if (raw/'scene.xml').exists() else ''
    # Actual generated body names, not a claim inferred just from scenario ID.
    import xml.etree.ElementTree as ET
    bodies=[b.get('name','') for b in ET.fromstring(scene).iter('body')] if scene else []
    report['v7_scene_audit']=dict(heavy_crate_bodies=[b for b in bodies if b.startswith('cargo_') and 'crate' in b.lower()],
        static_fixture_crates=[b for b in bodies if b.startswith('warehouse_') and 'crate' in b.lower()],
        scenario_id=json.loads((raw/'plan.json').read_text()).get('scenario_id') if (raw/'plan.json').exists() else None)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('folders',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    runs=[analyze(f) for f in a.folders]
    a.output.write_text(json.dumps(dict(schema='ugrp.reloc14.carry.v1',analysis_host='gcp1',runs=runs,
        reproduce='PYTHONPATH=. .venv-sim/bin/python /tmp/analyze_reloc14_carry.py <folders> --output <file>'),indent=2)+'\n')
    for r in runs:print(json.dumps({k:r[k] for k in ('run','status','sim_s','funnel','physical_success','termination_reason','pose_error','v7_scene_audit')}))


if __name__=='__main__':main()
