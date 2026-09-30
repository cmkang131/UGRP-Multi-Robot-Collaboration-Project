"""Collect Batch J mutation checks through the existing offline CI glob."""
from tests.test_review_e2e_batch_j import (  # noqa: F401
    crate_tree,
    test_original_guard_blocks_the_counterexample,
    test_removed_guard_changes_the_safety_decision,
    test_pr_suite_must_detect_removed_safety_logic,
)
