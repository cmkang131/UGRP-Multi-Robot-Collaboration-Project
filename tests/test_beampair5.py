"""Wall sensor inverse model regression checks, without physics/rendering."""
import math
from copy import deepcopy
from harness.beampair_wall_layer import WallLayer, ray_cells, HIGH, LOW


def world(t, walls):
    return dict(t=t,robots={'r2':{'pose':[0.,0.,0.]}},objects={},beam=None,
                walls=[(*m['xyz'][:2],*m['half_extents'],m['yaw']) for m in walls],
                visibility={'r2':dict(observations={m['id']:m for m in walls})})


def wall(t):
    return dict(id='north',kind='wall',xyz=[.5,0.,.2],half_extents=[.025,.2],yaw=0.,seen_t=t)


def test_stale_wall_requires_observed_misses_not_expiry_and_clamps():
    layer=WallLayer();m=wall(0.);w=world(0.,[m]);before=deepcopy(w)
    assert layer.update(w,'r2',[m],[]) is w and w==before  # inactive path unchanged
    layer.active=True
    for t in range(1,50):layer.update(world(float(t),[m]),'r2',[],[])
    assert layer.odds[(20,0)]>0  # empty frame / age cannot clear
    ray=dict(origin=[0.,.0125,.1],end=[1.,.0125,0.],hit_wall=None)
    for t in range(50,70):layer.update(world(float(t),[m]),'r2',[],[ray])
    assert layer.odds[(20,0)]==LOW and layer.odds[(20,3)]>0
    assert any(e['cleared_cell_N'] for e in layer.events)
    for t in range(70,90):
        fresh=wall(float(t));layer.update(world(float(t),[fresh]),'r2',[fresh],[ray])
    assert layer.odds[(20,0)]==HIGH  # current occupied support wins over free


def test_grid_geometry_keeps_blocker_names_and_clears_only_traversed_cells():
    layer=WallLayer();layer.active=True;m=wall(0.)
    w=layer.update(world(0.,[m]),'r2',[m],[])
    cells=[m for k,m in w['visibility']['r2']['observations'].items() if ':grid:' in k]
    assert cells and all(m['wall_layer_owner']=='north' for m in cells)
    assert all(m['half_extents'][0]>=.0125 for m in cells)
    assert (20,0) in set(ray_cells((0.,.0125),(1.,.0125)))
    assert (40,0) not in set(ray_cells((0.,.0125),(1.,.0125)))
    assert list(ray_cells((-.01,-.01),(-.06,-.06)))==[(-1,-1),(-2,-2)]


def test_gate_remains_unapproved_and_orders_failed_seeds_first(tmp_path,monkeypatch):
    import json,subprocess
    import scripts.queue_beampair5 as q
    source=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    wanted=[8318626,8318620,8318600,8318604,8318611,8318631]
    evidence=tmp_path/'summary.json';evidence.write_text(json.dumps(dict(runs=[dict(seed=s,adapter_sha=source) for s in wanted])))
    def previous(*a,**kw):
        return dict(source_hashes={},runs=[dict(name=f'beampair2-{s}',seed=s,episode=i,command=['python','runner','--host','gcp1','--per-run-mb','128']) for i,s in enumerate(wanted)])
    monkeypatch.setattr(q,'previous',previous)
    value=q.build(source,evidence,tmp_path/'table.json')
    assert value['status']=='HOLD_SCENE' and not any(value[k] for k in ('ready','approved','submitted'))
    assert value['first_two_seeds']==[8318620,8318626]
    assert [r['seed'] for r in value['runs'][:2]]==value['first_two_seeds']
    assert value['wall_layer']=='beampair_wall_clear_v1' and not value['training_rgb']
    assert all('beampair_wall_clear_v1' in r['command'] for r in value['runs'])


def test_supervisor_stop_is_preserved_when_a_candidate_is_in_flight():
    from scripts.run_beampair1 import record_partial_candidates
    rows=[dict(reason='blocked_goal'),{}];recorded=[]
    def original(t,w,rs,now):recorded.extend(r['reason'] for r in rs)
    try:
        try:raise KeyboardInterrupt('supervisor')
        finally:record_partial_candidates(original,None,{},rows,0.)
    except KeyboardInterrupt as e:
        assert str(e)=='supervisor'
    else:raise AssertionError('original supervisor interruption must propagate')
    assert recorded==['blocked_goal','supervisor_interrupted']
    assert rows[1]['interrupted_error_type']=='KeyboardInterrupt'
    normal=[{}]
    record_partial_candidates(lambda *a:None,None,{},normal,0.)
    assert normal==[{}]  # do not mask a normal-path missing-reason bug
