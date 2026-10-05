import pytest

from harness.frame_storage import DEFAULT_PROFILE, PROFILES, FrameStoragePolicy


def times(hz, seconds):
    step = 1.0 / hz
    return [i * step for i in range(int(round(seconds * hz)) + 1)]


def test_default_writes_no_frame_file_only_for_smoke():
    assert DEFAULT_PROFILE == "none_v1"
    for split in ("smoke",):
        policy = FrameStoragePolicy(split=split)
        assert not any(policy.decide("r1", t)["saved"] for t in times(5, 10))
        assert policy.record()["streams"]["r1"] == {"frames": 51, "saved": 0, "decision": 0, "periodic": 0}
        assert policy.record()["store"] == "none"


@pytest.mark.parametrize("split", [None, "dev", "diag", "test", "holdout", "final", "cohort"])
def test_no_default_profile_outside_smoke_so_a_cohort_never_loses_frames_by_omission(split):
    with pytest.raises(ValueError):
        FrameStoragePolicy(split=split)
    assert FrameStoragePolicy("all_v1", split=split).profile == "all_v1"


def test_all_v1_is_an_explicit_opt_in_that_keeps_every_frame():
    for split in (None, "test", "dev"):
        policy = FrameStoragePolicy("all_v1", split=split)
        assert all(policy.decide("r1", t)["saved"] for t in times(5, 10))
        assert policy.record()["streams"]["r1"] == {"frames": 51, "saved": 51, "decision": 0, "periodic": 0}


def test_dev_profile_keeps_one_periodic_frame_per_sim_second():
    policy = FrameStoragePolicy("dev_1hz_decisions_v1", split="dev")
    kept = [t for t in times(5, 10) if policy.decide("r1", t)["saved"]]
    # 0.2 s steps accumulate float error (e.g. 5 * 0.2 != 1.0 exactly); one frame per second still.
    assert [round(t, 6) for t in kept] == [float(s) for s in range(11)]


def test_decision_frames_always_kept_and_do_not_move_the_clock():
    policy = FrameStoragePolicy("dev_1hz_decisions_v1", split="dev")
    assert policy.decide("r1", 0.0)["why"] == "periodic"
    assert policy.decide("r1", 0.2, decision=True, reason="capture_request") == \
        {"saved": True, "why": "decision:capture_request"}
    assert policy.decide("r1", 0.4)["saved"] is False
    assert policy.decide("r1", 1.0)["why"] == "periodic"
    counts = policy.record()["streams"]["r1"]
    assert counts == {"frames": 4, "saved": 3, "decision": 1, "periodic": 2}


def test_streams_are_independent():
    policy = FrameStoragePolicy("dev_1hz_decisions_v1", split="diag")
    assert policy.decide("r1", 0.0)["saved"] and policy.decide("r2", 0.2)["saved"]
    assert not policy.decide("r1", 0.4)["saved"]
    assert policy.decide("top", 0.6)["saved"]


@pytest.mark.parametrize("split", [None, "test", "holdout", "final", "cohort"])
def test_reduced_profile_refused_outside_dev(split):
    with pytest.raises(ValueError):
        FrameStoragePolicy("dev_1hz_decisions_v1", split=split)


def test_unknown_profile_refused_and_profiles_frozen():
    with pytest.raises(ValueError):
        FrameStoragePolicy("dev_1hz")
    assert PROFILES["all_v1"].period_s is None and not PROFILES["all_v1"].reduced
    assert PROFILES["none_v1"].store == "none" and PROFILES["mp4_v1"].store == "mp4"
    assert PROFILES["dev_1hz_decisions_v1"].period_s == 1.0
