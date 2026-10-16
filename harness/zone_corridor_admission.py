"""Static runtime admission shared by managed launches and the opt-in factory.

Keep this gate independent of executor/host imports, including lazy imports:
the standard launcher's conservative source seal follows every static import.
"""


class UnsupportedCorridor(ValueError):
    """Explicit refusal, including legacy door-only executor construction."""


def require_door_runtime(static_map):
    """Refuse unsupported geometry; passing this check grants no run approval."""
    if not any(p.get('kind') == 'door' for p in static_map.get('passages', ())):
        raise UnsupportedCorridor('CORRIDOR_RUNTIME_UNSUPPORTED: T10b required')
