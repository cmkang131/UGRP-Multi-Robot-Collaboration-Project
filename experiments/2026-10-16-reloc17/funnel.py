"""GCP2-only recount of saved frames; no runtime/control imports or mutations."""
import collections,csv,hashlib,json,math,platform,subprocess
from pathlib import Path
import numpy as np
ROOT=Path('/home/ugrp/ugrp-sim/runs')
OUT=ROOT/'reloc17-investigation'

def read(path):
    p=Path(path)
    if p.exists():b=p.read_bytes()
    else:b=subprocess.check_output(['zstd','-dqc',str(p)+'.zst'])
    return [json.loads(x) for x in b.splitlines() if x.strip()]

def quant(xs):
    return dict(N=len(xs),**({k:float(v) for k,v in zip(('p0','p50','p95','p100'),np.percentile(xs,[0,50,95,100]))} if xs else {}))

def main():
    assert platform.node().startswith('ugrp-sim-gcp2')
    OUT.mkdir(exist_ok=True)
    reports=[];frame_rows=[]
    for n in (1,2,3):
        queue=json.loads((ROOT/f'reloc16-round{n}/queue.json').read_text())
        for task in queue['runs']:
            if task['kind']!='selfmap':continue
            raw=Path(task['raw']);result=json.loads((raw/'result.json').read_text())
            if not result.get('frames'):continue
            rows=read(raw/'trace.jsonl');counts=collections.Counter();reject=collections.Counter();ind=collections.Counter()
            detail=collections.defaultdict(list);files={}
            for name in ('trace.jsonl','result.json','eval_only/trajectory.jsonl'):
                p=raw/name;p=p if p.exists() else Path(str(p)+'.zst')
                files[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
            for row in rows:
                s=row.get('static_registration',{});g=s.get('geometry',{});d=s.get('reloc10_diagnostics',{});a=g.get('ambiguity',{})
                c=np.asarray(s.get('raw_covariance',s.get('covariance')),float)
                rawxy=float(np.sqrt(max(0.,np.linalg.eigvalsh(c[:2,:2]).max())))
                rawyaw=float(math.degrees(math.sqrt(max(0.,c[2,2]))))
                features=d.get('feature_kinds',{});land=sum(features.values())
                checks=[('frames',True),('detected',land>0 or d.get('wall_segments',0)>0),
                    ('sensor_update',bool(s.get('updated'))),('pf_resolved',bool(s.get('pf_resolved',s.get('resolved')))),
                    ('dominant_mode',s.get('cluster',{}).get('mass',0)>=.9),
                    ('raw_covariance',rawxy<=.15 and rawyaw<=5),
                    ('correspondence_nis',g.get('supported_floor_lines',0)>0),
                    ('geometry_axes',bool(g.get('independent_line_axes'))),
                    ('global_unique',bool(a.get('evaluated') and a.get('unique'))),
                    ('pf_geometry_agreement',bool(s.get('resolved'))),
                    ('three_views',s.get('confirmations',0)>=3),('registered',bool(s.get('registered')))]
                ok=True;first=None
                for name,pass_ in checks:
                    ind[name]+=bool(pass_)
                    if ok and not pass_:first=name;reject[name]+=1
                    ok=ok and pass_;counts[name]+=ok
                sensor=s.get('pf_sensor') or {}
                for key,val in [('raw_xy_sigma_m',rawxy),('raw_yaw_sigma_deg',rawyaw),('cluster_mass',s.get('cluster',{}).get('mass',0)),('injected',sensor.get('injected',0)),('recovery_probability',sensor.get('injection_probability',0)),('raw_columns',d.get('raw_columns') or 0),('fitted_columns',d.get('fitted_columns') or 0)]:detail[key].append(val)
                frame_rows.append(dict(run=task['name'],t=row['t'],first_rejection=first or 'accepted',**{k:int(v) for k,v in checks},raw_xy_sigma_m=rawxy,raw_yaw_sigma_deg=rawyaw,landmark_features=land,wall_segments=d.get('wall_segments',0),injected=sensor.get('injected',0),recovery_probability=sensor.get('injection_probability',0),actual_registered=int(bool(s.get('registered')))))
            reports.append(dict(round=n,seed=task['seed'],scene=task['scene'],run=task['name'],raw=str(raw),source_sha=task['source_sha'],
                cumulative=dict(counts),independent=dict(ind),first_rejections=[dict(category=k,N=v,blocked_object='static_registration_evidence',minimum_gap_m=None,gap_status='not_applicable_localization_gate') for k,v in reject.items()],
                distribution={k:quant(v) for k,v in detail.items()},sha256=files,
                note='Sequential acquisition funnel; registered is independently latched after acquisition. Tracking frames have separate independent counts. Correspondences are instrumented separately where packet supports replay.'))
    with (OUT/'funnel-frames.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(frame_rows[0]));writer.writeheader();writer.writerows(frame_rows)
    data=dict(schema='ugrp.reloc17.funnel.v1',analysis_host='gcp2',runs=reports,reproduction='PYTHONPATH=. /home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python experiments/2026-10-16-reloc17/funnel.py',frame_table=str(OUT/'funnel-frames.csv'))
    (OUT/'rejection-table.json').write_text(json.dumps(data,indent=2)+'\n')
    lines=['# reloc17 원본 프레임 관문 재집계','', '|실행|프레임→검출→갱신→PF resolved→mode→raw P→대응 NIS→기하축→유일→PF 일치→3뷰→수용|독립 registered|','|---|---|---:|']
    keys=['detected','sensor_update','pf_resolved','dominant_mode','raw_covariance','correspondence_nis','geometry_axes','global_unique','pf_geometry_agreement','three_views','registered']
    for r in reports:lines.append('|'+r['run']+'|'+str(r['cumulative']['frames'])+' → '+' → '.join(str(r['cumulative'][k]) for k in keys)+'|'+str(r['independent']['registered'])+'|')
    lines+=['','원본과 해시·사유별 거부·독립 통과 수는 rejection-table.json, 프레임별 값은 funnel-frames.csv.','기하/대응은 PF와 독립 계산되며 위 표는 비교용 순차 투영이다. PF가 막힌 뒤의 독립 통과를 수용으로 세지 않는다.']
    (OUT/'funnel.md').write_text('\n'.join(lines)+'\n')
    print('\n'.join(lines))

if __name__=='__main__':main()
