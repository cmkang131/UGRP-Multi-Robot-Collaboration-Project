"""Opt-in known box footprint, using only already admitted own observations.

OMPL SE(2) validity checks and Nav2 footprint checking motivate using the actual
oriented planar shape rather than a 3-D circumsphere. Geometry is the fixed
zone_arena.BOX_HALF specification; pose/yaw are from the visible-world model.
Arm sweeps retain the original bounding spheres. No obstacle is removed.
"""

MODE='beampair_box_geometry_v1'
CHECKS_MODE='beampair_checks_only_v1'


def navigation_class(original):
    import numpy as np
    from sim.zone_arena import BOX_HALF,COLORS
    from sim.grasp_act_search23 import rectangle_gaps
    from sim.grasp_act_search21 import FRESH_MARGIN_M
    from sim.grasp_act_search25 import hard_margins

    class BoxNavigation(original):
        def __init__(self,t,world,*a,**kw):
            super().__init__(t,world,*a,**kw)
            self.boxes=[]
            if getattr(t,'box_geometry','off')==MODE:
                obs=world['visibility'][t.rid].get('observations',{})
                for j,detail in enumerate(self.details):
                    name=detail['id'];m=obs.get(name)
                    # Fixed known color-box inventory. Unknown cargo keeps its
                    # original bounding sphere; no authored/live world lookup.
                    if (m is None or m.get('kind')!='cargo'
                            or name.rsplit('_',1)[0] not in COLORS):continue
                    self.boxes.append((j,(*m['xyz'][:2],*BOX_HALF[:2],m['yaw'])))
                if self.boxes and (not t.box_geometry_log or t.box_geometry_log[-1]['t']!=world['t']):
                    t.box_geometry_log.append(dict(t=world['t'],event='known_box_footprint',
                        reason_category='oriented_planar_cargo_shape',blocked_object=[self.details[j]['id'] for j,_ in self.boxes],
                        min_gap_m=None,gap_scope='geometry construction, no clearance verdict',
                        half_extents_m=list(BOX_HALF[:2]),source='zone_arena.BOX_HALF + admitted own-camera observation; retained covariance unchanged'))

        def measure(self,xy,yaw=None):
            if not self.boxes:return super().measure(xy,yaw)
            # Discard parent audit side effects from the superseded spheres;
            # this call still consumes exactly one native planning check.
            saved=self.blocked.copy()
            gaps,_=super().measure(xy,yaw)
            self.blocked=saved
            xy=np.asarray(xy,dtype=float).reshape(-1,2)
            if yaw is None:
                yaw=(np.full(len(xy),self.pose[2]) if self.target is None else
                    np.arctan2(self.target[1]-xy[:,1],self.target[0]-xy[:,0]))
            yaw=np.broadcast_to(yaw,(len(xy),))
            for j,rect in self.boxes:
                # Preserve the original folded low-cargo 5mm padding. The
                # change removes only the sphere's vertical/corner excess;
                # confidence margins and interpolation bounds stay native.
                padding=0. if self.inflation_soft else .005
                gaps[:,j]=rectangle_gaps(xy,yaw,rect)-padding
            margins=np.array(hard_margins(self));slack=gaps-margins
            self.last_inflation_slack=gaps-np.array([d['margin_m'] for d in self.audit_details])
            self.last_blockers=[]
            for j in np.flatnonzero((slack<0).any(axis=0)):
                i=int(np.argmin(slack[:,j]));d=self.audit_details[j]
                row={**d,'gap_m':float(gaps[i,j]),'slack_m':float(slack[i,j]),
                    'sample_pose':[*map(float,xy[i]),float(yaw[i])],
                    'category':'memory_margin' if not d['fresh'] and gaps[i,j]>=FRESH_MARGIN_M else 'current_geometry'}
                old=self.blocked.get(d['id'])
                if old is None or row['slack_m']<old['slack_m']:self.blocked[d['id']]=row
                self.last_blockers.append(row)
            return gaps,slack
    return BoxNavigation


def checks_only_class(original):
    class ChecksOnlyBudget(original):
        def __init__(self,*a,**kw):
            # Retain the native 98,304 logical checks. Original8328188 hit the
            # 30 wall-s safety cap at22 SIMs; OMPL's iteration termination and
            # user rule1 require a host-load-independent planning boundary.
            kw.update(max_s=None,safety_s=None)
            super().__init__(*a,**kw)
    return ChecksOnlyBudget
