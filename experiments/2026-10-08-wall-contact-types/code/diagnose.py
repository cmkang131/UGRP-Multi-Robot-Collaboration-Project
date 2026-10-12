"""GT-only diagnosis of the sealed OFF actual columns, never estimator input.

Geometry-assisted operational labels, not a perfect simulator semantic buffer.
Peer per-link geometry is unavailable; envelopes are reported as unresolved.
"""
from common import *
import xml.etree.ElementTree as ET

CATEGORIES=('floor_checker','floor_colour','other_robot','box','door_opening','wall_tape','image_edge','other')

class Labels:
    def __init__(self,seed):
        self.ep=EPISODES[seed];self.seed=seed;self.K=modules()[0].K
        self.truth={round(r['t'],6):r for r in rows(self.ep/'eval_only/trajectory.jsonl')}
        self.camera={round(r['t'],6):r for r in rows(self.ep/'eval_only/camera.jsonl')}
        self.frames={f['frame_id']:f for f in rows(self.ep/'robots/r3/frames.jsonl')}
        self.setup=load(self.ep/'eval_only/setup.json')
        static=load(self.ep/'inputs/static_map.json')
        self.walls=np.array([w['center_m']+w['half_extents_m'] for w in static['obstacles'] if w.get('kind')=='wall'])
        self.doors=static['passages']
        root=ET.parse(self.ep/'scene.xml').getroot()
        self.zones=[]
        for e in root.findall('worldbody/geom'):
            if e.get('name','').startswith(('zone_area_','zone_slot_','zone_region_')):
                self.zones.append((np.fromstring(e.get('pos'),sep=' '),np.fromstring(e.get('size'),sep=' ')))
        self.support=(modules()[0].undistort(np.full((480,640,3),255,np.uint8))==255).all(2)
        self.support=cv2.erode(self.support.astype(np.uint8),np.ones((5,5),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0).astype(bool)

    def surface(self,origin,rays,truth):
        with np.errstate(divide='ignore',invalid='ignore'):hit=np.where(rays[:,2]<0,-origin[2]/rays[:,2],np.inf)
        sem=np.full(len(rays),'floor',object)
        for x,y,hx,hy in self.walls:
            d=first_box(origin,rays,[x-hx,y-hy,0],[x+hx,y+hy,.4])
            mask=d<hit;hit[mask]=d[mask];sem[mask]='wall'
        R=np.array(truth['cyan_rotation']).reshape(3,3);c=np.array(truth['cyan_xyz_m']);h=np.array(truth['box_half_m'])
        d=first_box((origin-c)@R,rays@R,-h,h);mask=d<hit;hit[mask]=d[mask];sem[mask]='box'
        for rid,spawn in self.setup['spawns'].items():
            if rid=='r3':continue
            x,y=spawn[:2];d=first_box(origin,rays,[x-.2,y-.18,0],[x+.2,y+.18,.4])
            mask=d<hit;hit[mask]=d[mask];sem[mask]='peer_envelope'
        return sem,origin+np.where(np.isfinite(hit),hit,0)[:,None]*rays

    def classify(self,row):
        t=round(row['t'],6);truth=self.truth[t];cam=self.camera[t]
        uv=np.array(row['uv']).reshape(-1,2);local=np.array(row['points']).reshape(-1,2)
        body=transform(local,[*truth['robot_xyz_m'][:2],truth['robot_yaw_rad']])
        errors=metric.boundary_dist(body,self.walls);bad=errors>.15
        if not bad.any():return [],errors.tolist()
        origin=np.array(cam['camera_xyz']);rot=np.array(cam['camera_rotation']).reshape(3,3)@np.diag([1,-1,-1])
        und=modules()[0].undistort(cv2.cvtColor(rgb(self.ep,self.frames[row['frame_id']]),cv2.COLOR_RGB2BGR))
        hsv=cv2.cvtColor(und,cv2.COLOR_BGR2HSV);grey=cv2.cvtColor(und,cv2.COLOR_BGR2GRAY)
        out=[]
        for i in np.flatnonzero(bad):
            u,v=uv[i];ui,vi=round(u),round(v)
            pixels=np.array([[u,v],[u,v-3],[u,v+3],[u-3,v],[u+3,v]])
            rays=np.c_[pixels,np.ones(5)]@np.linalg.inv(self.K).T@rot.T
            sem,hits=self.surface(origin,rays,truth)
            ray=rays[0]
            plane=origin-origin[2]*ray/ray[2] if ray[2]<0 else None
            actual_error=float(metric.boundary_dist(plane[None,:2],self.walls)[0]) if plane is not None else None
            clipped=not (2<=ui<638 and 3<=vi<477) or not self.support[max(0,min(479,vi)),max(0,min(639,ui))]
            patch=grey[max(0,vi-6):min(480,vi+7),max(0,ui-3):min(640,ui+4)]
            saturation=hsv[max(0,vi-6):min(480,vi+7),max(0,ui-3):min(640,ui+4),1]
            doorway=False
            if sem[0]=='floor' and 'wall' in sem[3:]:
                for door in self.doors:
                    if door['kind']!='door':continue
                    x,y=door['center_m'];hx,hy=door['half_extents_m']
                    d=first_box(origin,rays[:1],[x-hx,y-hy,0],[x+hx,y+hy,.4])[0]
                    doorway|=bool(np.isfinite(d) and d<np.linalg.norm(hits[0]-origin)/np.linalg.norm(ray))
            subtype=None
            if clipped:category='image_edge';subtype='remap_support_or_clipped_contact'
            elif actual_error is not None and actual_error<=.15:category='other';subtype='camera_projection_residual'
            elif 'peer_envelope' in sem:category='other';subtype='peer_envelope_unresolved'
            elif 'box' in sem:category='box'
            elif doorway:category='door_opening'
            elif sem[0]=='wall' and hits[0,2]>.015 and patch.min()<40 and patch.max()-patch.min()>6:
                category='wall_tape'
            elif all(s=='floor' for s in sem):
                category='floor_colour' if saturation.max()>80 else 'floor_checker'
            elif 'wall' in sem and 'floor' in sem:
                category='other';subtype='wall_contact_projection_or_mixed_edge'
            else:category='other';subtype='unresolved_wall_or_background'
            out.append(dict(frame_id=row['frame_id'],t=row['t'],column=row['columns'][i],uv=uv[i].tolist(),
                local=local[i].tolist(),gt_body_error_m=float(errors[i]),actual_camera_plane_error_m=actual_error,
                category=category,subtype=subtype,surface_band=sem.tolist(),surface_xyz=hits.tolist()))
        return out,errors.tolist()

def diagnose(seed):
    folder=RAW/seed/'off';seal=load(folder/'seal.json');assert sha(folder/'points.jsonl')==seal['files']['points.jsonl']
    path=RAW/seed/'diagnosis.json'
    if path.exists():raise FileExistsError(path)
    label=Labels(seed);allrows=rows(folder/'points.jsonl');records=[];errors=[];perframe=[]
    expected=load(label.ep/'artifacts.sha256.json')
    for name in ('eval_only/trajectory.jsonl','eval_only/camera.jsonl','eval_only/setup.json','scene.xml','inputs/static_map.json'):
        assert sha(label.ep/name)==expected[name]
    inserted={r['frame_id'] for r in load(label.ep/'graph.json')['ledger']}
    for j,row in enumerate(allrows):
        bad,err=label.classify(row);records.extend(bad);errors.extend(err)
        perframe.append(dict(frame_id=row['frame_id'],points=len(err),false_points=len(bad),categories=dict(Counter(b['category'] for b in bad))))
        if j%200==0:print(seed,'diagnose',j,flush=True)
    summary={}
    for name,subset,n in [('all',records,len(errors)),('inserted',[r for r in records if r['frame_id'] in inserted],sum(len(r['points']) for r in allrows if r['frame_id'] in inserted))]:
        counts=Counter(r['category'] for r in subset)
        summary[name]=dict(points=n,false_points=len(subset),precision=1-len(subset)/n if n else None,
            categories={c:dict(count=counts[c],fraction=counts[c]/len(subset) if subset else None) for c in CATEGORIES},
            subtypes=dict(Counter(r['subtype'] for r in subset if r['subtype'])))
    dump(path,dict(seed=seed,summary=summary,frames=perframe,false_points=records,off_point_rmse_m=float(np.sqrt(np.mean(np.square(errors)))),
        sources={n:sha(label.ep/n) for n in ('eval_only/trajectory.jsonl','eval_only/camera.jsonl','eval_only/setup.json','scene.xml','inputs/static_map.json')},source_sha=head()))
    dump(EXP/f'results/{seed}-diagnosis.json',dict(seed=seed,summary=summary,frames=len(allrows),inserted_frames=len(inserted),
        rmse_m=float(np.sqrt(np.mean(np.square(errors)))),raw_path=str(path),sha256=sha(path)))
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('seed',choices=EPISODES);a=p.parse_args();diagnose(a.seed)
