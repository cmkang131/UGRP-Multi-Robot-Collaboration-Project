"""Explicit residual Brown-Conrady model after the PR405 fisheye model.

Fit only to physically straight scene edges; preserve independent held-out
edges and both image halves. Fixed K sets the output ray geometry. This does
not calibrate focal length, metric scale, camera mount or distance dependence.
"""
from dataclasses import dataclass
import cv2
import numpy as np


def brown(normalized, coefficients):
    p=np.asarray(normalized,float);x,y=p[...,0],p[...,1];k1,k2,p1,p2=coefficients
    r2=x*x+y*y;scale=1+k1*r2+k2*r2*r2
    return np.stack([x*scale+2*p1*x*y+p2*(r2+2*x*x),y*scale+p1*(r2+2*y*y)+2*p2*x*y],axis=-1)


def line_residual(points):
    p=np.asarray(points,float);center=p.mean(0);_,_,vt=np.linalg.svd(p-center,full_matrices=False)
    normal=vt[-1]
    if normal[np.argmax(abs(normal))]<0:normal=-normal
    return (p-center)@normal


@dataclass(frozen=True)
class ResidualLens:
    K:np.ndarray
    D:np.ndarray
    coefficients:tuple=(0.,0.,0.,0.)

    def __post_init__(self):
        K=np.asarray(self.K,float);D=np.asarray(self.D,float).reshape(4)
        coefficients=tuple(float(v) for v in self.coefficients)
        if K.shape!=(3,3) or len(coefficients)!=4 or K[0,0]<=0 or K[1,1]<=0 or not np.isfinite(K).all() or not np.isfinite(D).all() or not np.isfinite(coefficients).all() or max(abs(v) for v in coefficients)>.3:raise ValueError('Invalid residual camera model')
        object.__setattr__(self,'K',K.copy());object.__setattr__(self,'D',D.copy());object.__setattr__(self,'coefficients',coefficients)

    def points(self,raw):
        p=cv2.fisheye.undistortPoints(np.asarray(raw,float).reshape(-1,1,2),self.K,self.D,P=self.K)
        fn=getattr(cv2,'undistortPointsIter',cv2.undistortPoints)
        return fn(p,self.K,np.r_[self.coefficients,0.],R=None,P=self.K,criteria=(cv2.TERM_CRITERIA_COUNT+cv2.TERM_CRITERIA_EPS,40,1e-10)).reshape(-1,2)

    def maps(self,size=(640,480)):
        w,h=size;y,x=np.indices((h,w),dtype=float);rays=np.stack([(x-self.K[0,2])/self.K[0,0],(y-self.K[1,2])/self.K[1,1]],axis=-1)
        # Compose both models before resampling the image: one interpolation.
        distorted=cv2.fisheye.distortPoints(brown(rays,self.coefficients).reshape(-1,1,2),self.K,self.D).reshape(h,w,2)
        return distorted[...,0].astype(np.float32),distorted[...,1].astype(np.float32)

    def undistort(self,bgr):
        h,w=bgr.shape[:2]
        if (w,h)!=(640,480):raise ValueError('Residual calibration requires native 640x480')
        return cv2.remap(bgr,*self.maps((w,h)),cv2.INTER_LINEAR)


def bind_camera(module,model):
    from types import SimpleNamespace
    if not isinstance(model,ResidualLens) or not np.array_equal(model.K,module.K):
        raise ValueError('Residual model must preserve the frontend output K')
    return SimpleNamespace(**{**vars(module),'undistort':model.undistort})


def geometry_sane(model):
    y,x=np.mgrid[0:480:25,0:640:25];p=np.c_[(x.ravel()-model.K[0,2])/model.K[0,0],(y.ravel()-model.K[1,2])/model.K[1,1]]
    step=1e-5;dx=(brown(p+[step,0],model.coefficients)-brown(p-[step,0],model.coefficients))/(2*step)
    dy=(brown(p+[0,step],model.coefficients)-brown(p-[0,step],model.coefficients))/(2*step)
    determinant=dx[:,0]*dy[:,1]-dx[:,1]*dy[:,0]
    shift=np.linalg.norm((brown(p,model.coefficients)-p)*[model.K[0,0],model.K[1,1]],axis=1)
    return bool(np.isfinite(determinant).all() and determinant.min()>.25 and shift.max()<35.)


def fit_residual(lines,K,D):
    """Robust plumb-line objective, no surveyed 3D coordinates or depth labels.

    Caller must hold out whole physical edges/views rather than random pixels.
    A returned candidate has not passed the caller's independent adoption gate.
    """
    from scipy.optimize import least_squares
    if len(lines)<4 or any(len(p)<12 for p in lines):raise ValueError('Need at least four extended physical edges')
    yy,xx=np.mgrid[0:480:25,0:640:25]
    grid=np.c_[(xx.ravel()-K[0,2])/K[0,0],(yy.ravel()-K[1,2])/K[1,1]]
    def error(c):
        model=ResidualLens(K,D,tuple(c));res=[]
        for line in lines:res.extend(line_residual(model.points(line))/np.sqrt(len(line)))
        shift=np.linalg.norm((brown(grid,c)-grid)*[K[0,0],K[1,1]],axis=1)
        # Constrain the fit itself rather than loosening the adoption gate.
        return np.r_[res,np.asarray(c)*.05,np.maximum(0.,shift-30.)]
    solved=least_squares(error,np.zeros(4),bounds=([-.15,-.15,-.03,-.03],[.15,.15,.03,.03]),loss='soft_l1',f_scale=.5,max_nfev=150)
    return ResidualLens(K,D,tuple(solved.x)),dict(success=bool(solved.success),cost=float(solved.cost),condition=float(np.linalg.cond(solved.jac)))


def validation_report(model,lines):
    baseline=ResidualLens(model.K,model.D);result=[]
    for item in lines:
        raw=np.asarray(item['points'],float)
        before=float(np.sqrt(np.mean(line_residual(baseline.points(raw))**2)))
        after=float(np.sqrt(np.mean(line_residual(model.points(raw))**2)))
        result.append(dict(id=item['id'],side=item['side'],before_rms_px=before,after_rms_px=after))
    # Never trade a corrected right field for an overfitted left field.
    sides={s:[r for r in result if r['side']==s] for s in ('left','right')}
    enough=all(len(v)>=2 for v in sides.values())
    improved=all(np.median([r['after_rms_px'] for r in v])<.9*np.median([r['before_rms_px'] for r in v]) for v in sides.values()) if enough else False
    not_worse=all(r['after_rms_px']<=max(1.1*r['before_rms_px'],r['before_rms_px']+.15) for r in result)
    return dict(adopt=bool(enough and improved and not_worse and geometry_sane(model)),both_halves_supported=enough,geometry_sane=geometry_sane(model),edges=result)
