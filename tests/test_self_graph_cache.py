import copy,json
import numpy as np
import pytest
from harness.self_graph_cache import GraphCache,install,OPTION
from harness.self_pose_graph import GraphOptions,apply_pose_graph,make_submaps,match_loop,ProbabilityField
from tests.test_self_pose_graph import row,CORNER


def encoded(value):return json.dumps(value,sort_keys=True,default=lambda a:a.tolist()).encode()


def test_exact_fields_matches_and_defensive_result_copy():
    o=GraphOptions();sm,_=make_submaps('r1',[row(i) for i in range(10)],o)
    c=GraphCache('r1');c.prepare(sm,'r1');r=row(30);initial=np.array([.3,-.2,.05])
    a=match_loop(sm[0],r,initial,o);b=c.match(sm[0],r,initial,o)
    assert encoded(a)==encoded(b)
    b['reason']='caller mutation'
    assert encoded(c.match(sm[0],r,initial,o))==encoded(a)
    assert c.stats()['pair_hits']==1 and c.stats()['probability_builds']==1
    np.testing.assert_array_equal(sm[0]['_prepared'].probability().values,ProbabilityField(sm[0]['grid']).values)


def test_changed_input_invalidates_all_sensitive_keys_and_robot_scope():
    o=GraphOptions();sm,_=make_submaps('r1',[row(i) for i in range(3)],o);c=GraphCache('r1');c.prepare(sm,'r1')
    r=row(40);p=np.zeros(3);c.match(sm[0],r,p,o)
    for rr,pp,oo in [(row(40,segments=np.asarray(CORNER)+.01),p,o),
                     (r,p+[.001,0,0],o),(r,p,GraphOptions(min_score=.6))]:
        c.match(sm[0],rr,pp,oo)
    assert c.stats()['pair_misses']==4
    changed=copy.deepcopy(sm[0]);key=next(iter(changed['grid'].cells));changed['grid'].cells[key]+=.01
    c.prepare([changed],'r1');c.match(changed,r,p,o)
    assert c.stats()['pair_misses']==5 and c.stats()['field_misses']==2
    changed['segments']=changed['segments'][::-1].copy();c.prepare([changed],'r1')
    assert c.stats()['field_misses']==3
    with pytest.raises(ValueError,match='PEER'):c.prepare(sm,'r2')
    with pytest.raises(ValueError,match='PEER'):c.match(sm[0],{**r,'robot_id':'r2'},p,o)


def test_full_graph_off_cold_warm_bytes_and_bounds():
    rs=[row(0),row(10,(.1,0.,0.)),row(20,(.2,0.,0.))]
    ps=[dict(robot_id='r1',t=r['t'],pose=r['pose']) for r in rs]
    kw=dict(robot_id='r1',pose_graph='own_submap_v1',options={'submap_scans':2,'stride':1,'separation_s':1.})
    a=apply_pose_graph(rs,ps,**kw);c=GraphCache('r1')
    b=apply_pose_graph(rs,ps,cache=c,**kw);d=apply_pose_graph(rs,ps,cache=c,**kw)
    assert encoded(a)==encoded(b)==encoded(d)
    assert c.stats()['pair_hits']>0
    limited=GraphCache('r1',max_pairs=1,max_fields=1)
    assert encoded(apply_pose_graph(rs,ps,cache=limited,**kw))==encoded(a)
    assert limited.stats()['pair_entries']==limited.stats()['field_entries']==1
    x=object();assert install(x) is x
    with pytest.raises(ValueError):install(x,graph_acceleration='bad')
    assert apply_pose_graph(x,x,robot_id='r1',cache=object())==(x,x,None)


def test_memory_option_and_frontend_immutable():
    from harness.self_wall_memory_robust import SelfWallMemory
    from harness.active_wall_mapping import OPTIONS
    a=SelfWallMemory('r1',**OPTIONS);b=SelfWallMemory('r1',**OPTIONS,graph_acceleration=OPTION)
    for m in (a,b):m.self_map.ledger=[row(0),row(10)]
    before=encoded(b.self_map.export())
    assert encoded(a.finalize_pose_graph())==encoded(b.finalize_pose_graph())
    assert encoded(b.self_map.export())==before
