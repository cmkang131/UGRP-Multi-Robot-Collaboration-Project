# Loaded-motion process-noise rule (PROPOSED, v105 label) - params.motion_loaded.noise_abs / noise_rel

Data: v102 loaded-pair calibration raw (latA latB fwdA fwdB), FIT split only (roles fit, fit_duration); truth
(eval_only/trajectory.jsonl) used only as a calibration target (as #376/#378). Mean model = a04371f6 (affine dead zone, gain, tau, tau_stop)
through F.simulate(). Both robots (r1 = +u, r2 = -u) are used; they are mirror images, so n is NOT doubled independent data.

Statistic: residual = truth body-frame displacement increment over an H-window (H = 0.5, 1, 2 s, stride 0.05 s, body frame at window start)
minus the mean-model increment. Groups (axis, kind, H); kind = driven (commanded axis) / idle (other axis), settled drive only
(>= 3 lags into the step). Rest windows excluded (rest_noise=false: the PF injects no noise at rest).
Implied std s = RMS(residual) / sqrt(DT*H)  (PF: white per-step velocity noise, position += v*dt; verified against predict_to, unit_check_result.json).

Estimator (moment matching, = #376 fit_noise, not exact ML): NNLS  s ~ rel*vbar + abs, weights sqrt(n), vbar = mean |model velocity| in the window.
Exact Gaussian ML (composite likelihood) on the same windows is a cross-check (agrees: abs 1.7e-4/1.0e-4, rel 0.023/0.020).
Floor: abs = max(abs, NOISE_ABS_FLOOR = 0.002) (#376, unchanged). Turn (index 2): copied from the parent (no yaw excitation in v102).
Acceptance (#376): 2-sigma coverage >= 0.90 of sub-window residuals (H = 1, 2, 4 s). NEES (held-out, Bar-Shalom 2001): reported against
chi2(2) [0.0506, 7.378], one-sided 5.99, and averaged-NEES bound chi2(2N)/N; NEES is informational (no new threshold).

Result: raw abs 1.5e-4 / 0.9e-4 m/s is below the floor, so abs = 0.002 (the floor is the estimate); rel 0.0156 / 0.0166.
See fit_noise_loaded_result.json, nees_summary.json. Not applied anywhere.
