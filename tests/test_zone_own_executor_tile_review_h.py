"""Collect the #334 review regressions through the existing offline CI glob."""
from tests.test_review_e2e_batch_h import (  # noqa: F401
    tile,
    test_tile_consumes_native_navigation_command_history,
    test_tile_same_capture_cannot_supply_two_holding_confirmations,
)
