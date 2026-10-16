"""Array/scheduling-only regressions; no simulator, renderer or model calls."""
import ast
import sys
from pathlib import Path
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from scripts.warp5_render import blend_native
from scripts.warp5_batch import transform_runner,sim_clock,review_due,review_cameras
from scripts.warp5_e2e import AsyncDecisions


def test_native_setup_clock_never_moves_backwards_on_gpu_export():
    # Exact16-world R1d epoch from initial-state.json; old absolute rounding
    # violated the unchanged control_tape accumulator guard before first step.
    origin=1.3000000000000178
    assert 2000*(round(origin,9)-origin)<-1e-12
    assert sim_clock(origin,0,.1)==origin
    clocks=[sim_clock(origin,t,.1) for t in range(3001)]
    assert all(b>a for a,b in zip(clocks,clocks[1:]))


def test_review_camera_is_available_before_first_non_grid_playback():
    # Review cache readiness does not depend on native setup's clock phase.
    cameras=[('cctv_top','cctv_top',(320,240)),('r2','r2__robot_cam',(640,480))]
    cache={(0,'r1'):b'own'}
    assert review_due(cache,1,cameras,1.7)
    cache.update({(0,'cctv_top'):b'top',(0,'r2'):b'peer'})
    assert not review_due(cache,1,cameras,1.7)
    assert review_due(cache,1,cameras,2.)
    assert review_due(cache,2,cameras,1.7)  # every world, not just world0


def test_playback_selects_its_requested_top_not_first_alphabetical_cctv():
    cameras=[(n,n,(320,240)) for n in ('r1','r2','r3','cctv_front_left','cctv_top','cctv_top_east')]
    assert [n for n,_,_ in review_cameras(cameras,{'r1'})]==['r2','r3','cctv_top']


def test_native_model_group_changes_only_documented_batched_values():
    from scripts.warp7_native_models import layout_digest
    aa={'mass':np.array([[1.]]),'index':np.array([2,3])}
    bb={'mass':np.array([[8.]]),'index':np.array([2,3])}
    assert layout_digest(aa,{'nv':2},{'mass'})==layout_digest(bb,{'nv':2},{'mass'})
    bb['index'][1]=4
    assert layout_digest(aa,{'nv':2},{'mass'})!=layout_digest(bb,{'nv':2},{'mass'})
    assert layout_digest(aa,{'nv':2},{'mass'})!=layout_digest(aa,{'nv':3},{'mass'})


def test_native_alpha_keeps_opaque_occluders_and_world_layer_order():
    opaque=np.zeros((2,1,2,3));opaque[:,:,1]=100
    red=np.zeros_like(opaque);red[:,:,:,0]=200
    green=np.zeros_like(opaque);green[:,:,:,1]=200
    mask=np.array([[[True,False]],[[True,False]]])
    result=blend_native(opaque,[(red,mask),(green,mask)],[.3,.35],np.array([[0,1],[1,0]]))
    # Explicit GL front/back + back/front sequence; order is per world.
    expected=[]
    for order in ([0,1,1,0],[1,0,0,1]):
        pixel=np.zeros(3)
        for i in order:pixel=[.3,.35][i]*[red,green][i][0,0,0]+(1-[.3,.35][i])*pixel
        expected.append(pixel)
    np.testing.assert_allclose(result[:,0,0],expected)
    np.testing.assert_array_equal(result[:,:,1],opaque[:,:,1])


@pytest.mark.parametrize('kind,path,name,advances',[('carry','scripts/run_solo_grasp_act_teacher.py','run',1),('selfmap','scripts/run_self_map_diagnostic.py','acquire',2)])
def test_real_controller_source_has_exact_adapter_barriers(kind,path,name,advances):
    # Compilation only; function bodies and native factories are never run.
    text=(ROOT/path).read_text()
    fn,audit=transform_runner(text,{'make_executor':object()},object(),kind)
    assert audit['edits']=={'setup':1,'advance':advances}
    assert fn.__name__==name
    assert fn.__code__.co_flags & 0x20  # generator owns its original locals


def test_adapter_fails_closed_when_advance_semantics_change():
    with pytest.raises(ValueError,match='scheduling shape changed'):
        transform_runner('def run():\n    tick=0\n    return 2\n',{},None,'carry')


def test_legacy_e2e_scheduler_has_isolated_setup_and_005s_barrier():
    text=(ROOT/'scripts/run_e2e_ownmap_live.py').read_text()
    fn,audit=transform_runner(text,{},object(),'e2e')
    assert audit['edits']=={'setup':1,'advance':1}
    assert fn.__code__.co_flags & 0x20


def test_live_alert_rejection_never_submits_a_call():
    calls=[];broker=AsyncDecisions(lambda request:calls.append(request))
    try:
        with pytest.raises(ValueError,match='endpoint alert'):
            broker.submit(0,'r1',{'own':'rgb'},live=True)
        assert calls==[] and not broker.pending
    finally:broker.close()


def test_slow_world_does_not_block_peer_and_reset_discards_old_reply():
    import threading
    release=threading.Event();fast_done=threading.Event()
    def call(r):
        if r['slow']:release.wait(1)
        else:fast_done.set()
        return r
    broker=AsyncDecisions(call,workers=2)
    try:
        broker.submit(0,'r1',{'slow':True});broker.submit(1,'r1',{'slow':False})
        assert fast_done.wait(1)
        assert broker.poll(1,'r1')=={'slow':False}
        assert broker.poll(0,'r1') is None
        broker.reset_world(0);release.set()
        assert broker.poll(0,'r1') is None
    finally:release.set();broker.close()
