"""Lorigo/Brooks/Grimson IROS1997 §2.2-2.3 window histograms + median.

Default-off adapter, own RGB and camera calibration only. Unspecified constants
and output conventions were preregistered in 2026-10-08-lorigo-window-contact.
No pixel acceptance bins, temporal reference learning, GT, or semantic wall claim.
"""
import cv2
import numpy as np
from harness.wall_floor_boundary import _plane, to_scan

OPTION = 'lorigo_window_v1'
CONFIG = dict(process_size=[64,64], window_size=[20,10], bins=32,
              l1_thresholds=[80.,80.,80.], gaussian_kernel=5,
              min_saturation=.033, fusion='median', boundary_row='window_center_top_plus_5',
              reference='current_frame_bottom_window_per_slice', max_range_m=4.)


class Diagnostics:
    """Optional output holder; never fed back into detection."""
    last_result = None


def window_histogram(bins):
    """All 20x10 window count histograms; -1 denotes ignored colour samples."""
    bins=np.asarray(bins)
    if bins.shape!=(64,64) or np.any((bins < -1)|(bins>=32)):
        raise ValueError('EXPECTED_64X64_BINS_MINUS1_TO31')
    onehot=np.eye(33,dtype=np.int32)[bins+1][...,1:]
    integral=np.pad(onehot,((1,0),(1,0),(0,0))).cumsum(0).cumsum(1)
    return integral[10:,20:]-integral[:-10,20:]-integral[10:,:-20]+integral[:-10,:-20]


def features(bgr):
    """Paper: gradient distribution, normalized RG, HS excluding S < 3.3%."""
    small=cv2.resize(bgr,(64,64),interpolation=cv2.INTER_AREA)
    colour=small.astype(np.float32)/255.
    den=colour.sum(-1)
    normalized=np.divide(colour,den[...,None],out=np.zeros_like(colour),where=den[...,None]>0)
    hsv=cv2.cvtColor(colour,cv2.COLOR_BGR2HSV)
    hue=hsv[...,0]/360.;sat=hsv[...,1]
    quant=lambda a:np.minimum((a*32).astype(np.int32),31)
    h,s=quant(hue),quant(sat)
    h[sat<CONFIG['min_saturation']]=-1;s[sat<CONFIG['min_saturation']]=-1
    gray=cv2.cvtColor(cv2.GaussianBlur(small,(5,5),0),cv2.COLOR_BGR2GRAY).astype(float)
    dy,dx=np.gradient(gray)  # central differences; one-sided on image boundary
    edge=quant(np.hypot(dx,dy)/(255*np.sqrt(2.)))
    return [edge,quant(normalized[...,2]),quant(normalized[...,1]),h,s],small


def boundary_arrays(histograms,support,self_mask):
    """One-pixel upward scan, immutable bottom reference, all three modules."""
    support=np.asarray(support,bool);self_mask=np.asarray(self_mask,bool)
    if support.shape!=(64,64) or self_mask.shape!=(64,64):raise ValueError('SUPPORT_SHAPE')
    windows=np.lib.stride_tricks.sliding_window_view(support,(10,20)).all((-2,-1))
    own=np.lib.stride_tricks.sliding_window_view(self_mask,(10,20)).any((-2,-1))
    module=np.zeros((3,45),int);bottom=np.full(45,-1,int)
    distances=np.full((3,55,45),-1.,float)
    reasons=[]
    for x in range(45):
        valid=np.flatnonzero(windows[:,x])
        if not len(valid):reasons.append('no_valid_reference');continue
        y0=int(valid[-1]);bottom[x]=y0
        if own[y0,x]:reasons.append('self_reference');continue
        ref=[h[y0,x] for h in histograms]
        for y in range(y0-1,-1,-1):
            if not windows[y,x] or own[y,x]:break
            diff=[float(np.abs(h[y,x]-r).sum()) for h,r in zip(histograms,ref)]
            d=np.array([diff[0],diff[1]+diff[2],diff[3]+diff[4]])
            distances[:,y,x]=d
            for k in range(3):
                if module[k,x]==0 and d[k]>CONFIG['l1_thresholds'][k]:module[k,x]=y+5
        reasons.append('scanned')
    fused=np.median(module,axis=0).astype(int)
    return module,fused,bottom,distances,reasons


def detect(und_bgr,cm,valid_image,self_top):
    image=np.asarray(und_bgr)
    if image.dtype!=np.uint8 or image.ndim!=3 or image.shape[2]!=3:raise ValueError('UINT8_BGR_REQUIRED')
    if np.asarray(valid_image).shape!=image.shape[:2]:raise ValueError('VALID_IMAGE_SHAPE')
    columns=np.asarray(cm.columns,int);self_top=np.asarray(self_top,float)
    if self_top.shape!=columns.shape:raise ValueError('SELF_TOP_SHAPE')
    fields,small=features(image)
    # Undistortion validity is geometry, never RGB brightness. Full source support
    # plus blur margin is required for each window, without altering classification.
    support=cv2.resize(np.asarray(valid_image,np.float32),(64,64),interpolation=cv2.INTER_AREA)>=1.
    support=cv2.erode(support.astype(np.uint8),np.ones((5,5),np.uint8),borderType=cv2.BORDER_CONSTANT,borderValue=0).astype(bool)
    top=np.interp(np.arange(image.shape[1]),columns,self_top)
    own=np.indices(image.shape[:2])[0]>=top[None,:]
    own=cv2.resize(own.astype(np.float32),(64,64),interpolation=cv2.INTER_AREA)>0
    hist=[window_histogram(f) for f in fields]
    module,fused,bottom,distance,reasons=boundary_arrays(hist,support,own)
    from harness.active_wall_vision import modules
    intrinsic=modules()[0].K
    xyz,ranges,positive,_=_plane(image.shape[:2],tuple(cm.origin),tuple(cm._rot.ravel()),tuple(intrinsic.ravel()))
    ids,uv=[],[];counts=dict(unsupported_side=0,no_boundary=0,invalid_contact=0,behind_camera=0,range=0)
    for j,u in enumerate(columns):
        x=int(np.floor((u+.5)*64/image.shape[1]))-10
        if not 0<=x<45:counts['unsupported_side']+=1;continue
        if fused[x]==0:counts['no_boundary']+=1;continue
        v=int(round((fused[x]+.5)*image.shape[0]/64-.5))
        if not valid_image[v,u] or v>=self_top[j]:counts['invalid_contact']+=1;continue
        if not positive[v,u]:counts['behind_camera']+=1;continue
        if ranges[v,u]>=4.:counts['range']+=1;continue
        ids.append(j);uv.append((u,v))
    ids=np.array(ids,int);uv=np.array(uv,float).reshape(-1,2)
    vi=uv[:,1].astype(int);ui=uv[:,0].astype(int)
    return dict(column_ids=ids,uv=uv,xy=xyz[vi,ui,:2].copy(),ranges=ranges[vi,ui].copy(),
        diagnostics=dict(reason='classified',module_rows=module.tolist(),fused_rows=fused.tolist(),
            reference_top=bottom.tolist(),slice_reasons=reasons,columns=counts,
            module_hits=(module>0).sum(1).tolist(),fused_hits=int((fused>0).sum()),
            distance=distance.tolist()),small=small,support=support)
