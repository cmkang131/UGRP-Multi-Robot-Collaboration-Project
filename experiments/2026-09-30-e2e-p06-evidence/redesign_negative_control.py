"""Negative control: old production readers in isolated module namespaces only."""
from pathlib import Path
import types


def old_module(name, filename, realpath):
    module = types.ModuleType(name)
    module.__file__ = str(Path.cwd() / realpath)
    data = (Path('/private/tmp/p06-evidence-redesign') / filename).read_text()
    exec(compile(data, module.__file__, 'exec'), module.__dict__)
    return module


def pytest_collection_modifyitems(items):
    contract = old_module('p06_old_contract', 'old_contract.py', 'scripts/zone_study_evidence_contract.py')
    study = old_module('p06_old_study', 'old_study.py', 'scripts/tensorboard_tools/zone_study.py')
    study.verify_identity_join = contract.verify_identity_join
    exporter = old_module('p06_old_export', 'old_export.py', 'scripts/tensorboard_tools/export.py')
    exporter.export_study = study.export_study
    for item in items:
        if item.module.__name__.endswith('test_zone_study_evidence_review_f303'):
            item.module.tb = exporter
