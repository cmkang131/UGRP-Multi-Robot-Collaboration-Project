"""Array/scheduling-only regressions; no simulator, renderer or model calls."""
import ast
import sys
from pathlib import Path
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from scripts.warp5_render import blend_native
from scripts.warp5_batch import transform_runner


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
