"""One finite wait then terminal-only analysis; never submits a simulation."""
import json, os, platform, subprocess, sys, time
from pathlib import Path


def main(root):
    assert platform.node().startswith('ugrp-sim-gcp2')
    batch = Path('/home/ugrp/ugrp-sim/runs/reloc18-round3')
    tools = Path('/home/ugrp/ugrp-sim/analysis-tools')
    deadline = time.monotonic()+3600
    while not (batch/'DONE').exists():
        if time.monotonic()>deadline:
            raise RuntimeError('terminal evidence wait timed out; no new physics submitted')
        time.sleep(5)
    env = dict(os.environ, PYTHONPATH=root)
    for script, args in [
        ('reloc18-summarize.py', ['--round', '3']),
        ('reloc18-selfmap-results.py', [root, '3']),
        ('reloc18-place-predicates.py', []),
        ('place_frames.py', []),
        ('terminal_evidence.py', [root]),
    ]:
        subprocess.run([sys.executable, str(tools/script), *args], env=env, cwd=root, check=True)
    (batch/'ANALYSIS_DONE.json').write_text(json.dumps(dict(status='terminal analysis complete', source_root=root))+'\n')


if __name__ == '__main__':
    main(sys.argv[1])
