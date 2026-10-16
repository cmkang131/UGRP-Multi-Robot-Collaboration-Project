"""gcp2-only saved RGB audit and strict component admission; no simulation."""
import argparse,hashlib,json,platform
from pathlib import Path
import numpy as np


def dist(values):
    values=[v for v in values if v is not None]
    return dict(N=len(values),**{k:float(np.percentile(values,q)) if values else None for k,q in [('min',0),('p10',10),('median',50),('p95',95),('max',100)]})


def analyze(root):
    manifest=json.loads((root/'SHA256SUMS.json').read_text())
    mismatch=[name for name,sha in manifest.items() if hashlib.sha256((root/name).read_bytes()).hexdigest()!=sha]
    rows=[json.loads((root/(name+'.json')).read_text()) for name in json.loads((root/'index.json').read_text())]
    changes=[dict(case=r['case'],cpu=r['metrics']['cpu']['colours'],mjwarp=r['metrics']['mjwarp']['colours']) for r in rows if r['metrics']['cpu']['colours']!=r['metrics']['mjwarp']['colours']]
    reports={}
    for backend in ('cpu','mjwarp'):
        rr=[r['metrics'][backend] for r in rows];b=[r['boundary'] for r in rr]
        reports[backend]=dict(orb={s:{'fast7':dist([r['orb'][s]['orb7'] for r in rr]),'fast20':dist([r['orb'][s]['orb20'] for r in rr])} for s in ('floor','wall')},
            boundary=dict(qualified=sum(x['qualified'] for x in b),columns=sum(x.get('columns') or 0 for x in b),false_columns=sum(x.get('false_columns') or 0 for x in b),
                per_frame=dist([x.get('columns') for x in b]),residual_px=dist([v for x in b for v in x.get('residuals_px',[])])),
            stall_static={k:dist([r['rgb_stall_static'].get(k) for r in rr]) for k in ('median_px','mean_abs_diff')},
            stall_one_pixel_yaw={k:dist([r['rgb_stall_one_pixel_yaw'].get(k) for r in rr]) for k in ('median_px','mean_abs_diff')})
    checks=dict(rendered88=len(rows)==88 and not mismatch,colour_semantic_counts_identical=not changes,
        no_new_false_boundary_columns=reports['mjwarp']['boundary']['false_columns']<=reports['cpu']['boundary']['false_columns'],
        boundary_columns_not_lost=reports['mjwarp']['boundary']['columns']>=reports['cpu']['boundary']['columns'])
    for s in ('floor','wall'):
        for q in ('p10','median'):
            checks[f'orb7_{s}_{q}_not_lost']=reports['mjwarp']['orb'][s]['fast7'][q]>=reports['cpu']['orb'][s]['fast7'][q]
    # Reuses scene-tex5's exact semantic count and p10/median signal comparisons.
    # This strict component gate is not E2E/pose/loaded-VO admission.
    alive=list(rows);funnel=[]
    filters=[('rendered',lambda r:True),('colour_semantics_equal',lambda r:r['metrics']['cpu']['colours']==r['metrics']['mjwarp']['colours']),
        ('no_false_boundary_increase',lambda r:(r['metrics']['mjwarp']['boundary'].get('false_columns') or 0)<=(r['metrics']['cpu']['boundary'].get('false_columns') or 0))]
    for name,fn in filters:
        before=len(alive);alive=[r for r in alive if fn(r)];funnel.append(dict(stage=name,cumulative_pass_n=len(alive),rejected_n=before-len(alive)))
    return dict(admitted=all(checks.values()),scope='paired static image components only; no motion/localization/E2E success',
        source=json.loads((root/'meta.json').read_text()),raw=str(root),N=len(rows),checks=checks,reports=reports,
        colour_changes=changes,colour_equal_n=len(rows)-len(changes),rgb_mae=dist([r['rgb_mae'] for r in rows]),
        verified_files=len(manifest),hash_mismatches=mismatch,funnel=funnel,
        rejections=[dict(category=k,reason=k,blocked_object='rendered_appearance',minimum_gap_m=None,gap_status='not_applicable',N=1) for k,v in checks.items() if not v],
        reproduction=['python','-m','scripts.analyze_warp5_render','--input',str(root)])


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if platform.system()!='Linux' or not platform.node().startswith(('ugrp-act-l4-gcp2','ugrp-sim-gcp2')):p.error('gcp2 saved-image analysis only')
    a.output.write_text(json.dumps(analyze(a.input),indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
