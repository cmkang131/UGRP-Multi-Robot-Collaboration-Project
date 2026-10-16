# Nav2 AMCL Python numerical translation

Upstream revision `235fc5ce55bdf94d9be360fdbca39d89dc0e4f74`, fetched
2026-10-17. Sources and exact SHA256 are in provenance.json. Original source
copyright/license headers are preserved in upstream/. algorithms.py is a
modified translation distributed under LGPL-2.1-or-later; COPYING.LIB is the
complete license. This is a numerical port, not a ROS node or binary ABI.

- motion(): differential_motion_model.cpp lines 45–131, local odometry delta
  adapter sets old_pose=(0,0,0), vectorized three independent normal samples.
  Original 0.01m bearing guard, backward/forward symmetric noise retained.
- likelihood(): likelihood_field_model.cpp sensorFunction lines 50–145,
  existing projected chassis endpoints replace range/bearing + laser transform.
  Original step, off-map distance, Gaussian hit/random and `1+sum(pz^3)` retained.
- sample_limit()/resample(): pf.c pf_resample_limit/pf_update_resample,
  pf_kdtree.c .5m/.5m/10deg bins. NumPy searchsorted replaces the linear CDF
  lookup with the same probability law. Batch RNG differs from libc drand48;
  bitwise equivalence is not claimed. Strict > stop and single-bin max retained.
  pf_z=.99 is passed directly as upstream does, not inverse-normal transformed.
- Recovery EMA .001/.1 comes from existing own_map_amcl_vendor/augmented.py
  and published augmented-MCL, intentionally active for kidnapped recovery.
- max=100000/min=2000 matches existing UGRP own_map_amcl_vendor/kld.py,
  rather than Nav2 ROS launch default max2000/min500. This is a fixed compute
  budget for global distribution, not tuned to evaluation results.
- StaticField is an authored-map raster adapter using scipy EDT, .01m/2m from
  existing UGRP AMCL field.py. No simulator bodies or spawn input.
- sigma=.0202m is the prior four-scan max P95 20.2mm used as sigma directly;
  no Gaussian confidence claim, no fitting to current replay truth.
- Readiness is a separate UGRP navigation gate on full weighted P95 position
  and circular angle plus inherited handoff coupled budget; no best-cluster
  acceptance. Compact wrong convergence is counted by a separate evaluator.

Probabilistic Robotics motion/sensor/filter chapters and Fox 2001 are algorithm
references, not evidence that RGB virtual scans attain lidar accuracy.

## Fixed-population diagnostic profiles

`fixed_population_v1` sets min=max=100000 (existing global cap), retaining the
same motion, sigma, likelihood, and multinomial resampling. It tests whether
early KLD reduction discards hypotheses. `nav2_sigma_fixed_v1` differs only by
Nav2's published sigma_hit=.2m. Both are standard documented parameter settings,
not fitted to new truth or new scan matchers. Candidate calibration profile stays
separate; an unready candidate is never executed as transport.

## Textbook/official probability model diagnostic

`likelihood_product_v1` retains min=max100000 and sigma .0202m but uses the
fixed upstream `likelihood_field_model_prob.cpp` do_beamskip=false branch:
ceil(count/max_beams), sum log(pz), exp(log_p). The additional original file and
hash are preserved. This is the textbook likelihood-field product, an existing
Nav2 sensor option; no new scan matcher. Its independence assumption can be
overconfident for neighboring camera columns, so it does not grant live admission.

Python motion normalizes final heading to S1; the C++ body leaves an unbounded
heading. Native motion parity is checked modulo 2pi, not raw yaw bytes. This
coordinate choice can change histogram bins at the yaw seam, so full native
ROS filter equivalence is not claimed.
