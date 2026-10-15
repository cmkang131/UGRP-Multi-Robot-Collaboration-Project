"""GCP-only original-data diagnosis; no controller, physics or model calls."""
import hashlib,json,math,subprocess,sys
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path('/home/ugrp/ugrp-sim'); OPS=ROOT/'ops-reviews/beampair9'
def file(p):return p if p.exists() else Path(str(p)+'.zst')
def data(p):
    p=file(p);return subprocess.check_output(['zstd','-qdc',str(p)]) if p.suffix=='.zst' else p.read_bytes()
def read(p):return json.loads(data(p))
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def stats(values):
    return dict(zip(('min','p25','p50','p75','p95','max'),map(float,np.percentile(values,[0,25,50,75,95,100])))) if values else None

def main():
    assert sys.platform=='linux'
    OPS.mkdir(exist_ok=True); (OPS/'montages').mkdir(exist_ok=True)
    original=ROOT/'ops-reviews/beampair8/cohort-analysis-v2'
    summary=read(original/'summary.json'); table=read(original/'rejection_table.json')
    candidates=read(original/'candidate-rejections.json'); grouped=defaultdict(list)
    failed={r['seed']:r for r in summary['runs'] if not r['strict_success']}
    for c in candidates:
        if c['seed'] in failed:grouped[(c['reason_category'],c['blocked_object'])].append(c)
    distribution=[dict(reason_category=k[0],blocked_object=k[1],N=len(v),
        min_gap_m=min((x['min_gap_m'] for x in v if x['min_gap_m'] is not None),default=None),
        gap_distribution_m=stats([x['min_gap_m'] for x in v if x['min_gap_m'] is not None]),
        affected_seeds=sorted({x['seed'] for x in v})) for k,v in grouped.items()]
    distribution.sort(key=lambda x:-x['N'])
    write(OPS/'rejection_table-before.json',dict(table,failed15_reason_object_distribution=distribution,
        reproduce='python operations/analyze_before.py',raw_root=str(ROOT/'runs'),
        scope='200 original record runs; distribution below limited to15 failed/cap runs; not causal labels',
        original_table_sha256=hashlib.sha256(file(original/'rejection_table.json').read_bytes()).hexdigest()))
    rows=[]
    for seed,entry in failed.items():
        raw=Path(entry['raw']); result=read(raw/'result.json'); plan=read(raw/'plan.json')
        ev=[json.loads(x) for x in data(raw/'eval-only.jsonl').splitlines() if x.strip()]
        selected=[round(i*(len(ev)-1)/5) for i in range(6)]
        # Six actual native10Hz timestamps, both robot views; all processing on GCP.
        canvas=Image.new('RGB',(1280,3*272)); d=ImageDraw.Draw(canvas); frames=[]
        for k,i in enumerate(selected):
            for j,rid in enumerate(('r1','r2')):
                p=raw/'rgb'/rid/f'{i:06d}.jpg'
                canvas.paste(Image.open(p).convert('RGB').resize((320,240)),((k%2)*640+j*320,(k//2)*272))
                frames.append(dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),robot=rid,t=ev[i]['t']))
            d.text(((k%2)*640+4,(k//2)*272+242),f"{seed} SIM{ev[i]['t']-ev[0]['t']:.1f}: r1={plan['roles']['r1']} / r2={plan['roles']['r2']}",fill='white')
        out=OPS/'montages'/f'{seed}.jpg';canvas.save(out,quality=89)
        related=[c for c in candidates if c['seed']==seed]
        local=Counter((c['reason_category'],c['blocked_object']) for c in related)
        relation=[]
        for i in selected:
            row=ev[i];poses={r:row['robots'][r]['pose'] for r in ('r1','r2')}
            nearest={r:min(row['beam']['ends'],key=lambda end:math.dist(poses[r][:2],row['beam']['ends'][end][:2])) for r in poses}
            relation.append(dict(sim_s=row['t']-ev[0]['t'],peer_distance_m=math.dist(poses['r1'][:2],poses['r2'][:2]),
                nearest_ends=nearest,same_nearest_end=len(set(nearest.values()))==1,evaluator_only=True))
        teachers={r:{k:t.get(k) for k in ('phase','outcome','events','ready_log','alignment_log','goal_set_log','progress_log') if k in t}
            for r,t in result.get('teachers',{}).items()}
        # Full teacher diagnostics stay on GCP; compact terminal/candidate records travel to Mac.
        write(OPS/f'detail-{seed}.json',teachers)
        rows.append(dict(seed=seed,category=entry['category'],reason_category=entry['reason_category'],sim_s=entry['sim_s'],
            cap_type=('wall_planning_safety' if result.get('error') else 'sim_cap') if entry['cap_end'] else None,
            outcomes=entry['outcomes'],phases=entry['phases'],roles=plan['roles'],relation=relation,
            top_rejections=[dict(reason_category=k[0],blocked_object=k[1],N=n,
                min_gap_m=min((c['min_gap_m'] for c in related if (c['reason_category'],c['blocked_object'])==k and c['min_gap_m'] is not None),default=None)) for k,n in local.most_common(6)],
            montage=dict(path=str(out),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),frames=frames),raw=str(raw),
            result_sha256=hashlib.sha256(file(raw/'result.json').read_bytes()).hexdigest(),input_audit=result['input_audit']))
    gate=read(ROOT/'ops-reviews/beampair7/gate-plan.json')['episodes']
    record=[read(Path(r['raw'])/'plan.json') for r in summary['runs']]
    def describe(plans):
        vals=defaultdict(list)
        for e in plans:
            x,y,a=e['beam_pose']; vals['beam_x_m'].append(x); vals['beam_y_m'].append(y);vals['beam_yaw_deg'].append(math.degrees(a))
            vals['peer_distance_m'].append(math.dist(e['spawns']['r1'][:2],e['spawns']['r2'][:2]))
            for r,end in e['roles'].items():
                p=e['spawns'][r]; delta=.27 if end=='blue' else -.27
                ex,ey=x+delta*math.cos(a),y+delta*math.sin(a)
                vals['assigned_end_distance_m'].append(math.hypot(p[0]-ex,p[1]-ey))
                vals['assigned_end_bearing_deg'].append(abs(math.degrees(math.atan2(math.sin(math.atan2(ey-p[1],ex-p[0])-p[3]),math.cos(math.atan2(ey-p[1],ex-p[0])-p[3])))))
        return dict(N=len(plans),strata=dict(Counter((str(e['peer_case'])+':r1_'+e['roles']['r1']) for e in plans)),metrics={k:stats(v) for k,v in vals.items()})
    dist={k:describe(v) for k,v in [('gate40',gate),('record200',record),('failed15',[e for e in record if e['seed'] in failed])]}
    write(OPS/'before-summary.json',dict(N=summary['N'],n=summary['n'],teacher_failure_N=9,cap_end_N=6,HOST_ERROR_N=0,
        runs=rows,distribution=dist,cohort_pooling=False,source=str(original),
        scope='terminal categories, geometric rejection frequency and evaluator robot relationship; frequencies alone do not establish causes'))
    lines=['# beampair8 원본 거부 분포 (실패9 + cap_end6)','', '|사유 범주|막은 물체|검사 수|최소 틈 m|영향 시드 수|','|---|---|---:|---:|---:|']
    lines += [f"|{r['reason_category']}|{r['blocked_object']}|{r['N']}|{r['min_gap_m']}|{len(r['affected_seeds'])}|" for r in distribution]
    (OPS/'rejection-distribution.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(N=summary['N'],n=summary['n'],failed=list(failed),top=distribution[:6],distribution=dist)))

if __name__=='__main__':main()
