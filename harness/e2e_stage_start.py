"""Host-only bounded restore admission and common physics start; no robot data."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import time


class StageStart:
    def __init__(self, root, member, sha, *, timeout=600.):
        self.root=Path(root);self.member=member;self.deadline=time.monotonic()+timeout
        manifest=json.loads((self.root/'manifest.json').read_text())
        self.members=manifest['members'];self.slots=manifest['restore_slots']
        if manifest['source_sha']!=sha or member not in self.members or len(set(self.members))!=len(self.members):
            raise ValueError('START_GROUP_IDENTITY_MISMATCH')
        if not 1<=len(self.members)<=16 or not 1<=self.slots<=8:raise ValueError('START_GROUP_SIZE')
        self.sha=sha

    def pause(self):
        if time.monotonic()>=self.deadline:raise TimeoutError('STAGE_START_TIMEOUT')
        time.sleep(.1)

    @contextmanager
    def restore_slot(self):
        held=None
        try:
            while held is None:
                for n in range(self.slots):
                    f=(self.root/f'slot-{n}.lock').open('a')
                    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:f.close();continue
                    held=f;break
                if held is None:self.pause()
            yield
        finally:
            if held is not None:held.close()

    def ready(self):
        # Each ready marker belongs to exactly one predeclared process/run.
        marker=self.root/(self.member+'.ready.json')
        with marker.open('x') as f:json.dump(dict(source_sha=self.sha,ready_monotonic=time.monotonic()),f)
        while True:
            with (self.root/'release.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                release=self.root/'release.json'
                if not release.exists() and all((self.root/(m+'.ready.json')).exists() for m in self.members):
                    for m in self.members:
                        if json.loads((self.root/(m+'.ready.json')).read_text())['source_sha']!=self.sha:
                            raise ValueError('START_READY_SHA_MISMATCH')
                    release.write_text(json.dumps(dict(start_monotonic=time.monotonic()+2,source_sha=self.sha)))
                if release.exists():
                    record=json.loads(release.read_text());break
            self.pause()
        while time.monotonic()<record['start_monotonic']:self.pause()
        return dict(**record,actual_start_monotonic=time.monotonic(),member=self.member,members=len(self.members),restore_slots=self.slots)
