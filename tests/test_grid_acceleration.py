import json
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pytest
from harness.grid_acceleration import using,enabled,OPTION,install
from harness.self_odom_grid import OdomGrid,ray_cells
from harness.public_navigation_persistent import raytrace_cells
from harness.wall_confidence import weighted_insert


def test_traversal_cells_and_order_including_boundary_ties():
    rng=np.random.default_rng(47001)
    pairs=[(a,b) for a in [(0.,0.),(-1.,1.),(.1,-.1)] for b in [(0.,0.),(1.,0.),(0.,1.),(-1.,-1.),(.3,.3)]]
    pairs+=list(zip(rng.uniform(-4,4,(250,2)),rng.uniform(-4,4,(250,2))))
    for start,end in pairs:
        for resolution in (.05,.1):
            before=ray_cells(start,end,resolution)
            with using(OPTION):after=ray_cells(start,end,resolution)
            assert before==after
            a,b=np.floor(np.asarray(start)/resolution).astype(int),np.floor(np.asarray(end)/resolution).astype(int)
            before=list(raytrace_cells(a,b))
            with using(OPTION):after=list(raytrace_cells(a,b))
            assert before==after


def test_weighted_and_plain_maps_bytes_identical():
    a,b=OdomGrid('r3'),OdomGrid('r3')
    rng=np.random.default_rng(9)
    for _ in range(8):
        camera=rng.uniform(-.3,.3,2);segments=rng.uniform(-2,2,(3,2,2));weights=[.2,.6,1.]
        weighted_insert(a,camera,segments,weights);a.insert(camera,segments)
        with using(OPTION):
            weighted_insert(b,camera,segments,weights);b.insert(camera,segments)
        assert json.dumps(a.export())==json.dumps(b.export())


def test_default_identity_nested_exception_and_thread_isolation():
    class Mapper:
        def receive(self,**kw):return enabled()
    a=Mapper();assert install(a) is a and not a.receive()
    b=install(Mapper(),map_acceleration=OPTION)
    assert b.receive() and not a.receive() and not enabled()
    with using(OPTION):
        assert enabled()
        with ThreadPoolExecutor(1) as pool:assert pool.submit(enabled).result() is False
        with using('off'):assert not enabled()
        assert enabled()
    with pytest.raises(RuntimeError):
        with using(OPTION):raise RuntimeError()
    assert not enabled()
    with pytest.raises(ValueError):install(a,map_acceleration='invalid')
