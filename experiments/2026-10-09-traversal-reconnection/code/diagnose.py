"""Post-seal audit only. Never imported by the controller or predictor."""
import math
from collections import Counter
import numpy as np
from offline import legacy,RAW,EXP
from harness.self_pose_graph import between,wrap
load,rows,dump,sha=legacy.load,legacy.rows,legacy.dump,legacy.sha


def main():
    reports=[]
    for seed in range(49001,49007):
        out=RAW/str(seed)
        assert sha(out/'prediction.json')==load(out/'seal.json')['sha256']
        p=load(out/'prediction.json');g=p['graph'];r=load(EXP/'results'/f'{seed}.json')
        old=load(EXP.parent/'2026-10-09-own-traversal-return/results'/f'{seed}.json')
        truth=rows(legacy.BASE/f'seed{seed}/eval_only/trajectory.jsonl')
        times=np.array([v['t'] for v in truth]);gt=np.array([[*v['robot_xyz_m'][:2],v['robot_yaw_rad']] for v in truth])
        accepted=[]
        for e in g['reconnections']:
            if not e['accepted']:continue
            a,b=[g['nodes'][e[k]] for k in ('a','b')]
            ia,ib=[int(np.argmin(abs(times-n['t']))) for n in (a,b)]
            assert max(abs(times[ia]-a['t']),abs(times[ib]-b['t']))<.101
            actual=between(gt[ia],gt[ib]);estimate=np.array(e['relative_pose'])
            accepted.append(dict(a=e['a'],b=e['b'],kind=e['kind'],t=e['t'],
                gt_xy_error_m=float(np.linalg.norm(estimate[:2]-actual[:2])),
                gt_yaw_error_deg=abs(float(wrap(estimate[2]-actual[2])))*180/math.pi,
                score=e['score'],overlap=e['overlap'],residual_m=e['residual_m']))
        candidates=[]
        if p['match']:
            for c in p['match']['candidate_attempts']:
                candidates.append({k:c[k] for k in ('node','node_distance_m','node_heading_difference_deg','reason','overlap','residual_m','hessian_eigenvalues') if k in c})
        counts={kind:dict(Counter(e['reason'] for e in g['reconnections'] if e['kind']==kind)) for kind in ('recovery_bridge','place_recognition')}
        audit={label:{k:sum(e[label][k] for e in r['edges_audit']) for k in ('center_crossing_segments','center_segments','footprint_overlap_samples','footprint_samples')} for label in ('estimated','actual')}
        reports.append(dict(seed=seed,frames=r['frames'],retained_frames=g['retained_frames'],
            old_nodes=old['nodes'],nodes=r['nodes'],old_components=old['components'],components=r['components'],edges=r['edges'],
            B_node=r['B_node'],B_component_size=r['B_component_size'],last_component_size=r['last_component_size'],
            route=r['route_exists'],selected_route=r['selected_route'],first_match=None if p['match'] is None else p['match']['reason'],
            candidate_attempts=candidates,reconnection_reasons=counts,accepted_constraint_audit=accepted,
            all_edges_audit=audit,cache=g['cache'],unfinished_gap=g['unfinished_gap'],seal=r['seal']))
    dump(EXP/'results/diagnosis.json',reports)
    totals=dict(cases=len(reports),prefix_frames=sum(r['frames'] for r in reports),
        old_nodes=sum(r['old_nodes'] for r in reports),nodes=sum(r['nodes'] for r in reports),
        old_components=sum(r['old_components'] for r in reports),components=sum(r['components'] for r in reports),
        accepted=sum(len(r['accepted_constraint_audit']) for r in reports),
        reasons={k:dict(sum((Counter(r['reconnection_reasons'][k]) for r in reports),Counter())) for k in ('recovery_bridge','place_recognition')},
        qualification='GT read only after all predictions sealed; geometry of all edges is not a selected B route')
    dump(EXP/'results/totals.json',totals)
    print(totals)


if __name__=='__main__':main()
