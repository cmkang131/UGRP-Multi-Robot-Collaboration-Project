"""CoELA runtime with the option ``self_wall_memory`` (stage D wiring). Default OFF. Refs #216.

``harness/coela_runtime.py`` and ``harness/coela_modules.py`` are hash-pinned (``tests/fixtures/rgb_communication_audit/
source_manifest.json``) and are NOT edited. ``run_coela_episode`` here has the pinned function's signature plus two keywords:

  ``self_wall_memory``   ``"off"`` (default) or ``"on_v1"``.
  ``self_walls_source``  optional ``callable(robot_id) -> iterable of ego-wall-map records`` (``on_v1`` only).

``off`` calls the pinned ``harness.coela_runtime.run_coela_episode`` itself with the caller's arguments and returns its result: the
same function, so its output is what it was before this module existed (tested). ``on_v1`` runs the SAME code object of that
function in a copy of its module namespace in which ``Memory`` is a factory of ``SelfWallMemory`` (``self_walls_enabled`` and
``self_walls_text`` on, height out of the wording). Nothing global is patched, so concurrent episodes of the other kind are
unaffected. Because it relies on the pinned source, ``on_v1`` refuses to run when ``coela_runtime.py`` / ``coela_modules.py``
no longer have the hashes in ``PINNED_SOURCES_SHA256``: re-check this module and the bundle in ``source_manifest.json`` first.

The runtime's observation carries no camera data, so the walls reach the memory through ``self_walls_source`` (the stage C map,
``experiments/2026-10-05-ego-wall-map-probe/code/ego_wall_map.py``, filled by whoever has the frames). Without a source ``on_v1``
puts an empty ``self_walls`` and "no wall observed yet" into the planner context. ``source_from_maps`` adapts a
``{robot_id: map}`` dict of objects with a ``records`` list.

The other memory path, ``harness/rgb_communication_runtime._ActorState.memory_snapshot``, does not use ``Memory`` and is not
touched.
"""
from __future__ import annotations

import copy
import hashlib
import types
from pathlib import Path
from typing import Callable, Iterable, Mapping

from harness import coela_runtime as _runtime
from harness.self_wall_memory import SelfWallMemory

SELF_WALL_MEMORY_VALUES = ("off", "on_v1")
SELF_WALL_MEMORY_DEFAULT = "off"
ON_V1 = {"self_walls_enabled": True, "self_walls_text": True, "self_walls_text_height": False}
# The files ``on_v1`` was written against (the ``files_sha256`` of the original bundle in source_manifest.json).
PINNED_SOURCES_SHA256 = {
    "harness/coela_runtime.py": "a6fc5afa7d873281c4f008958f946bd9696d30b376a79a611e84b1a7fd8c75e3",
    "harness/coela_modules.py": "af8275de470d75ed4037f1be236f6572cde49abc0c597f1c2760795f7ba2706e",
}
_ROOT = Path(__file__).resolve().parents[1]


def source_from_maps(maps: Mapping[str, object]) -> Callable[[str], list]:
    """``self_walls_source`` over ``{robot_id: object with a .records list}`` (a stage C ``EgoWallMap``); a copy per call."""
    return lambda robot_id: list(getattr(maps.get(robot_id), "records", ()))


def memory_factory(self_wall_memory: str = SELF_WALL_MEMORY_DEFAULT, self_walls_source=None):
    """``None`` for ``off`` (the pinned runtime keeps its own ``Memory``), else ``callable(robot_id) -> SelfWallMemory``."""
    if self_wall_memory not in SELF_WALL_MEMORY_VALUES:
        raise ValueError(f"UNKNOWN_SELF_WALL_MEMORY: {self_wall_memory!r}")
    if self_wall_memory == "off":
        if self_walls_source is not None:
            raise ValueError("SELF_WALLS_SOURCE_NEEDS_SELF_WALL_MEMORY_ON_V1")
        return None
    return lambda robot_id, **kwargs: SelfWallMemory(robot_id, **ON_V1, self_walls_source=self_walls_source, **kwargs)


def check_pinned_sources() -> None:
    """Raise unless the pinned runtime files are the ones ``on_v1`` was written against."""
    for name, expected in PINNED_SOURCES_SHA256.items():
        if hashlib.sha256((_ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"PINNED_SOURCE_CHANGED: {name}")


def run_coela_episode(environment, planners, *, self_wall_memory: str = SELF_WALL_MEMORY_DEFAULT,
                      self_walls_source: Callable[[str], Iterable[dict]] | None = None, **kwargs):
    """``harness.coela_runtime.run_coela_episode`` (same keywords) with ``self_wall_memory`` = ``off`` | ``on_v1``."""
    factory = memory_factory(self_wall_memory, self_walls_source)
    if factory is None:
        return _runtime.run_coela_episode(environment, planners, **kwargs)
    check_pinned_sources()
    base = _runtime.run_coela_episode
    namespace = dict(vars(_runtime))
    namespace["Memory"] = factory
    run = types.FunctionType(base.__code__, namespace, base.__name__, base.__defaults__, base.__closure__)
    run.__kwdefaults__ = copy.copy(base.__kwdefaults__)
    return run(environment, planners, **kwargs)
