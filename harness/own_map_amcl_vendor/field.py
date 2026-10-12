"""Unmodified PR406 definitions; only imports and Runtime omission differ."""
import math
import numpy as np
from scipy.ndimage import distance_transform_edt


PARAMS=dict(z_hit=.5,z_rand=.5,sigma_hit_m=.2,max_occ_dist_m=2.,max_beams=60,
            range_max_m=100.,grid_resolution_m=.01,update_min_d_m=.25,
            update_min_a_rad=.2,do_beamskip=False)


class Field:
    """Metric occupancy raster; Euclidean cell-center distance, as AMCL cspace."""
    def __init__(self,static_map):
        rects=[]
        for o in static_map['obstacles']:
            if o.get('kind')!='wall':continue
            if o.get('yaw_rad',0):raise ValueError('axis-aligned S2 walls required')
            x,y=o['center_m'];dx,dy=o['half_extents_m']
            rects.append((x-dx,x+dx,y-dy,y+dy))
        if not rects:raise ValueError('static occupied walls required')
        r=np.array(rects);self.res=PARAMS['grid_resolution_m']
        self.origin=np.floor(r[:,[0,2]].min(0)/self.res)*self.res
        end=np.ceil(r[:,[1,3]].max(0)/self.res)*self.res
        self.shape=tuple((np.rint((end-self.origin)/self.res).astype(int)+1)[::-1])
        iy,ix=np.indices(self.shape);x=self.origin[0]+ix*self.res;y=self.origin[1]+iy*self.res
        occupied=np.zeros(self.shape,bool)
        for a,b,c,d in rects:occupied|=(x>=a-1e-12)&(x<=b+1e-12)&(y>=c-1e-12)&(y<=d+1e-12)
        self.dist=np.minimum(distance_transform_edt(~occupied)*self.res,PARAMS['max_occ_dist_m'])

    def distances(self,points):
        points=np.asarray(points,float)
        ij=np.floor((points-self.origin)/self.res+.5).astype(int)
        x,y=ij[...,0],ij[...,1]
        good=(x>=0)&(y>=0)&(x<self.shape[1])&(y<self.shape[0])
        out=np.full(x.shape,PARAMS['max_occ_dist_m'])
        out[good]=self.dist[y[good],x[good]]
        return out


def likelihood(field,px,points):
    px=np.asarray(px,float);points=np.asarray(points,float).reshape(-1,2)
    if not len(points):return np.ones(len(px))
    c,s=np.cos(px[:,2,None]),np.sin(px[:,2,None])
    x=px[:,0,None]+c*points[None,:,0]-s*points[None,:,1]
    y=px[:,1,None]+s*points[None,:,0]+c*points[None,:,1]
    d=field.distances(np.stack((x,y),axis=-1))
    pz=PARAMS['z_hit']*np.exp(-d*d/(2*PARAMS['sigma_hit_m']**2))+PARAMS['z_rand']/PARAMS['range_max_m']
    return 1.+np.sum(pz*pz*pz,axis=1)
