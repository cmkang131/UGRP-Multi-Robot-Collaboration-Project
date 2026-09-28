"""Explicit default measurement adapter for memory; injected sources use geometry."""
from harness.owncam_landmarks import GeometricLandmarkProvider


def memory_inputs(static_map, params, seed, pose_source, landmark_provider, *, pose_factory=None):
    if pose_source is not None:
        provider = landmark_provider if landmark_provider is not None else GeometricLandmarkProvider()
        return pose_source, provider, lambda: {}
    from harness.owncam_pose_source import OwnCamPoseSource
    from harness.owncam_landmark_tags import TagLandmarkProvider
    from harness.m1_owncam_memory import _RecordingDetector
    pose = (pose_factory or OwnCamPoseSource)(static_map, params, seed=seed)
    pose.detector = _RecordingDetector(pose.detector)
    provider = landmark_provider if landmark_provider is not None else TagLandmarkProvider(static_map, params)
    return pose, provider, lambda: {'tag_detections': pose.detector.last}


def result_label(provider):
    from harness.owncam_landmark_tags import TagLandmarkProvider, INTERIM_LABEL
    return INTERIM_LABEL if isinstance(provider, TagLandmarkProvider) else 'own-camera geometry'
