"""Global SE(2) landmark consensus; static map + own RGB detections/commands.

Exhaustive minimal line correspondences (the small-map analogue of RANSAC),
consensus, then scipy's Huber least_squares. No initial map pose is required.
Partial line endpoints constrain extent, never pretend to be mapped corners.
Sources and sensor-specific choices: release-localization-reference-first.md.
"""
from __future__ import annotations

import itertools
import math

import numpy as np
from scipy.optimize import least_squares

OPTION = 'setdown_global_v1'
PARAMS = dict(line_sigma_m=.04, angle_sigma_rad=math.radians(5),
              inlier_sigma=2.5, min_lines=3, min_views=2,
              min_span_m=.20, wall_fit_m=.025, wall_min_points=8,
              cluster_m=.15, cluster_rad=math.radians(8), min_score_gap=.75,
              max_views=18, max_refine=16, robot_clearance_m=.18)


def wrap(a):
    return np.arctan2(np.sin(a), np.cos(a))


def rotation(a):
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s], [s, c]])


def wall_lines(points):
    """Seeded two-point RANSAC, TLS refit; remove each consensus before next."""
    p = np.asarray(points, float).reshape(-1, 2)
    p = p[np.isfinite(p).all(1) & (np.linalg.norm(p, axis=1) <= 2.5)]
    rng = np.random.default_rng(0); out = []
    for _ in range(4):
        if len(p) < PARAMS['wall_min_points']:
            break
        best = np.zeros(len(p), bool)
        for _ in range(96):
            a, b = p[rng.choice(len(p), 2, replace=False)]
            d = b-a; length = np.linalg.norm(d)
            if length < PARAMS['min_span_m']:
                continue
            n = np.array([-d[1], d[0]])/length
            keep = abs((p-a)@n) <= PARAMS['wall_fit_m']
            if keep.sum() > best.sum():
                best = keep
        if best.sum() < PARAMS['wall_min_points']:
            break
        q = p[best]; center = q.mean(0)
        tangent = np.linalg.svd(q-center, full_matrices=False)[2][0]
        normal = np.array([-tangent[1], tangent[0]])
        if normal@center > 0:
            normal = -normal  # wall face points toward the observing free space
        along = (q-center)@tangent
        ends = center+np.array([along.min(), along.max()])[:, None]*tangent
        if np.linalg.norm(ends[1]-ends[0]) >= PARAMS['min_span_m']:
            out.append(dict(kind='wall', endpoints=ends, normal=normal,
                            fit_rms_m=float(np.sqrt(np.mean(((q-center)@normal)**2))), points=len(q)))
        p = p[~best]
    return out


def observations(views, current_command):
    """Bring every detection into CURRENT body coordinates using issued motion."""
    out = []; current = np.asarray(current_command, float)
    for vi, view in enumerate(views[-PARAMS['max_views']:]):
        command = np.asarray(view.get('command_pose', view['prior']), float)
        R = rotation(float(wrap(command[2]-current[2])))
        shift = rotation(-current[2])@(command[:2]-current[:2])
        features = wall_lines(view.get('wall_points_body', []))
        features += [f for f in view.get('features', []) if f.get('kind') == 'floor_line']
        for f in features:
            p, n = np.asarray(f['endpoints']), np.asarray(f['normal'])
            if p.shape != (2, 2) or n.shape != (2,) or not np.isfinite(p).all() or not np.isfinite(n).all():
                continue
            if np.linalg.norm(n) < .9 or np.linalg.norm(p[1]-p[0]) < .12:
                continue
            p = p@R.T+shift; n = R@n; n /= np.linalg.norm(n)
            out.append(dict(kind=f['kind'], p=p, n=n, hue=f.get('hue'), view=vi,
                            rho=float(p.mean(0)@n), angle=math.atan2(n[1], n[0])))
    return out


class GlobalLandmarkMatcher:
    def __init__(self, static):
        from harness.zone_solo_cyan_landmarks import MapFeatures
        self.static = static; self.edges = []
        for e in MapFeatures(static).edges:
            self.edges.append(dict(p=np.array([e['a'], e['b']]), n=e['normal'],
                                   kind='floor_line', hue=e['hue'], group=f"{e['region']}:{len(self.edges)}"))
        for o in static['obstacles']:
            if o.get('kind') != 'wall':
                continue
            x, y = o['center_m']; a, b = o['half_extents_m']
            for p, n in [([(x-a,y-b),(x+a,y-b)], (0,-1)), ([(x-a,y+b),(x+a,y+b)],(0,1)),
                         ([(x-a,y-b),(x-a,y+b)],(-1,0)), ([(x+a,y-b),(x+a,y+b)],(1,0))]:
                self.edges.append(dict(p=np.array(p), n=np.array(n), kind='wall', hue=None,
                                       group=f"{o['id']}:{len(self.edges)}"))
        for e in self.edges:
            e['rho'] = float(e['p'][0]@e['n']); e['angle'] = math.atan2(e['n'][1],e['n'][0])

    def candidates(self, f):
        return [i for i,e in enumerate(self.edges) if e['kind']==f['kind'] and
                (e['hue'] is None or abs(float(wrap(math.radians(2*(e['hue']-f['hue']))))) <= math.radians(24))]

    def free(self, poses, *, extra_clearance=0.):
        q = np.asarray(poses); x, y = q[:,0], q[:,1]; a,b,c,d = self.static['bounds_m']
        margin = PARAMS['robot_clearance_m']+extra_clearance
        good = (x>=a+margin)&(x<=b-margin)&(y>=c+margin)&(y<=d-margin)
        for o in self.static['obstacles']:
            if o.get('kind')!='wall':
                continue
            cx,cy=o['center_m']; hx,hy=o['half_extents_m']
            good &= ~((abs(x-cx)<hx+margin)&(abs(y-cy)<hy+margin))
        return good

    def hypotheses(self, fs, matches):
        hypotheses = []
        # Enumerate the finite correspondence set instead of random subsampling.
        for i,j in itertools.combinations(range(len(fs)),2):
            f,g=fs[i],fs[j]
            if abs(np.linalg.det(np.array([f['n'],g['n']]))) < .5:
                continue
            for k,l in itertools.product(matches[i],matches[j]):
                e,h=self.edges[k],self.edges[l]
                N=np.array([e['n'],h['n']])
                if abs(np.linalg.det(N)) < .5:
                    continue
                a=float(wrap(e['angle']-f['angle'])); b=float(wrap(h['angle']-g['angle']))
                if abs(float(wrap(a-b))) > 2*PARAMS['angle_sigma_rad']:
                    continue
                yaw=a+float(wrap(b-a))/2; R=rotation(yaw)
                rhs=[e['rho']-float((R@f['p'].mean(0))@e['n']),h['rho']-float((R@g['p'].mean(0))@h['n'])]
                xy=np.linalg.solve(N,rhs); hypotheses.append([*xy,float(wrap(yaw))])
        if not hypotheses:
            return np.empty((0,3))
        q=np.array(hypotheses);q=q[self.free(q)]
        # Only numerical duplicates removed; alternative regions/headings stay.
        return np.unique(np.round(q,6),axis=0)

    def residuals(self, poses, fs, matches):
        """ML finite-segment association, scaled metric + signed-normal residual."""
        poses=np.atleast_2d(poses);c,s=np.cos(poses[:,2]),np.sin(poses[:,2])
        values=[]; ids=[]
        for f, candidates in zip(fs,matches):
            p=f['p'];world=np.stack((poses[:,0,None]+c[:,None]*p[:,0]-s[:,None]*p[:,1],
                                     poses[:,1,None]+s[:,None]*p[:,0]+c[:,None]*p[:,1]),axis=-1)
            choices=[]
            for k in candidates:
                e=self.edges[k];a,b=e['p'];v=b-a
                u=np.clip(((world-a)@v)/(v@v),0,1)
                distance=np.sqrt(np.mean(np.sum((world-a-u[:,:,None]*v)**2,axis=-1),axis=1))
                angle=wrap(poses[:,2]+f['angle']-e['angle'])
                choices.append((distance/PARAMS['line_sigma_m'])**2+(angle/PARAMS['angle_sigma_rad'])**2)
            if choices:
                choices=np.array(choices).T;ix=choices.argmin(1)
                values.append(choices[np.arange(len(poses)),ix]);ids.append(np.array(candidates)[ix])
            else:
                values.append(np.full(len(poses),1e6));ids.append(np.full(len(poses),-1))
        return np.array(values).T,np.array(ids).T

    def fit(self, views, current_command):
        fs=observations(views,current_command);matches=[self.candidates(f) for f in fs]
        base=dict(accepted=False,reason='insufficient_global_landmarks',lines=len(fs),
                  views_with_evidence=len({f['view'] for f in fs}),prior_used=False,method='exhaustive_line_consensus_huber')
        if len(fs)<PARAMS['min_lines'] or base['views_with_evidence']<PARAMS['min_views']:
            return base
        q=self.hypotheses(fs,matches);base['hypotheses']=len(q)
        if not len(q):
            return {**base,'reason':'unobservable_global_landmarks'}
        threshold=PARAMS['inlier_sigma']**2
        errors,_=self.residuals(q,fs,matches)
        scores=np.maximum(0,1-errors/threshold).sum(1)
        seeds=[]
        for i in np.argsort(-scores,kind='stable'):
            if any(np.linalg.norm(q[i,:2]-p[:2])<PARAMS['cluster_m'] and abs(float(wrap(q[i,2]-p[2])))<PARAMS['cluster_rad'] for p in seeds):
                continue
            seeds.append(q[i])
            if len(seeds)==PARAMS['max_refine']:
                break
        solutions=[]
        for seed in seeds:
            err,ids=self.residuals(seed,fs,matches);keep=np.flatnonzero(err[0]<=threshold)
            if len(keep)<3:
                continue
            def residual(pose):
                R=rotation(pose[2]);out=[]
                for i in keep:
                    f=fs[i];e=self.edges[ids[0,i]];p=f['p']@R.T+pose[:2];a,b=e['p'];v=b-a
                    out.extend(((p-a)@e['n']/PARAMS['line_sigma_m']).tolist())
                    out.append(float(wrap(pose[2]+f['angle']-e['angle']))/PARAMS['angle_sigma_rad'])
                    u=((p-a)@v)/(v@v)
                    out.extend(((u-np.clip(u,0,1))*np.linalg.norm(v)/PARAMS['line_sigma_m']).tolist())
                return out
            opt=least_squares(residual,seed,loss='huber',f_scale=1.,max_nfev=40)
            p=opt.x;p[2]=float(wrap(p[2]))
            if not self.free([p])[0]:
                continue
            er,ids2=self.residuals(p,fs,matches); er=er[0];keep2=np.flatnonzero(er<=threshold)
            score=float(np.maximum(0,1-er/threshold).sum())
            solution=dict(pose=p,score=score,keep=keep2,ids=ids2[0],errors=er,
                          rank=int(np.linalg.matrix_rank(opt.jac)))
            if not any(np.linalg.norm(p[:2]-h['pose'][:2])<PARAMS['cluster_m'] and
                       abs(float(wrap(p[2]-h['pose'][2])))<PARAMS['cluster_rad'] for h in solutions):
                solutions.append(solution)
        if not solutions:
            return {**base,'reason':'no_consensus'}
        solutions.sort(key=lambda h:-h['score']);best=solutions[0]; keep=best['keep']
        gap=best['score']-solutions[1]['score'] if len(solutions)>1 else None
        view_count=len({fs[i]['view'] for i in keep});groups={self.edges[best['ids'][i]]['group'] for i in keep}
        normals=np.array([self.edges[best['ids'][i]]['n'] for i in keep])
        rank=int(np.linalg.matrix_rank(normals)) if len(normals) else 0
        ok=len(keep)>=PARAMS['min_lines'] and view_count>=PARAMS['min_views'] and rank==2 and (gap is None or gap>=PARAMS['min_score_gap'])
        metric_errors=[];angle_errors=[];R=rotation(best['pose'][2])
        for i in keep:
            f=fs[i];e=self.edges[best['ids'][i]];p=f['p']@R.T+best['pose'][:2];a,b=e['p'];v=b-a
            u=np.clip(((p-a)@v)/(v@v),0,1)
            metric_errors.extend(np.linalg.norm(p-a-u[:,None]*v,axis=1).tolist())
            angle_errors.append(float(wrap(best['pose'][2]+f['angle']-e['angle'])))
        return {**base,'accepted':bool(ok),'reason':'global_consensus' if ok else 'ambiguous_global_landmarks',
                'proposed':best['pose'].tolist(),'inliers':len(keep),'inlier_views':view_count,'groups':sorted(groups),
                'normal_rank':rank,'score':best['score'],'score_gap':gap,
                'normalized_inlier_rms':float(np.sqrt(np.mean(best['errors'][keep]))) if len(keep) else None,
                'inlier_segment_rms_m':float(np.sqrt(np.mean(np.square(metric_errors)))) if metric_errors else None,
                'inlier_normal_rms_deg':float(np.degrees(np.sqrt(np.mean(np.square(angle_errors))))) if angle_errors else None,
                'alternatives':[dict(pose=h['pose'].tolist(),score=h['score'],inliers=len(h['keep'])) for h in solutions[:4]],
                'credible_hypotheses':[dict(pose=h['pose'].tolist(),score=h['score']) for h in solutions
                                       if h['score']>=best['score']-PARAMS['min_score_gap']],
                'sigma':[.05,.05,math.radians(3)],'coordinate_frame':'map'}
