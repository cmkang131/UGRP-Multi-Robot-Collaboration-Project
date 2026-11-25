"""Original local tar helper used by the simulated object store."""
import subprocess


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def make_tar(dest, base, members):
    lst = dest.with_suffix(".list")
    lst.write_text("\n".join(members) + "\n")
    r = sh(["tar", "--zstd", "-cf", str(dest), "-C", str(base), "-T", str(lst)], timeout=900)
    lst.unlink(missing_ok=True)
    if r.returncode not in (0, 1):  # 1 = a file changed while reading
        raise RuntimeError("tar failed: " + r.stderr[-300:])
    return dest.stat().st_size
