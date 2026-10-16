"""Publish complete native libraries under a per-target POSIX build lock."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import tempfile


@contextmanager
def build_target(target):
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.with_suffix(target.suffix+'.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if target.exists():
            yield None
            return
        fd,name=tempfile.mkstemp(prefix=target.stem+'-',suffix=target.suffix,dir=target.parent)
        os.close(fd);temporary=Path(name)
        try:
            yield temporary
            os.replace(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)
