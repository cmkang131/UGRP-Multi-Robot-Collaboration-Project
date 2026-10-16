"""Recording-only GPU native finger normals, byte-derived from f0db6b1a.

No forces, contacts, measured joints or success labels are returned to control.
Formula/kernel body is the existing WarpTransport evaluator, not C reconstruction.
"""
class NativeContactRecorder:
    def __init__(self,model,data,target,fingers):
        import warp as wp
        from mujoco_warp._src.support import contact_force_fn
        from mujoco_warp._src.types import vec5
        self.wp=wp;self.model=model;self.data=data
        self.targets=wp.array([target],dtype=int);self.fingers=wp.array([fingers],dtype=int);self.out=wp.zeros((1,2),dtype=float)
        @wp.kernel
        def evaluate(nacon:wp.array[int],worldid:wp.array[int],geom:wp.array[wp.vec2i],
                     cone:int,njmax:int,frame:wp.array[wp.mat33],friction:wp.array[vec5],
                     condim:wp.array[int],adr:wp.array2d[int],adhesion:wp.array[float],
                     efc_force:wp.array2d[float],targets:wp.array[int],fingers:wp.array2d[int],out:wp.array2d[float]):
            i=wp.tid()
            if i<nacon[0]:
                a,b=geom[i][0],geom[i][1]
                w=worldid[i]
                target=targets[w]
                left,right=fingers[w,0],fingers[w,1]
                k=int(-1)
                if a==target or b==target:
                    if a==left or b==left:k=0
                    if a==right or b==right:k=1
                if k>=0:
                    w=worldid[i]
                    force=contact_force_fn(cone,frame,friction,condim,adr,adhesion,efc_force,njmax,nacon,w,i,False)
                    wp.atomic_add(out,w,k,wp.abs(force[0]))
        self.kernel=evaluate

    def record(self):
        d=self.data;self.out.zero_()
        self.wp.launch(self.kernel,dim=d.naconmax,inputs=[d.nacon,d.contact.worldid,d.contact.geom,
            int(self.model.opt.cone),int(d.njmax),d.contact.frame,d.contact.friction,d.contact.dim,
            d.contact.efc_address,d.contact.adhesion,d.efc.force,self.targets,self.fingers,self.out])
        return self.out.numpy()[0].tolist()
