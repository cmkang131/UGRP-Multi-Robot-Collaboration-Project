import subprocess
import sys
import time
import pytest
from harness.native_build_cache import build_target


def test_failed_build_never_publishes_partial_target_and_can_retry(tmp_path):
    target=tmp_path/'core.so'
    with pytest.raises(RuntimeError):
        with build_target(target) as output:
            output.write_bytes(b'partial')
            raise RuntimeError('compiler failed')
    assert not target.exists() and not list(tmp_path.glob('core-*.so'))
    with build_target(target) as output:output.write_bytes(b'complete')
    with build_target(target) as output:assert output is None
    assert target.read_bytes()==b'complete'


def test_concurrent_loader_waits_until_library_is_fully_published(tmp_path):
    target=tmp_path/'core.so';marker=tmp_path/'writing'
    producer="""from pathlib import Path
import sys,time
from harness.native_build_cache import build_target
target,marker=map(Path,sys.argv[1:])
with build_target(target) as output:
 output.write_bytes(b'partial');marker.touch();time.sleep(.4)
 output.write_bytes(b'complete')
"""
    reader="""from pathlib import Path
import sys
from harness.native_build_cache import build_target
target=Path(sys.argv[1])
with build_target(target) as output:assert output is None
assert target.read_bytes()==b'complete'
"""
    child=subprocess.Popen([sys.executable,'-c',producer,str(target),str(marker)])
    try:
        end=time.monotonic()+10
        while not marker.exists() and time.monotonic()<end:time.sleep(.01)
        assert marker.exists() and not target.exists()
        subprocess.run([sys.executable,'-c',reader,str(target)],check=True,timeout=10)
        assert child.wait(timeout=10)==0
    finally:
        if child.poll() is None:child.kill();child.wait()
