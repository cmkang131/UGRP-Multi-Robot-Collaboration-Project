"""Finite gcp2 evidence pass after all three bounded physics rounds terminate."""
import hashlib, importlib.util, json, platform, subprocess, sys, tempfile
from pathlib import Path

RUNS = Path('/home/ugrp/ugrp-sim/runs')


def obj(p):
    return json.loads(p.read_bytes() if p.exists() else subprocess.check_output(['zstd', '-dc', str(p)+'.zst']))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main(root):
    assert platform.node().startswith('ugrp-sim-gcp2')
    root = Path(root)
    assert all((RUNS/f'reloc18-round{n}'/'DONE').exists() for n in (1, 2, 3))
    baseline = module('baseline', root/'experiments/2026-10-16-reloc17/baseline_analyzer.py')
    records = []
    for n in (1, 2, 3):
        for task in obj(RUNS/f'reloc18-round{n}/queue.json')['runs']:
            raw = Path(task['raw'])
            assert (raw.parent/'EXIT').exists()
            result = obj(raw/'result.json')
            records.append(dict(round=n, run=task['name'], source_sha=task['source_sha'], raw=str(raw),
                                result_status=result.get('status'),
                                invalid=(raw.parent/'INVALID_CONTROL.json').exists(),
                                result_sha256=hashlib.sha256((raw/'result.json').read_bytes() if (raw/'result.json').exists() else (raw/'result.json.zst').read_bytes()).hexdigest(),
                                integrity=baseline.verify(raw)))
    (RUNS/'reloc18-integrity.json').write_text(json.dumps(dict(runs=records, all_manifest_hashes_verified=all(r['integrity']['verified'] for r in records)), indent=2)+'\n')
    print(json.dumps(records))


if __name__ == '__main__':
    main(sys.argv[1])
