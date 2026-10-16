"""Read only the explicitly supplied completed short-check folder."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np


def summary(root):
    result = json.loads((root/'summary.json').read_text())
    if result['status'] != 'HEADLESS_CHECK_COMPLETE':
        raise ValueError('short check incomplete')
    manifest = json.loads((root/'artifacts.sha256.json').read_text())
    for name, digest in manifest.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
            raise ValueError('changed input: '+name)
    read = lambda name: [json.loads(line) for line in (root/name).read_text().splitlines()]
    trace, contacts = read('eval_only/trajectory.jsonl'), read('eval_only/contacts.jsonl')
    geoms = [g for g in ET.parse(root/'scene.xml').find('.//body[@name="cargo_beam"]').findall('geom')
             if g.get('contype', '1') != '0']
    assert len(geoms) == 1 and geoms[0].get('type') == 'box'
    geom = geoms[0]
    size = np.fromstring(geom.get('size'), sep=' ')
    pos = np.fromstring(geom.get('pos', '0 0 0'), sep=' ')
    wanted = {rid+'__'+side+'_finger' for rid in ('r1', 'r2') for side in ('left', 'right')}
    rows = []
    assert len(trace) == len(contacts)
    for tr, cr in zip(trace, contacts):
        assert abs(tr['t']-cr['t']) < 1e-7
        rotation = np.asarray(tr['beam_rotation']).reshape(3, 3)
        bottom = tr['beam_xyz_m'][2]+(rotation@pos)[2]-np.abs(rotation[2])@size
        touched = set()
        for contact in cr['contacts']:
            if geom.get('name') in (contact['geom1'], contact['geom2']) and contact['dist_m'] <= 0:
                touched.add(contact['geom2'] if contact['geom1'] == geom.get('name') else contact['geom1'])
        reason = ('weld' if cr['active_weld_ids'] else 'not_lifted' if bottom < .01 else
                  'external_support' if touched-wanted else 'missing_bilateral_grip' if not wanted <= touched else 'lifted')
        rows.append({'t': round(tr['t']-trace[0]['t'], 6), 'bottom_m': float(bottom), 'reason': reason})
    intervals = [(8., 10.), (10., 27.2), (27.2, 34.), (34., 47.6), (47.6, 49.), (49., 52.0001)]
    reports = []
    for a, z in intervals:
        selected = [r for r in rows if a <= r['t'] < z]
        reports.append({'interval_s': [a, z], 'samples': len(selected),
                        'reasons': dict(collections.Counter(r['reason'] for r in selected)),
                        'bottom_min_m': min(r['bottom_m'] for r in selected)})
    out = {'source_sha': result['source_sha'], 'raw_root': str(root.resolve()),
           'raw_manifest_sha256': hashlib.sha256((root/'artifacts.sha256.json').read_bytes()).hexdigest(),
           'all_samples': len(rows), 'all_reasons': dict(collections.Counter(r['reason'] for r in rows)),
           'intervals': reports, 'geometry': result['geometry'],
           'loadavg_start': result['loadavg_start'], 'loadavg_end': result['loadavg_end'],
           'scope': '52 SIM초 준비 상태 진단. 학생 RGB 실행·실측 보정·전체 운반 인수 아님',
           'joint_limits': result['command_joint_limits'], 'kinematics': result['kinematics'],
           'sim_s': result['sim_s'], 'commands': result['commands'], 'model_calls': result['model_calls']}
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('raw', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    with args.output.open('x') as f:
        json.dump(summary(args.raw), f, ensure_ascii=False, indent=2)
        f.write('\n')
