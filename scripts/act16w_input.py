"""ACT16 opt-in input intervention, shared by training and deployment.

Layout copied from grasp_act_contract.py at act-train 3f99d58c: 16 issued
commands, each [wheel4, duration4, PWM5, age1], then task tokens and clocks.
Zeros in normalized continuous columns mean the TRAIN mean, not zero PWM.
There is no simulator, teacher, truth, reward or controller capability here.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

MODES = ("off", "wheel_pulse_train_mean")
HISTORY = 16
STRIDE = 14
HISTORY_END = HISTORY * STRIDE
CONTEXT_DIM = 252
MASK_COLUMNS = tuple(j * STRIDE + k for j in range(HISTORY) for k in range(8))


def transform_state(state, mode="off"):
    if mode not in MODES:
        raise ValueError("unknown history_causal_split_v1 mode")
    if mode == "off":
        return state
    if state.ndim not in (1, 2) or state.shape[-1] != CONTEXT_DIM:
        raise ValueError("normalized ACT context with task tokens required")
    # numpy and torch support the same column index operation. Clone only for
    # the candidate so baseline identity and RNG are untouched.
    changed = state.copy() if isinstance(state, np.ndarray) else state.clone()
    changed[..., list(MASK_COLUMNS)] = 0.
    return changed


def transform_batch(batch, mode="off"):
    if mode == "off":
        return batch
    return {**batch, "observation.state": transform_state(batch["observation.state"], mode)}


def contract_check(contract):
    if (contract.HISTORY, contract.ACTION_DIM, contract.CHUNK, contract.PERIOD_S,
            contract.CONTEXT_DIM) != (16, 14, 8, .1, CONTEXT_DIM):
        raise ValueError("input intervention requires the frozen v6 ACT layout")


def save_actor(policy, output, stats, provenance, *, mode="off", done_mode="balanced_bce_v1"):
    from harness import grasp_act_contract as c
    from harness.grasp_act_data import sha256, write_json
    from harness.grasp_act_policy import save_actor as base_save
    contract_check(c)
    if mode not in MODES:
        raise ValueError("unknown history mode")
    base_save(policy, output, stats, provenance, done_mode=done_mode)
    output = Path(output)
    meta = json.loads((output / "adapter.json").read_text())
    # A stock loader rejects v3 instead of silently deploying B with full history.
    meta.update(schema="ugrp.grasp_act.adapter.act16w.v3",
                history_causal_split_v1=mode, done_mode=done_mode,
                input_transform={"history": HISTORY, "stride": STRIDE,
                                 "columns": list(MASK_COLUMNS) if mode != "off" else [],
                                 "replacement": "TRAIN mean in normalized coordinates",
                                 "train_inference_identical": True})
    write_json(output / "adapter.json", meta)
    write_json(output / "SHA256.json", {n: sha256(output / n)
               for n in ("model.safetensors", "config.json", "adapter.json")})


class Act16wActor:
    def __init__(self, base, mode):
        self.base, self.mode = base, mode
        self.policy, self.stats = base.policy, base.stats

    def predict(self, observation, jpegs):
        import torch
        from harness import grasp_act_contract as c
        from harness.grasp_act_policy import observation_batch
        batch = transform_batch(observation_batch(observation, jpegs, self.stats), self.mode)
        batch = {k: torch.from_numpy(v.copy()).unsqueeze(0).to(self.base.device) for k, v in batch.items()}
        with torch.inference_mode():
            values = self.policy.predict_action_chunk(batch)[0].cpu().numpy()
        values = self.base.decode_predictions(values)
        if values.shape != (c.CHUNK, c.ACTION_DIM) or not np.isfinite(values).all():
            raise ValueError("invalid ACT chunk; no fallback")
        return values.tolist()

    @classmethod
    def load(cls, root, *, device="cpu"):
        import draccus
        from safetensors.torch import load_file
        from harness import grasp_act_contract as c
        from harness.grasp_act_data import IMAGE_HW, MODEL_IMAGE_HW, IMAGE_KEYS, sha256
        from harness.grasp_act_policy import UPSTREAM_SHA, GraspActor, make_policy
        from harness.grasp_act_loss import DONE_MODES
        contract_check(c)
        root = Path(root)
        hashes = json.loads((root / "SHA256.json").read_text())
        names = {"model.safetensors", "config.json", "adapter.json"}
        if set(hashes) != names or any(sha256(root / n) != hashes[n] for n in names):
            raise ValueError("checkpoint inventory/hash mismatch")
        meta = json.loads((root / "adapter.json").read_text())
        mode = meta.get("history_causal_split_v1")
        if (meta["schema"] != "ugrp.grasp_act.adapter.act16w.v3" or mode not in MODES
                or meta.get("done_mode") not in DONE_MODES or meta["blank_images"]
                or meta["upstream_sha"] != UPSTREAM_SHA
                or meta["contract_sha256"] != sha256(Path(c.__file__))
                or meta["image_hw"] != list(IMAGE_HW) or meta["model_image_hw"] != list(MODEL_IMAGE_HW)
                or meta["image_keys"] != list(IMAGE_KEYS)
                or meta["history_layout"] != "2x2_row_major_oldest_to_newest"):
            raise ValueError("ACT16 adapter mismatch")
        expected = {"history": HISTORY, "stride": STRIDE,
                    "columns": list(MASK_COLUMNS) if mode != "off" else [],
                    "replacement": "TRAIN mean in normalized coordinates", "train_inference_identical": True}
        if meta.get("input_transform") != expected:
            raise ValueError("input transform provenance mismatch")
        policy = make_policy(device=device)
        saved = json.loads((root / "config.json").read_text())
        actual = json.loads(json.dumps(draccus.encode(policy.config)))
        saved["device"] = actual["device"]
        if saved != actual:
            raise ValueError("checkpoint differs from frozen ACT config")
        policy.load_state_dict(load_file(str(root / "model.safetensors")), strict=True)
        return cls(GraspActor(policy, meta["stats"], device=device, done_mode=meta["done_mode"]), mode)
