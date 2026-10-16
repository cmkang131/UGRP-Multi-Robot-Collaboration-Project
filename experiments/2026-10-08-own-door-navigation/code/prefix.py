"""Additional exposure-matched comparison: legacy door logs end at pose loss.

The preregistered full-record gate is kept unchanged. No detector reruns.
"""
from offline import *


def main():
    result=[]
    spec=importlib.util.spec_from_file_location('visibility',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py');vis=importlib.util.module_from_spec(spec);spec.loader.exec_module(vis)
    for case in map(str,range(49001,49007)):
        ep=COHORT[case];p=load(RAW/case/'prediction.json');tr=rows(ep/'own-controller.jsonl');truth=rows(ep/'eval_only/trajectory.jsonl')
        loss=next((r['t'] for r in tr if r.get('status')=='unknown_start_reset'),None)
        own=[r for r in tr if r.get('pose') is not None and (loss is None or r['t']<loss)]
        origin=[*truth[0]['robot_xyz_m'][:2],truth[0]['robot_yaw_rad']];static=load(ep/'inputs/static_map.json');doors=static['passages']
        rects=np.array([r['center_m']+r['half_extents_m'] for r in static['obstacles'] if r.get('kind')=='wall'])
        cameras=[r for r in rows(ep/'eval_only/camera.jsonl') if loss is None or r['t']<loss];eligible=[]
        for i,d in enumerate(doors):
            axis=np.array([0,1]) if d['axis']=='x' else np.array([1,0]);c=np.array(d['center_m']);pts=[c-axis*d['width_m']/2,c+axis*d['width_m']/2]
            if any(vis.in_view(pts,[r],rects).all() for r in cameras):eligible.append(i)
        new=[d for d in p['tracks'] if loss is None or d['first_t']<loss]
        result.append(dict(case=case,loss_t=loss,prefix_frames=len(own),off=metrics(p['legacy_tracks'],doors,origin,eligible),on=metrics(new,doors,origin,eligible)))
    dump(EXP/'results/exposure-matched-prefix.json',dict(cases=result,qualification='secondary analysis only; unchanged full-record gate; legacy output absent after loss'))
    print([{k:r[k] for k in ('case','prefix_frames')}|{'off':(r['off']['tp'],r['off']['n']),'on':(r['on']['tp'],r['on']['n'])} for r in result])

if __name__=='__main__':main()
