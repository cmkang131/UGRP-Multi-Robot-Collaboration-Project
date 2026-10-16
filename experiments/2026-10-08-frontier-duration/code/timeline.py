"""Causal online snapshots; deliberately has no final-map fallback."""
import math

CHECKPOINTS=(120.,180.,240.,360.)


def select_snapshots(snapshots,*,start,end,checkpoints=CHECKPOINTS):
    if not all(math.isfinite(float(x)) for x in (start,end)) or end<start:raise ValueError('INVALID_RUN_INTERVAL')
    times=[float(x['t']) for x in snapshots]
    if times!=sorted(times):raise ValueError('NONMONOTONIC_SNAPSHOTS')
    result=[]
    for elapsed in checkpoints:
        t=start+elapsed
        if t>end+1e-8:
            result.append(dict(elapsed_s=elapsed,status='censored',snapshot=None));continue
        available=[s for s in snapshots if s['t']<=t+1e-8]
        snapshot=available[-1] if available else None
        result.append(dict(elapsed_s=elapsed,status='observed' if snapshot else 'no_map_yet',snapshot=snapshot))
    return result
