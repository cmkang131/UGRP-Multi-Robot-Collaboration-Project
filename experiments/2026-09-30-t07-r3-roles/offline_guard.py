"""Local T07 verification: fail before any simulator, render or network call."""
import socket
import sys

import pytest

for name in ('mujoco', 'torch', 'torchvision'):
    sys.modules[name] = None


@pytest.fixture(autouse=True)
def prohibit_side_effects(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('T07 local verification forbids network/render/inference')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    from harness import zone_map_schematic
    monkeypatch.setattr(zone_map_schematic, 'render_schematic', forbidden)
    from harness.vision_loc_client import VisionWorkerClient
    monkeypatch.setattr(VisionWorkerClient, '__init__', forbidden)
