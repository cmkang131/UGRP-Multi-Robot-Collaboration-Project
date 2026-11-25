"""Run the executor's own tests with its normal entry point, isolated from sibling projects."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parents[2]


def main():
    scratch = BASE/"handover/verification/scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        root = Path(tmp)
        executor = root/"phase3/exec"
        shutil.copytree(BASE/"exec", executor)
        # Historical scorer, map and git fixtures live outside exec. The normal tests skip missing fixtures.
        env = dict(os.environ, TMPDIR=tmp, GIT_CEILING_DIRECTORIES=tmp, OPENBLAS_NUM_THREADS="1",
                   PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(BASE))
        script = ("import sys, unittest; from handover.run_trial import offline; sys.addaudithook(offline); "
                  "sys.path[:0]=['.', 'tests']; unittest.main(module=None, argv=['unittest','discover','-s','tests','-v'])")
        return subprocess.run([sys.executable, "-B", "-c", script], cwd=executor, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
