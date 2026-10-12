"""Evaluation-only potential visible contact recall. No simulator imports."""
from common import *
sys.path.insert(0,str(ROOT/'experiments/2026-10-08-wall-contact-types/code'))
from diagnose import Labels


class ContactRecall:
    def __init__(self,seed):
        self.labels=Labels(seed);self.cache={}
        expected=load(self.labels.ep/'artifacts.sha256.json')
        for n in ('eval_only/trajectory.jsonl','eval_only/camera.jsonl','eval_only/setup.json','scene.xml','inputs/static_map.json'):
            assert sha(self.labels.ep/n)==expected[n]

    def targets(self,row):
        frame=row['frame_id']
        if frame in self.cache:return self.cache[frame]
        label=self.labels;cam=label.camera[round(row['t'],6)]
        mp,hfw,_=modules();columns=mp.column_positions(96,2)
        origin=np.array(cam['camera_xyz'])
        rotation=np.array(cam['camera_rotation']).reshape(3,3)@np.diag([1,-1,-1])
        cm=mp.ColumnModel((),0.,columns,camera_transform=(origin,rotation))
        distances=np.full(len(columns),np.inf)
        for x,y,hx,hy in label.walls:
            hit=first_box(cm.q0,cm.d,[x-hx,y-hy],[x+hx,y+hy])
            distances=np.minimum(distances,np.where(hit>0,hit,np.inf))
        finite=np.isfinite(distances)
        safe=np.where(finite,distances,0.)
        xy=cm.floor_point(safe);v=cm.rows(safe)
        visible=finite & np.isfinite(v) & (v>=3) & (v<mp.HEIGHT-3)
        visible &= np.linalg.norm(xy-origin[:2],axis=1)<4.
        f=label.frames[frame];servo={int(k):v for k,v in f['commanded_servo'].items()}
        own_o,own_r=camera_transform(servo)
        own_cm=mp.ColumnModel(tuple(sorted(servo.items())),0.,columns,camera_transform=(own_o,own_r))
        und=mp.undistort(cv2.cvtColor(rgb(label.ep,f),cv2.COLOR_RGB2BGR))
        self_top=hfw.self_top_mask(und,own_cm,loaded=False)
        visible &= v<=self_top-hfw.PARAMS['self_margin_px']-1
        vi=np.rint(np.nan_to_num(v,nan=0.)).astype(int).clip(0,mp.HEIGHT-1)
        visible &= label.support[vi,columns.astype(int)]
        target=np.c_[xy,np.zeros(len(xy))]
        rays=target-origin
        _,first=label.surface(origin,rays,label.truth[round(row['t'],6)])
        visible &= np.linalg.norm(first-origin,axis=1)>=np.linalg.norm(rays,axis=1)-1e-5
        self.cache[frame]=(xy,visible)
        return xy,visible

    def measure(self,row,world_points):
        target,visible=self.targets(row)
        col=np.asarray(row['columns'],int)
        success=visible[col] & (np.linalg.norm(world_points-target[col],axis=1)<=.15)
        return int(visible.sum()),int(success.sum())
