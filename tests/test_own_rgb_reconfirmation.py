import copy
import json
import math
from types import SimpleNamespace
import cv2
import numpy as np
import pytest
from harness import own_rgb_reconfirmation as m
from harness import own_route_reconfirmation as route
from harness.own_rgb_homing import Frame
from harness.own_route_reference import Options, install as route_install
from test_own_route_traversed import prepared, frame


def views(angle=.12):
    rng = np.random.default_rng(43)
    K = np.array([[500., 0, 320], [0, 500., 240], [0, 0, 1]])
    uv = rng.uniform([40, 40], [600, 440], (80, 2))
    descriptors = rng.integers(0, 256, (80, 32), dtype=np.uint8)
    first = Frame(1, 1., np.zeros(3), np.eye(4), uv, descriptors, np.ones(80), 'first')
    second = copy.deepcopy(first)
    second.frame_id = 2; second.t = 2.; second.sha256 = 'second'
    second.pose[2] = angle
    H = K @ cv2.Rodrigues(np.array([0., angle, 0.]))[0] @ np.linalg.inv(K)
    q = np.column_stack([uv, np.ones(80)]) @ H.T
    second.uv = q[:, :2]/q[:, 2:]
    return first, second, K


def test_geometry_accepts_changed_planar_view_and_rejects_wrong_correspondences():
    a, b, K = views()
    result = m.geometry(a, b, K)
    assert result['accepted'] and result['inliers'] == 80
    assert result['minimum_optical_angle_rad'] == pytest.approx(.12, abs=1e-5)
    b.uv = np.random.default_rng(5).uniform([0, 0], [640, 480], b.uv.shape)
    assert not m.geometry(a, b, K)['accepted']


def test_one_frame_or_command_yaw_only_cannot_confirm():
    a, b, K = views()
    gate = m.TwoViewGate(K)
    assert gate.observe('B', a)['reason'] == 'second_view_required'
    assert not gate.observe('B', a)['accepted']
    fixed = copy.deepcopy(b); fixed.uv = a.uv.copy()
    assert gate.observe('B', fixed)['reason'] == 'different_angle_required'
    assert gate.observe('B', b)['accepted']


def test_repeated_rgb_and_wrong_semantics_cannot_reuse_verified_pair():
    a, b, K = views()
    gate = m.TwoViewGate(K); gate.observe('B', a)
    assert gate.observe('B', b)['accepted']
    third = copy.deepcopy(b); third.frame_id = 3; third.t = 3.; third.sha256 = 'third'
    assert not gate.observe('B', third, semantic=False)['accepted']
    third.sha256 = a.sha256
    assert gate.observe('B', third)['reason'] == 'repeated_rgb'


def test_old_memory_is_required_for_home_and_must_precede_current():
    a, b, K = views(); gate = m.TwoViewGate(K)
    assert gate.observe('home', a, references=[])['reason'] == 'no_reference'
    assert gate.observe('home', a, references=[b])['reason'] == 'no_reference'
    reference = copy.deepcopy(a); reference.frame_id = 0; reference.t = 0.; reference.sha256 = 'prefix'
    assert not gate.observe('home', a, references=[reference])['accepted']
    assert gate.observe('home', b, references=[reference])['accepted']
    assert reference.frame_id == 0 and np.all(reference.pose == 0)


def test_confirmation_expires_and_never_changes_pose_or_covariance():
    a, b, K = views(); gate = m.TwoViewGate(K)
    gate.observe('B', a); gate.observe('B', b)
    last = copy.deepcopy(b); last.t = 40.; last.frame_id = 40; last.sha256 = 'late'
    before = last.pose.copy()
    assert gate.observe('B', last)['reason'] == 'second_view_required'
    assert np.array_equal(last.pose, before)


class Bank:
    robot_id = 'r3'
    K = np.eye(3)
    def __init__(self):
        self.frames = []
        self.home = []

    def extract(self, rgb, servo, pose, t, frame_id, sha):
        return Frame(frame_id, t, np.asarray(pose).copy(), np.eye(4), np.empty((0, 2)),
            np.empty((0, 32), np.uint8), np.empty(0), sha)


def test_off_is_identity_without_reads_and_full_frame_bytes(monkeypatch):
    class Poison:
        def __getattribute__(self, name):
            raise AssertionError(name)
    p = Poison(); assert route.install(p) is p
    a, _ = prepared(monkeypatch); b, _ = prepared(monkeypatch)
    route.install(b)
    assert json.dumps(frame(a), sort_keys=True) == json.dumps(frame(b), sort_keys=True)
    assert json.dumps(a.snapshot(), sort_keys=True) == json.dumps(b.snapshot(), sort_keys=True)


def test_on_composes_accelerated_receive_and_does_not_declare_from_missing_home(monkeypatch):
    c, active = prepared(monkeypatch)
    route_install(c, Options(return_own_free_astar=True), traversed_free='footprint_history_v1')
    c.route = {'samples': [{'pose': [0, 0, 0]}], 'length_m': 0.}
    def candidate(pose):
        c.cursor = 1
        return np.zeros(2)
    c._return_target = candidate
    route.install(c, rgb_reconfirmation=m.OPTION, memory=Bank())
    _, trace = frame(c)
    assert active == [True] and trace['rgb_reconfirmation']['calls'] == 1
    c._return_target(np.zeros(3))
    assert c.cursor == 0 and not c.declared
    assert c._rgb_reconfirmation_gate.rows[-1]['reason'] == 'no_reference'


def test_B_63004_pickup_hue_wrong_track_stale_frame_and_partial_extent_rejected(monkeypatch):
    c, _ = prepared(monkeypatch, near=True)
    c.entities['B']['observation'] = dict(candidate_id=1)
    c.explorer.goal.tracks = [dict(id=1, last_t=2.)]
    c.labels = np.ones((12, 16), int)
    patch = dict(component=1, track_id=1, confirmed_t=1., center_odom_m=[.1, 0], rect_sides_m=[.6, 1.4])
    c.current_patches = [patch]
    B = np.full((12, 16, 3), [51, 102, 242], np.uint8)
    pickup = np.full((12, 16, 3), [31, 92, 179], np.uint8)
    assert route.current_B(c, np.zeros(3), B, 2.)[0]
    assert not route.current_B(c, np.zeros(3), pickup, 2.)[0]
    assert not route.current_B(c, np.zeros(3), B, 3.)[0]
    patch['track_id'] = 2
    assert not route.current_B(c, np.zeros(3), B, 2.)[0]
    patch['track_id'] = 1; patch['rect_sides_m'] = [.2, .5]
    assert not route.current_B(c, np.zeros(3), B, 2.)[0]


def test_failed_B_gate_prevents_arrival_side_effects_and_has_finite_acquisition(monkeypatch):
    c, _ = prepared(monkeypatch, near=True)
    c.explorer.goal.tracks = []
    c.current_patches = [{'confirmed_t': 1.}]; c.labels = np.ones((12, 16))
    route.install(c, rgb_reconfirmation=m.OPTION, memory=Bank())
    frame(c)
    for t in range(3, 9):
        c._arrival(t, t, np.zeros(3), False)
    assert not c.reached and not any(e['reason'] == 'goal_reached' for e in c.events)
    assert len(c._rgb_reconfirmation_acquisitions) == 1
    request = c._rgb_reconfirmation_acquisitions[0]
    c.heading_host.command(t=23., pose=np.zeros(3))
    assert request['status'] == 'exhausted'
    assert request['ended_t']-request['started_t'] <= 21.


def test_corridor_veto_happens_before_accepted_match_side_effects(monkeypatch):
    c, _ = prepared(monkeypatch)
    c.graph.match = lambda sample, node=None: dict(status='accepted', node=0, pose=[.4, .1, 0], reason='fixture')
    route.install(c, rgb_reconfirmation=m.OPTION, memory=Bank())
    frame(c)
    result = c.graph.match(dict(pose=[0, 0, 0], t=2., frame_id=2), 0)
    assert result['status'] == 'rejected' and result['ungated_status'] == 'accepted'
    assert not c.offsets and not c.match_nodes
    assert not any(e['reason'] == 'route_local_match' for e in c.events)


def test_new_B_confirmation_does_not_write_entity_event_graph_or_cue(monkeypatch):
    c, _ = prepared(monkeypatch)
    route.install(c, rgb_reconfirmation=m.OPTION, memory=Bank())
    frame(c)
    del c.entities['B']
    before = json.dumps((c.events, c.cues, c.graph.snapshot()), sort_keys=True)
    c._entity('B', [.1, 0], 2., 2, 'x', observation={'candidate_id': 1})
    assert 'B' not in c.entities
    assert json.dumps((c.events, c.cues, c.graph.snapshot()), sort_keys=True) == before
    assert c._rgb_reconfirmation_gate.rows[-1]['reason'] == 'semantic_or_association_rejected'


def test_new_node_capture_is_causal_and_cannot_extend_home(monkeypatch):
    c, _ = prepared(monkeypatch)
    bank = Bank()
    route.install(c, rgb_reconfirmation=m.OPTION, memory=bank)
    original = c.graph.observe
    def node(sample):
        original(sample)
        # Force this pure fixture's current sample to be a newly taught node.
        c.graph.nodes[-1]['frame_id'] = sample['frame_id']
    c.graph.observe = node
    _, trace = frame(c)
    assert [f.frame_id for f in bank.frames] == [2]
    assert bank.home == [] and trace['rgb_reconfirmation']['home_references'] == 0
    assert trace['rgb_reconfirmation']['captured'] == 1
    assert not c._rgb_reconfirmation_gate.rows  # no same-frame self match
