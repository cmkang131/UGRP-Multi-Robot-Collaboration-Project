"""Unpack the selected, scripted compatibility fixtures for this test process."""
from pathlib import Path
import tarfile
import tempfile

# Some CLI tests only accept paths inside the experiment. A separate directory
# per test process also keeps simultaneous suite runs independent.
_scratch = tempfile.TemporaryDirectory(prefix=".regression-", dir=Path(__file__).resolve().parent)
REGRESSION = Path(_scratch.name)
for pack in sorted((Path(__file__).parent / "fixtures/regression").glob("*.tar.gz")):
    with tarfile.open(pack) as archive:
        archive.extractall(REGRESSION, filter="data")
