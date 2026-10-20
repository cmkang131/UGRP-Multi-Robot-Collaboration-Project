"""Frozen seven-probe/FOV definition; all occlusion rays run as one GPU batch."""
import numpy as np


class BatchVisibility:
    def __init__(self, transport, contexts):
        self.transport=transport
        self.wp,self.mjw=transport.wp,transport.mjw
        # The topology is shared; each model's geometry sizes remain per-world.
        self.gids=sorted({g for c in contexts for g in c['visibility_gids']})
        self.index={g:i for i,g in enumerate(self.gids)}
        self.models=[c['world'].model for c in contexts]
        self.sizes=np.stack([m.geom_size[self.gids] for m in self.models])
        self.cid=self.models[0].camera('r1__robot_cam').id
        self.nray=len(self.gids)*7
        wp=self.wp;n=transport.n
        self.origins=wp.zeros((n,self.nray),dtype=wp.vec3)
        self.directions=wp.zeros((n,self.nray),dtype=wp.vec3)
        self.distance=wp.zeros((n,self.nray),dtype=float)
        self.hits=wp.zeros((n,self.nray),dtype=int)
        self.normals=wp.zeros((n,self.nray),dtype=wp.vec3)
        self.exclude=wp.full(self.nray,-1,dtype=int)
        self.inside=None;self.hit_ids=None;self.calls=0

    def update(self, transforms):
        import cv2
        from sim.masterpi_camera_profile import scaled_camera_matrix,CAMERA_FISHEYE_D
        wp=self.wp;t=self.transport
        centers=transforms['geom_xpos'][:,self.gids]
        axes=transforms['geom_xmat'][:,self.gids].reshape(t.n,len(self.gids),3,3)
        points=np.repeat(centers[:,:,None,:],7,axis=2)
        for axis in range(3):
            for sign in (-1,1):
                k=1+axis*2+(sign==1)
                points[:,:,k]=centers+sign*.8*self.sizes[:,:,axis,None]*axes[:,:,:,axis]
        points=points.reshape(t.n,self.nray,3)
        cam=transforms['cam_xpos'][:,self.cid]
        rotation=transforms['cam_xmat'][:,self.cid].reshape(t.n,3,3)
        optical=np.einsum('nri,nij->nrj',points-cam[:,None,:],rotation)*np.array([1.,-1.,-1.])
        z=optical[:,:,2]
        K=scaled_camera_matrix(640,480);D=np.array(CAMERA_FISHEYE_D)
        uv=optical[:,:,:2]/np.maximum(z[:,:,None],1e-12)*np.diag(K)[:2]+K[:2,2]
        raw,_=cv2.fisheye.projectPoints(optical.reshape(-1,1,3),np.zeros(3),np.zeros(3),K,D)
        raw=raw.reshape(t.n,self.nray,2)
        near=np.array([m.vis.map.znear*m.stat.extent for m in self.models])
        self.inside=(z>near[:,None])&(uv[:,:,0]>=0)&(uv[:,:,0]<640)&(uv[:,:,1]>=0)&(uv[:,:,1]<480)&(raw[:,:,0]>=0)&(raw[:,:,0]<640)&(raw[:,:,1]>=0)&(raw[:,:,1]<480)
        delta=points-cam[:,None,:];length=np.linalg.norm(delta,axis=2)
        direction=delta/np.maximum(length[:,:,None],1e-12)
        origins=cam[:,None,:]+(near[:,None]*length/np.maximum(z,1e-12))[:,:,None]*direction
        # Off-frame probes still receive finite valid rays; their results are
        # masked before any visibility count. They never yield a measurement.
        origins=np.where(self.inside[:,:,None],origins,cam[:,None,:])
        direction=np.where(self.inside[:,:,None],direction,np.array([0.,0.,1.]))
        wp.copy(self.origins,wp.array(origins,dtype=wp.vec3));wp.copy(self.directions,wp.array(direction,dtype=wp.vec3))
        from mujoco_warp._src.types import vec6
        self.mjw.rays(t.wm,t.wd,self.origins,self.directions,vec6(1,1,1,1,0,0),True,self.exclude,
            self.distance,self.hits,self.normals,t.rc)
        self.hit_ids=self.hits.numpy().reshape(t.n,len(self.gids),7)
        self.inside=self.inside.reshape(t.n,len(self.gids),7)
        self.calls+=1

    def region_visible(self,index,gids):
        gids=list(gids)
        if not gids:return 0,0
        selected=[self.index[g] for g in gids]
        seen=np.isin(self.hit_ids[index,selected],gids)&self.inside[index,selected]
        return int(seen.sum()),len(gids)*7
