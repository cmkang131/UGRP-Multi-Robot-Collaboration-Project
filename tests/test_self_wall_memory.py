"""Stage D of the own wall map: ``SelfWallMemory`` options and their off state. Refs #216. No simulation."""
import copy
import json
import math
import unittest

from harness.coela_modules import Memory
from harness.self_wall_memory import SelfWallMemory, render_self_walls, select_for_text, validate_record


def cargo(cid="small_box_01", seen=True):
    return {"cargo_id": cid, "current_view": seen, "observed_sim_time": 1.5}


def observation(self_walls=None, sim_time=2.0):
    obs = {"observation_id": "o-1", "sim_time": sim_time, "cargo": [cargo()]}
    if self_walls is not None:
        obs["self_walls"] = self_walls
    return obs


def record(t, view=1, seg=None, posture="high", load=True):
    return {"t_sim": t, "seg": seg if seg is not None else [(2.1, 0.21, 2.4, -0.14, 0.40)], "posture": posture, "load": load, "view_index": view}


def dump(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


class OffStateTests(unittest.TestCase):
    def sequence(self, memory, with_self_walls):
        memory.observe(observation([record(1.0)] if with_self_walls else None), 2.0)
        memory.observe(observation([record(1.0), record(3.0, 2)] if with_self_walls else None, sim_time=4.0), 4.0)
        memory.receive({"message_id": "m1", "sender_id": "r2", "kind": "intent", "content": "I take small_box_01",
                        "observed_ids": ["small_box_01"], "sent_sim_time": 3.0, "intent_ttl_s": 12.})
        memory.decisions.append({"t": 1})
        return memory.snapshot()

    def test_default_snapshot_is_byte_identical_to_memory(self):
        plain = self.sequence(Memory("r1", clock=lambda: 5.), False)
        off = self.sequence(SelfWallMemory("r1", clock=lambda: 5.), False)
        self.assertEqual(dump(plain), dump(off))

    def test_default_ignores_self_walls_in_the_observation(self):
        plain = self.sequence(Memory("r1", clock=lambda: 5.), False)
        off = self.sequence(SelfWallMemory("r1", clock=lambda: 5.), True)
        self.assertEqual(dump(plain), dump(off))
        self.assertNotIn("self_walls", off)
        self.assertNotIn("self_walls_text", off)

    def test_text_option_needs_the_records_option(self):
        with self.assertRaises(ValueError):
            SelfWallMemory("r1", self_walls_text=True)

    def test_off_even_accepts_malformed_self_walls_without_error(self):
        memory = SelfWallMemory("r1")
        memory.observe(observation([{"garbage": 1}]), 2.0)
        self.assertEqual(memory.self_walls, [])


class RecordsOnTests(unittest.TestCase):
    def memory(self, **kw):
        return SelfWallMemory("r1", self_walls_enabled=True, clock=lambda: 5., **kw)

    def test_records_reach_the_snapshot_next_to_the_existing_keys(self):
        m = self.memory()
        m.observe(observation([record(1.0)]), 2.0)
        snap = m.snapshot()
        self.assertEqual(snap["self_walls"], [{"t_sim": 1.0, "seg": [[2.1, 0.21, 2.4, -0.14, 0.4]], "posture": "high",
                                               "load": True, "view_index": 1}])
        self.assertEqual({"observations", "peer_reports", "peer_observations", "expired_peer_intents",
                          "own_execution_history", "own_decisions"} - set(snap), set())
        self.assertNotIn("self_walls_text", snap)
        json.dumps(snap)

    def test_same_observation_twice_is_one_record_but_repeated_sightings_are_kept(self):
        m = self.memory()
        for _ in range(3):
            m.observe(observation([record(1.0, 1)]), 2.0)
        self.assertEqual(len(m.self_walls), 1)
        m.observe(observation([record(3.0, 2), record(5.0, 3)]), 6.0)
        self.assertEqual([r["t_sim"] for r in m.self_walls], [1.0, 3.0, 5.0])      # no de-duplication of walls seen again

    def test_snapshot_carries_the_newest_records_only(self):
        m = self.memory(snapshot_records=2)
        m.observe(observation([record(float(i), i) for i in range(1, 6)]), 6.0)
        self.assertEqual([r["view_index"] for r in m.snapshot()["self_walls"]], [4, 5])
        self.assertEqual(len(m.self_walls), 5)

    def test_malformed_records_are_rejected(self):
        for bad in ({"t_sim": float("nan"), "seg": [(1, 0, 1, 0, 0.4)], "posture": "high", "load": True, "view_index": 1},
                    record(1.0, seg=[]), record(1.0, seg=[(-1.0, 0, 1, 0, 0.4)]), record(1.0, seg=[(1, 4.0, 1, 0, 0.4)]),
                    record(1.0, seg=[(1, 0, 1, 0)]), {**record(1.0), "load": "yes"}, {**record(1.0), "view_index": 1.5}, "x"):
            with self.assertRaises(ValueError, msg=str(bad)):
                validate_record(bad)
        self.assertEqual(validate_record(record(1.0, seg=[(1, 0, 2, 0.1, None)]))["seg"][0][4], None)

    def test_peer_claims_never_overwrite_the_own_walls(self):
        m = self.memory()
        m.observe(observation([record(1.0)]), 2.0)
        before = copy.deepcopy(m.self_walls)
        m.receive({"message_id": "m1", "sender_id": "r2", "kind": "observation", "content": "wall at 0.5 m straight ahead",
                   "observed_ids": [], "sent_sim_time": 3.0, "self_walls": [record(9.0, 99)]})
        self.assertEqual(m.self_walls, before)
        self.assertEqual(m.snapshot()["self_walls"][0]["t_sim"], 1.0)
        self.assertEqual(len(m.snapshot()["peer_reports"]), 1)             # the claim is a peer report, nothing else


class TextOnTests(unittest.TestCase):
    def test_text_lists_newest_first_with_age_and_is_deterministic(self):
        m = SelfWallMemory("r1", self_walls_enabled=True, self_walls_text=True)
        m.observe(observation([record(10.0, 1), record(12.3, 2, seg=[(2.1, math.radians(12), 2.4, math.radians(-8), 0.40),
                                                                       (1.2, math.radians(88), 1.2, math.radians(70), None)],
                                                    load=False)], sim_time=14.0), 14.0)
        text = m.snapshot()["self_walls_text"]
        self.assertEqual(text, m.snapshot()["self_walls_text"])
        self.assertLess(text.index("t=12.3"), text.index("t=10.0"))
        self.assertIn("t=12.3 (age 1.7s) [high, not carrying] 2.1m @ 12° → 2.4m @ -8° h=0.40 ; 1.2m @ 88° → 1.2m @ 70°", text)
        self.assertIn("2 observations", text)
        self.assertIn("positive = left", text)

    def test_text_is_bounded_and_thinned(self):
        recs = [record(float(t), t) for t in range(0, 60)]
        picked = select_for_text(recs, max_obs=6, min_gap_s=2.0)
        self.assertEqual([r["t_sim"] for r in picked], [59.0, 57.0, 55.0, 53.0, 51.0, 49.0])
        text = render_self_walls(recs, now=60.0)
        self.assertEqual(text.count("t="), 6)
        self.assertLess(len(text), 1500)

    def test_segments_per_observation_are_capped(self):
        many = [(1.0 + i*0.1, 0.1, 1.5 + i*0.1, 0.2, 0.4) for i in range(7)]
        text = render_self_walls([record(1.0, seg=many)], max_segments=4)
        self.assertIn("+3 more", text)

    def test_empty(self):
        self.assertEqual(render_self_walls([]), "self_walls: no wall observed yet")


if __name__ == "__main__":
    unittest.main()
