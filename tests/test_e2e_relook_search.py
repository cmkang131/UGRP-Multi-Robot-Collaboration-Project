import copy
from types import SimpleNamespace as NS

import numpy as np
import pytest

from harness import e2e_relook_search as m
from harness import e2e_setdown_relook as old
from harness.e2e_rgb_gate import features
from harness.owncam_pair_beam_v2 import pose_of
from tests.test_e2e_setdown_relook import own_goal, texture


def fixture(mode):
    goals={r:own_goal() for r in ('r1','r2')}
    # The existing fixture creates r1 goals; use only r1 in metric tests.
    for g in goals.values():
        old.OwnRGBRelook(g)
    tr=NS(robots={r:NS(goal=g,servo=dict(pose_of('search'))|{1:2000}) for r,g in goals.items()},
          state='mapping',queue=[],queue_until=0.,robot_queue_until={},profiles={},events=[])
    tr.step=lambda now:[]
    tr.event=lambda now,event,**kw:tr.events.append(dict(t=now,event=event,**kw))
    tr._poses=lambda rid,now,path:tr.robot_queue_until.update({rid:now+sum(d+s for _,d,s in path)})
    m.install(tr,mode)
    return tr,goals['r1']


def frame(goal, i, t, image=None, segments=True):
    return goal.receive(robot_id=goal.robot_id,t=t,frame_id=i,frame_sha256=f'{i:064x}',
        rgb=texture() if image is None else image,servo=pose_of('search'),
        observation=dict(segments=[[[1.,-1.],[1.,1.]],[[1.,1.],[-1.,1.]]] if segments else [],camera=[0.,0.]))


def test_nearest_featureless_view_is_replaced_but_real_three_frame_metric_gate_remains():
    _,goal=fixture('view5_v1');frame(goal,1,1.);goal.graph.seal()
    rl=goal.e2e_relook;g=goal.explorer.memory.self_map
    bad=copy.deepcopy(goal.graph.nodes[0]);bad.update(id=1,frame_id=99,t=1.5,pose=[.08,0.,0.])
    goal.graph.nodes.append(bad)
    rl.history[99]=dict(features=features(np.zeros((240,320,3),np.uint8)),servo=pose_of('search'))
    g.poses[:,0]=.08;before=g.odom.pose[0];cov=g.odom.covariance.copy()
    rl.request(2.,seg=0,epoch=2)
    assert rl.pending['candidate_nodes']==[0] and rl.pending['node']==0
    frame(goal,2,2.1);frame(goal,3,2.2)
    assert rl.receipt is None and g.odom.pose[0]==before
    frame(goal,4,2.3)
    assert rl.receipt and abs(g.odom.pose[0])<abs(before)
    assert len(rl.receipt['rgb'])==3 and not rl.receipt['covariance_reset']
    assert np.trace(g.odom.covariance)==pytest.approx(np.trace(cov))


@pytest.mark.parametrize('bad',('blank','no_metric','stale'))
def test_candidate_retrieval_cannot_replace_visual_metric_or_freshness_evidence(bad):
    _,goal=fixture('view5_v1');frame(goal,1,1.);goal.graph.seal();rl=goal.e2e_relook;rl.request(2.,seg=0,epoch=2)
    for i in range(2,5):
        frame(goal,i,1.5+.1*i if bad=='stale' else 2.+.1*i,
              image=np.zeros((240,320,3),np.uint8) if bad=='blank' else None,segments=bad!='no_metric')
    assert rl.receipt is None


def test_active_pan_holds_open_chassis_and_excludes_pre_settle_image():
    tr,goal=fixture('view5_pan_v1');frame(goal,1,1.);goal.graph.seal();rl=goal.e2e_relook;rl.request(2.,seg=0,epoch=2)
    tr.state='relook';out=tr.step(4.5)
    assert out and all(a['kind']=='hold' for _,a in out)
    assert rl.search_until==5.4 and tr.events[-1]['receipt'] is False
    for i,t in enumerate((4.6,4.7,4.8),2):frame(goal,i,t)
    assert rl.receipt is None and not rl.pending['matches']
    tr.robots['r1'].servo[1]=1500
    assert ('r1',dict(kind='hold')) in m.actions(tr,7.)


def test_candidates_are_frozen_prior_own_nodes_not_post_request_self_matches():
    _,goal=fixture('view5_v1');frame(goal,1,1.);rl=goal.e2e_relook;rl.request(2.,seg=0,epoch=2)
    assert rl.pending['candidate_nodes']==[0]
    frame(goal,2,2.1)
    newer=copy.deepcopy(goal.graph.nodes[0]);newer.update(id=len(goal.graph.nodes),frame_id=2,t=2.1)
    goal.graph.nodes.append(newer)
    assert rl.pending['candidate_nodes']==[0]


def test_off_identity_and_registered_parent_scope():
    obj=object();assert m.install(obj,'off') is obj
    for mode,v in m.VERSIONS.items():
        b=dict(execution_bundle_id='e2e18-v273',e2e_options={});before=copy.deepcopy(b)
        assert m.compose(b,'off')==() and b==before
        m.compose(b,mode);assert b['execution_bundle_id']==f'e2e18-v{v}'
        assert b['relook_search_parameters']==m.PARAMS
        with pytest.raises(ValueError):m.compose(b,mode)
