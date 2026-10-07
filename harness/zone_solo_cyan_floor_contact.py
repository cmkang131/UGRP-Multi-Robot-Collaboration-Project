"""Default-off S2 floor-appearance veto, Ulrich/Nourbakhsh AAAI 2000 §§4–6.

Fixed regular-mode H/I histograms ORed across manually reviewed own-RGB
floor references. A floor/floor edge is missing wall data, not a new obstacle.
No GT, map position, particle prior, camera/physics change, or online training.
"""
import copy
import cv2
import numpy as np
from harness.zone_solo_cyan_observed_amcl import Runtime as Previous, OPTION as OBSERVED

OPTION='floor_appearance_v1'
PARAMS=dict(gaussian_kernel=5,histogram_bins=256,histogram_window=5,
    hue_count_threshold=60,intensity_count_threshold=80,min_intensity=10/255,min_saturation=.1)


def features(und_bgr):
    """Paper HSI (I=mean RGB); invalid hue never rejects grey floor."""
    image=cv2.GaussianBlur(und_bgr,(5,5),0)
    b,g,r=np.moveaxis(image.astype(np.float64)/255.,-1,0)
    intensity=(r+g+b)/3
    sat=1-np.minimum(np.minimum(r,g),b)/np.maximum(intensity,1e-12)
    hue=np.mod(np.arctan2(np.sqrt(3.)*(g-b),2*r-g-b),2*np.pi)/(2*np.pi)
    valid=(intensity>PARAMS['min_intensity'])&(sat>PARAMS['min_saturation'])
    h=np.minimum((hue*256).astype(int),255);i=np.minimum((intensity*256).astype(int),255)
    return h,i,valid


def reference_histograms(und_bgr,reference):
    h,i,valid=features(und_bgr);reference=np.asarray(reference,bool)
    if reference.shape!=h.shape or not reference.any():raise ValueError('nonempty own-RGB floor reference required')
    kernel=np.ones(5)/5
    hh=np.bincount(h[reference&valid],minlength=256).astype(float)
    ih=np.bincount(i[reference],minlength=256).astype(float)
    hh=np.convolve(np.pad(hh,(2,2),mode='wrap'),kernel,mode='valid')
    ih=np.convolve(np.pad(ih,(2,2),mode='constant'),kernel,mode='valid')
    return hh,ih


def validate(table):
    if (table.get('schema')!='ugrp.s2.floor_appearance.v1' or table.get('runtime_gt') is not False
            or table.get('parameters')!=PARAMS or table.get('fit_uses_gt') is not False):
        raise ValueError('fixed own-RGB floor table and unchanged parameters required')
    for key in ('hue_floor_bins','intensity_floor_bins'):
        value=table.get(key)
        if not isinstance(value,list) or len(value)!=256 or any(type(v) is not bool for v in value):
            raise ValueError('expected 256 boolean floor bins')


def floor_pixels(und_bgr,table):
    h,i,valid=features(und_bgr)
    return (~valid|np.array(table['hue_floor_bins'],bool)[h])&np.array(table['intensity_floor_bins'],bool)[i]


def floor_contacts(obs,floor):
    """Both detector-adjacent 3x5 supports must be entirely known floor.

    Borders/missing RGB remain unknown, not evidence to remove a contact.
    This is the only RGB-contact ABI adaptation, fixed before replay.
    """
    remove=np.zeros(len(obs.columns),bool)
    if floor is None:return remove
    height,width=floor.shape
    for j in np.flatnonzero((obs.b_kind==1)&np.isfinite(obs.b_lo)):
        u=int(obs.columns[j]);v=int(round(obs.b_lo[j]))
        if u<2 or u+2>=width or v<3 or v+3>=height:continue
        remove[j]=bool(floor[v-3:v,u-2:u+3].all() and floor[v+1:v+4,u-2:u+3].all())
    return remove


def install(visibility,table):
    validate(table);table=copy.deepcopy(table)
    rgb=visibility.on_rgb;apply=visibility.apply;state={'und':None,'floor':None}
    audit=dict(option=OPTION,rows=[],gt_inputs=False,parameters=copy.deepcopy(PARAMS))
    def on_rgb(image):
        rgb(image);state['floor']=None;state['und']=None
        if image is not None:
            from harness import vision_loc_protocol as vp
            vl=vp.load_vis3()[0]
            state['und']=vl.mp.undistort(cv2.cvtColor(image,cv2.COLOR_RGB2BGR))
    def filtered(pf,obs,pose,t):
        masked=apply(pf,obs,pose,t)
        if masked is None:return None
        if state['floor'] is None and state['und'] is not None:
            state['floor']=floor_pixels(state['und'],table)
        remove=floor_contacts(masked,state['floor'])
        before=int((masked.b_kind==1).sum());masked.b_kind[remove]=0
        audit['rows'].append(dict(t=float(t),before=before,removed=int(remove.sum()),
            kept=int((masked.b_kind==1).sum()),removed_columns=masked.columns[remove].tolist()))
        return masked if np.any(masked.b_kind==1) else None
    visibility.on_rgb=on_rgb;visibility.apply=filtered
    return audit


class Runtime(Previous):
    def __init__(self,*args,contact_filter='off',floor_appearance=None,**kwargs):
        if contact_filter not in ('off',OPTION):raise ValueError('unknown contact_filter')
        if contact_filter!='off':
            if kwargs.get('visibility_policy')!=OBSERVED:raise ValueError('S2 observed AMCL policy required')
            validate(floor_appearance or {})
        self.contact_filter=contact_filter
        super().__init__(*args,**kwargs)
        if contact_filter!='off':
            self.contact_audit=install(self.visibility,floor_appearance)
            from harness.zone_solo_cyan_v106 import hp
            inner=self.pose.provider
            self.contact_audit['table_sha256']=hp.base.digest(floor_appearance)
            inner.runtime_contract['s2_contact_filter']=dict(option=OPTION,
                table_sha256=self.contact_audit['table_sha256'],scope='S2 loaded only',gt_inputs=False)
            inner.identity_sha256=hp.base.digest(inner.runtime_contract)
            inner.source='owncam_pf_s2_floor_contact:'+inner.identity_sha256[:8];self.pose.source=inner.source

    def record(self):
        out=super().record()
        if self.contact_filter!='off':out['contact_filter']=copy.deepcopy(self.contact_audit)
        return out
