"""Finite all-pair line consensus with the exact original ordering/tie rule.

Vectorization changes calculation placement, not hypotheses, tolerance, count or
selection. It avoids thousands of Python/NumPy dispatches per5Hz image.
"""
import numpy as np


def best_line(points,remaining,eligible,tolerance,*,perpendicular=False):
    ids=np.flatnonzero(remaining & eligible)
    if len(ids)<2:return None,0
    ai,aj=np.triu_indices(len(ids),1);i,j=ids[ai],ids[aj]
    dx=points[j,0]-points[i,0]
    valid=dx!=0;i,j,dx=i[valid],j[valid],dx[valid]
    if not len(i):return None,0
    slope=(points[j,1]-points[i,1])/dx
    predicted=points[i,1,None]+slope[:,None]*(points[None,:,0]-points[i,0,None])
    residual=abs(points[None,:,1]-predicted)
    if perpendicular:
        # Original compass cross-product/normal arithmetic. Integer image
        # contacts keep the dot products exact even at a1.5px tie boundary.
        a,b=points[i],points[j]
        lines=np.column_stack([a[:,1]-b[:,1],b[:,0]-a[:,0],a[:,0]*b[:,1]-a[:,1]*b[:,0]])
        design=np.column_stack([points,np.ones(len(points))])
        residual=abs((design@lines.T)/np.linalg.norm(lines[:,:2],axis=1)).T
    keep=remaining[None,:] & (residual<=tolerance)
    # np.argmax takes the first max, same as the original strict '>' update.
    return keep[int(np.argmax(keep.sum(1)))],len(i)
