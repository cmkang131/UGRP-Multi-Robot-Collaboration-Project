"""gcp2-only saved-step evaluation; no simulation stepping or controller inputs."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--partial-evidence',action='store_true',help='default OFF: label and compare an incomplete candidate prefix')
    a=p.parse_args()
    from simalt_host import gcp2_identity
    gcp2_identity()
    import numpy as np
    import mujoco
    a.out.mkdir(parents=True,exist_ok=False)
    rm=json.loads((a.reference/'result.json').read_text())
    cm=json.loads((a.candidate/'result.json').read_text())
    if rm['status']!='complete' or (cm['status']!='complete' and not a.partial_evidence):raise RuntimeError('incomplete input')
    if rm['case']!=cm['case']:raise RuntimeError('case mismatch')
    if rm['fixture_sha256']!=cm['fixture_sha256']:raise RuntimeError('tape mismatch')
    r=np.load(a.reference/'steps.npz')['records'].astype(np.float64);c=np.load(a.candidate/'steps.npz')['records'].astype(np.float64)
    reference_rows=len(r);candidate_rows=len(c)
    complete=rm['status']=='complete' and cm['status']=='complete' and reference_rows==candidate_rows
    if a.partial_evidence:r=r[:min(reference_rows,candidate_rows)];c=c[:len(r)]
    if r.shape!=c.shape:raise RuntimeError('step shape mismatch')
    m=mujoco.MjModel.from_xml_path(str(a.fixture/'scene.xml'))
    nc=len(rm['columns']);dt=rm['dt'];n=len(r)
    ba=int(m.jnt_qposadr[m.body_jntadr[m.body('r1__robot').id]])
    box=int(m.jnt_qposadr[m.body_jntadr[m.body('cargo_cyan_2').id]])
    size=m.geom_size[m.geom('cargo_cyan_2_geom').id]
    def clearance(rows):
        q=rows[:,nc+box:nc+box+7];w,x,y,z=q[:,3:].T
        third=np.stack((2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)),axis=1)
        return q[:,2]-np.abs(third)@size
    def pose_error(b):
        translation=np.linalg.norm(r[:,nc+b:nc+b+3]-c[:,nc+b:nc+b+3],axis=1)
        rq=r[:,nc+b+3:nc+b+7];cq=c[:,nc+b+3:nc+b+7]
        dots=np.abs(np.sum(rq*cq,axis=1))/(np.linalg.norm(rq,axis=1)*np.linalg.norm(cq,axis=1))
        angle=np.rad2deg(2*np.arccos(np.clip(dots,0,1)))
        return translation,angle
    rc=clearance(r);cc=clearance(c)
    bd,br=pose_error(ba);od,orr=pose_error(box)
    def first(mask):
        ids=np.flatnonzero(mask)
        return {'step_1based':int(ids[0]+1),'SIM_s':float((ids[0]+1)*dt)} if len(ids) else None
    topology=np.any(r[:,[0,1,3,4,11]]!=c[:,[0,1,3,4,11]],axis=1)
    meta=json.loads((a.fixture/'fixture.json').read_text())
    phases=next(x['phases'] for x in meta['cases'] if x['name']==rm['case'])
    hold=np.array([i*400+399 for i,s in enumerate(phases) if s=='hold' and i*400+399<n],dtype=int)
    summary={'reference':str(a.reference),'candidate':str(a.candidate),'case':rm['case'],
        'steps':n,'dt':dt,'complete':complete,'reference_rows':reference_rows,'candidate_rows':candidate_rows,'candidate_status':cm['status'],'analysis_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'same_MuJoCo_version':rm['mujoco']==cm['mujoco'],
        'C_version':rm['mujoco'],'candidate_MuJoCo':cm['mujoco'],
        'physics_hashes_equal':rm['physics_hashes']==cm['physics_hashes'],
        'first_raw_qpos_difference':first(np.any(r[:,nc:nc+m.nq]!=c[:,nc:nc+m.nq],axis=1)),
        'first_contact_or_constraint_count_difference':first(topology),
        'topology_count_different_steps':int(topology.sum()),
        'first_pad_contact_presence_difference':first(np.any((r[:,3:5]>0)!=(c[:,3:5]>0),axis=1)),
        'first_reference_pad_contact':first(np.any(r[:,3:5]>0,axis=1)),
        'first_candidate_pad_contact':first(np.any(c[:,3:5]>0,axis=1)),
        'reference_max_ncon':int(r[:,0].max()),'candidate_max_ncon':int(c[:,0].max()),
        'reference_max_nefc':int(r[:,1].max()),'candidate_max_nefc':int(c[:,1].max()),
        'candidate_overflow_steps':int(np.count_nonzero(c[:,2])),
        'candidate_capacities':cm['capacities'],
        'base_endpoint_m':float(bd[-1]),'base_endpoint_deg':float(br[-1]),
        'box_endpoint_m':float(od[-1]),'box_endpoint_deg':float(orr[-1]),
        # User 2026-10-16 exploratory proposals, not new research acceptance constants.
        'endpoint_pass':bool(complete and bd[-1]<=.005 and br[-1]<=2 and od[-1]<=.005 and orr[-1]<=2),
        'reproduce':sys.argv,'force_semantics':'contact-frame normal and tangential resultant; force API after noslip; no controller feedback',
        'missing_distance_semantics':'zero if no penetrating contact; consult count before interpreting',
        'max_abs_difference_by_metric':{name:float(np.max(np.abs(r[:,i]-c[:,i]))) for i,name in enumerate(rm['columns'])}}
    if len(hold):
        summary['hold']={'samples':len(hold),'reference_bilateral':int(np.all(r[hold,3:5]>0,axis=1).sum()),
          'candidate_bilateral':int(np.all(c[hold,3:5]>0,axis=1).sum()),
          'reference_min_bottom_m':float(rc[hold].min()),'candidate_min_bottom_m':float(cc[hold].min()),
          'max_abs_height_difference_m':float(np.max(np.abs(rc[hold]-cc[hold]))),
          'reference_pad_force_min_N':r[hold,7:9].min(axis=0).tolist(),
          'candidate_pad_force_min_N':c[hold,7:9].min(axis=0).tolist(),
          'height_proposal_pass':bool(np.max(np.abs(rc[hold]-cc[hold]))<=.002)}
    header=['step_1based','SIM_s']+[label+'_'+s for label in ('C','candidate') for s in rm['columns']]+[
        'C_box_bottom_m','candidate_box_bottom_m','base_difference_m','base_difference_deg']
    csvpath=a.out/'every-step.csv'
    def row(i):return [i+1,(i+1)*dt,*r[i,:nc],*c[i,:nc],rc[i],cc[i],bd[i],br[i]]
    with csvpath.open('w') as out:
        writer=csv.writer(out);writer.writerow(header)
        for i in range(n):writer.writerow(row(i))
    rawhash=hashlib.sha256(csvpath.read_bytes()).hexdigest()
    subprocess.run(['zstd','-q','-f',str(csvpath)],check=True)
    restored=subprocess.check_output(['zstd','-dc',str(csvpath)+'.zst'])
    if hashlib.sha256(restored).hexdigest()!=rawhash:raise RuntimeError('CSV compression hash mismatch')
    csvpath.unlink()
    summary['every_step_table']={'path':str(csvpath)+'.zst','uncompressed_sha256':rawhash,
        'compressed_sha256':hashlib.sha256(Path(str(csvpath)+'.zst').read_bytes()).hexdigest(),'rows':n,'restored_hash_verified':True}
    indices=set(range(min(20,n)))|set(hold.tolist())
    for key in ('first_contact_or_constraint_count_difference','first_pad_contact_presence_difference',
                'first_reference_pad_contact','first_candidate_pad_contact'):
        if summary[key]:
            j=summary[key]['step_1based']-1;indices.update(range(max(0,j-5),min(n,j+6)))
    with (a.out/'step-excerpts.csv').open('w') as out:
        writer=csv.writer(out);writer.writerow(header)
        for i in sorted(indices):writer.writerow(row(i))
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
