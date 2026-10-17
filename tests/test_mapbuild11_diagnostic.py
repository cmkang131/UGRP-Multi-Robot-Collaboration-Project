"""DEV recording can continue an unresolved belief without admission or GT."""
import numpy as np
from harness.mapbuild10_diagnostic import DiagnosticCorrection
from tests.test_mapbuild10 import STATIC,CAL,REQ,ZONE


def test_dev_light_uses_only_the_unqualified_belief_and_preserves_gate():
    d=DiagnosticCorrection(STATIC,CAL,REQ,ZONE,enabled=True)
    particles=d.amcl.particles.copy();rng=d.amcl.rng.bit_generator.state
    result=d.initialize_static(dev_light=True)
    assert result['status']=='accepted' and result['would_stop']
    assert not result['production_qualified'] and not result['runtime_qualified']
    assert not d.navigation_ready and d.amcl.current['ready_for_handoff'] is False
    np.testing.assert_array_equal(d.amcl.particles,particles)
    assert d.amcl.rng.bit_generator.state==rng
    # The unchanged normal path still rejects this exact distribution.
    assert d.initialize_static()['status']=='rejected'
