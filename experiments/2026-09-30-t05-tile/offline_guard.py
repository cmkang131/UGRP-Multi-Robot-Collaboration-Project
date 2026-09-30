"""T05 local verification only: block physics, model SDKs and network access."""
import socket
import sys

import pytest

for name in ('mujoco', 'torch', 'torchvision', 'google.genai', 'openai'):
    sys.modules[name] = None


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('T05 offline verification forbids network access')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
