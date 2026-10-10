"""Explicit DEV prediction-only handling of unavailable camera calibration.

The camera transform is never synthesized or adjusted to archived frames.
Unmeasured postures supply no measurement, while the existing commanded
motion prediction and its uncertainty remain available. Other provider
failures remain hard execution failures. Historical default off is identity.
"""
import copy
import math
from dataclasses import replace

OPTION = 'defer_unmeasured_v1'


def attach(runtime, *, pose_validity='off'):
    if pose_validity == 'off':
        return runtime
    if pose_validity != OPTION:
        raise ValueError('unknown pose validity option')
    from harness.zone_final_pair_contract import camera_record
    from harness.vision_pose_source_final import CalibrationError
    inner = runtime.pose.provider
    pf = inner.loc._pf
    old = inner.on_frame
    audit = dict(option=OPTION, gt_inputs=False, count=0, rows=[])

    def frame(now, rgb):
        if (inner.failure is None and now >= pf.t and pf.settled(now)
                and (inner._last_frame_t is None or now > inner._last_frame_t)):
            state = 'loaded' if pf.load.loaded else 'unloaded'
            try:
                camera_record(inner.calibration, state, inner.servo)
                pf.column_model_for(inner.servo)
            except CalibrationError as exc:
                if not str(exc).startswith('UNMEASURED_V3_CAMERA_POSTURE:'):
                    raise
                # Preserve actual failure cause and do not stamp a new fix.
                audit['count'] += 1
                row = dict(t=float(now), code='UNMEASURED_V3_CAMERA_POSTURE',
                    reason=str(exc), action='prediction_only', visual_update=False,
                    commanded_servo=dict(inner.servo))
                audit['rows'].append(row)
                runtime.events.append(dict(robot_id=runtime.robot_id,
                    event='dev_light_would_stop', occurrence=audit['count'], **row))
                inner._last_frame_t = float(now)
                inner.counts['frames'] += 1
                inner.counts['rejected_frames'] += 1
                pf.update_obs(now, None, dict(inner.servo))
                report = inner.report(now)
                quality = copy.deepcopy(report.observation_quality or {})
                quality.update(accepted=False, informative=False,
                    skipped_camera_posture=row, visual_update=False)
                return replace(report, observation_quality=quality)
        return old(now, rgb)

    inner.on_frame = frame
    previous_record = runtime.record
    runtime.record = lambda: {**previous_record(), 'pose_validity': copy.deepcopy(audit)}
    runtime.pose_validity_audit = audit
    return runtime


def finite_record(value):
    """Explicit null + field paths for invalid reports, including failure logs."""
    paths = []
    def visit(item, path):
        if isinstance(item, float) and not math.isfinite(item):
            paths.append(path)
            return None
        if isinstance(item, dict):
            return {k: visit(v, path+'.'+str(k)) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [visit(v, path+'['+str(i)+']') for i, v in enumerate(item)]
        return item
    out = visit(value, '$')
    out['nonfinite_record_fields'] = paths
    return out
