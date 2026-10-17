"""Read actual first30SIM command prefixes from v7 teacher output; no control."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from act16w_runtime import require_gcp2,frozen_source,sha256
from act17_open_loop import read


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();host=require_gcp2(training=True);source=frozen_source(Path(__file__).resolve().parents[1])
    rows=[]
    for controller in sorted(a.run.glob('group-*/controller')):
        for world in sorted(controller.glob('world-*')):
            if not world.is_dir():continue
            path=world/'teacher-commands.jsonl'
            if not path.exists() and not Path(str(path)+'.zst').exists():continue
            values=read(path,lines=True)
            if not values:continue
            origin=values[0]['t'];prefix=[x for x in values if x['t']-origin<=30+1e-8]
            if prefix[-1]['t']-origin<30-1e-8:continue
            if any(abs(y['t']-x['t']-.1)>1e-5 for x,y in zip(prefix,prefix[1:])):
                raise ValueError('first30 command clock gap')
            plan=read(world/'plan.json')
            actual=path if path.exists() else Path(str(path)+'.zst')
            rows.append(dict(seed=plan['seed'],kind=plan['kind'],scenario_id=plan['scenario_id'],
                rows=len(prefix),SIM_range=[0,prefix[-1]['t']-origin],phase_counts=dict(Counter(x['phase'] for x in prefix)),
                visible_target_rows=sum(bool(x['visible_target']) for x in prefix),
                wheel_command_rows=sum(any(x['command']['wheels']) for x in prefix),
                done_in_first30=any(x['phase']=='complete' for x in prefix),
                command_prefix_sha256=__import__('hashlib').sha256(json.dumps(prefix,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                raw=dict(path=str(actual),sha256=sha256(actual)),source_sha=source))
    report=dict(source_sha=source,host=host,scope='actual first30SIM command/visibility prefixes, no inferred task success',
        rows=rows,N=len(rows),physics_steps=0,rendered_frames=0,training_rgb=False,
        timing_note='do not infer exact first30 latency from later progress snapshots; observed_SIM is recorded separately',reproduce=sys.argv)
    with a.out.open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(dict(N=len(rows),phase_counts=dict(sum((Counter(r['phase_counts']) for r in rows),Counter())))))


if __name__=='__main__':main()
