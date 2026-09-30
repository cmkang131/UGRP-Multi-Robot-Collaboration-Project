"""Test-gap mutation: omit ArmSequence from the receipt in memory only."""
import sys
import pytest
from scripts import zone_pair_v6_contract as contract

original = contract.candidate_contract


def missing_arm_pin(*args, **kwargs):
    value = original(*args, **kwargs)
    value['source_sha256'].pop('scripts/zone_teacher.py', None)
    return value


contract.candidate_contract = missing_arm_pin
raise SystemExit(pytest.main(sys.argv[1:]))
