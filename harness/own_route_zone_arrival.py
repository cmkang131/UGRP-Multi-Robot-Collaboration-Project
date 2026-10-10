"""Observed-cell B arrival and nearest material hue; default identity.

Only own RGB, frozen class appearance, stored observed cells and own pose.
No map coordinates/scene state/GT. Partial observed extent stays partial.
"""
import copy
import math
from types import MethodType
import cv2
import numpy as np

ARRIVAL = 'remembered_cells_v1'
COLOR = 'nearest_material_hue_v1'
# Appearance specifications only (not positions, region IDs or scene queries).
# sim/zone_masterpi_v3_scene.py palette: blue B vs blue pickup floor.
PALETTE = {'B': [.20,.40,.95], 'pickup': [.12,.36,.70]}


def hue_distance(a,b):
    d=np.abs(a-b)
    return np.minimum(d,180-d)


def classify(rgb,region):
    hue=cv2.cvtColor(np.asarray(rgb),cv2.COLOR_RGB2HSV)[...,0][region].astype(float)
    if not len(hue):return dict(accepted=False,reason='empty_component')
    # Equal-prior nearest class hue; midpoint is determined by appearance specs,
    # not fit to these six evaluation seeds. Existing v3 metric gates stay.
    prototypes={k:float(cv2.cvtColor(np.array([[v]],np.float32),cv2.COLOR_RGB2HSV)[0,0,0]/2)
                for k,v in PALETTE.items()}
    distances={k:float(np.median(hue_distance(hue,v))) for k,v in prototypes.items()}
    accepted=distances['B']<distances['pickup']
    return dict(accepted=accepted,reason='B_nearest_hue' if accepted else 'pickup_or_ambiguous_hue',
        median_hue=float(np.median(hue)),distances=distances,prototypes=prototypes,pixels=len(hue))


def filter_components(rgb,patches,labels):
    accepted=[];out=np.zeros_like(labels);records=[]
    for p in patches:
        region=labels==p['component'];r=classify(rgb,region);records.append(r)
        if r['accepted']:
            q=copy.deepcopy(p);q['component']=len(accepted)+1;q['color_confirmation']=r
            out[region]=q['component'];accepted.append(q)
    return accepted,out,records


def observed_inside(c,pose):
    entity=c.entities.get('B')
    if not entity or entity.get('quarantined'):return False,0
    candidate=entity.get('observation',{}).get('candidate_id')
    track=next((x for x in c.explorer.goal.tracks if x['id']==candidate and x['confirmed_t'] is not None),None)
    if track is None:return False,0
    cell=tuple(np.floor(np.asarray(pose[:2])/c.explorer.goal.options.cell_m).astype(int))
    return cell in track['cells'],len(track['cells'])


def install(c,*,arrival_zone='off',B_color_confirmation='off',prefix_rgb=None,prefix_servo=None):
    if arrival_zone=='off' and B_color_confirmation=='off':return c
    if arrival_zone not in ('off',ARRIVAL) or B_color_confirmation not in ('off',COLOR):
        raise ValueError('UNKNOWN_ZONE_OPTION')
    c._zone_calls=0;c._zone_rows=[];c._color_rows=[];c._zone_streak=0;c._legacy_streak=0
    c._legacy_declared=None;c._zone_declared=None;c._zone_last=None
    base_receive,base_arrival,base_entity,base_select=c.receive,c._arrival,c._entity,c._select
    pending_quarantine=False
    if B_color_confirmation!='off':
        if prefix_rgb is None:raise ValueError('PREFIX_OWN_RGB_REQUIRED')
        original=c.explorer.goal.detector
        def detector(rgb,**kw):
            patches,labels,diag=original(rgb,**kw)
            patches,labels,records=filter_components(rgb,patches,labels)
            c.labels=labels;c.current_patches=patches
            c._color_rows.extend(dict(t=c.explorer.goal.last_t,**r) for r in records)
            return patches,labels,{**diag,'material_rejected':sum(not r['accepted'] for r in records)}
        c.explorer.goal.detector=detector
        # Revalidate causally stored first-confirmation RGB, never evaluation RGB.
        patches,labels,_=original(prefix_rgb,servo=prefix_servo,profile='camera_v3',options=c.explorer.goal.options)
        candidate=c.entities['B']['observation']['candidate_id']
        track=next(x for x in c.explorer.goal.tracks if x['id']==candidate)
        # Projected metric association identifies the remembered component.
        from harness.self_odom_grid import transform
        pose=c.explorer.memory.self_map.odom.pose
        nearest=min(patches,key=lambda p:math.dist(transform([p['center_body_m']],pose)[0],track['last_center']),default=None)
        r=classify(prefix_rgb,labels==nearest['component']) if nearest else dict(accepted=False,reason='prefix_component_not_visible')
        c._color_rows.append(dict(scope='prefix',**r));pending_quarantine=not r['accepted']

        def entity(self,name,*args,**kw):
            return base_entity(name,*args,**kw)
        c._entity=MethodType(entity,c)

    def select(self,t):
        # This registered task is B then return; quarantine must not silently
        # turn the task into box approach while searching for a valid B.
        if B_color_confirmation!='off' and 'B' not in self.entities and 'B' not in self.reached:
            self.active=None;self.stage='explore';return
        return base_select(t)

    def arrival(self,t,frame_id,pose,box_visible):
        if self.active!='B':return base_arrival(t,frame_id,pose,box_visible)
        near=math.dist(pose[:2],self.entities['B']['center_m'])<=.20
        fresh=any(p.get('confirmed_t') is not None for p in self.current_patches)
        lower=0 if self.labels is None else int(np.count_nonzero(self.labels[2*self.labels.shape[0]//3:]))
        legacy=near and fresh and lower>=self.explorer.goal.options.min_pixels
        self._legacy_streak=self._legacy_streak+1 if legacy else 0
        if self._legacy_streak>=5 and self._legacy_declared is None:self._legacy_declared=t
        inside,n=observed_inside(self,pose)
        self._zone_streak=self._zone_streak+1 if inside else 0
        self._zone_last=dict(t=t,frame_id=frame_id,inside=inside,observed_cells=n,legacy_eligible=bool(legacy),
            legacy_streak=self._legacy_streak,zone_streak=self._zone_streak,pose=list(map(float,pose)),
            legacy_declared_t=self._legacy_declared)
        self._zone_rows.append(self._zone_last.copy())
        if arrival_zone=='off':return base_arrival(t,frame_id,pose,box_visible)
        if self._zone_streak<5:return
        self._zone_declared=t
        self.reached['B']=dict(t=t,frame_id=frame_id,pose=list(map(float,pose)),node=self.graph.anchor,
            criterion=ARRIVAL,observed_cells=n,legacy_also_satisfied=self._legacy_declared is not None)
        self.graph.nodes[self.graph.anchor]['entities'].append(dict(kind='B_reached',**self.reached['B']))
        self.cues.append(dict(kind='B_reached',**self.reached['B']))
        self.event(t,'goal_reached',entity='B',frame_id=frame_id,pose=list(map(float,pose)),criterion=ARRIVAL)
        self.active=None;self.streak=0;self.leg_start=t;self.stage='explore'

    def receive(**kw):
        nonlocal pending_quarantine
        c._zone_calls+=1
        if pending_quarantine:
            old=c.entities.pop('B');candidate=old['observation']['candidate_id']
            for tr in c.explorer.goal.tracks:
                if tr['id']==candidate:tr['confirmed_t']=None
            c.event(kw['t'],'remembered_B_quarantined',source='own_prefix_rgb',entity=old)
            c.active=None;c.stage='explore';c.navigator.reset_action();c.navigator.target=None
            c.explorer.goal_target=None
            pending_quarantine=False
        cmd,tr=base_receive(**kw)
        tr['zone_arrival']=dict(calls=c._zone_calls,receive_executed=True,arrival_zone=arrival_zone,
            B_color_confirmation=B_color_confirmation,last=copy.deepcopy(c._zone_last),
            legacy_declared_t=c._legacy_declared,zone_declared_t=c._zone_declared)
        c.last_trace=copy.deepcopy(tr)
        return cmd,tr
    c._select=MethodType(select,c);c._arrival=MethodType(arrival,c);c.receive=receive
    return c
