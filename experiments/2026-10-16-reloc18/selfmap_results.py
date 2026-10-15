"""Terminal-only selfmap comparison, keeping local and map-absolute errors apart."""
import json,platform,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
RUNS=Path('/home/ugrp/ugrp-sim/runs')
def main(source_root):
    assert platform.node().startswith('ugrp-sim-gcp2')
    sys.path.insert(0,str(Path(source_root)/'experiments/2026-10-16-reloc17'))
    from analyze import analysis
    from scripts.analyze_reloc14 import selfmap
    q=json.loads((RUNS/'reloc18-round2/queue.json').read_text());out=[]
    for t in q['runs']:
        if t['kind']!='selfmap':continue
        folder=Path(t['raw']).parent
        if not (folder/'EXIT').is_file():continue
        base=selfmap(folder);extra=analysis(folder)
        out.append(dict(run=t['name'],raw=t['raw'],source_sha=t['source_sha'],
            local_command=extra['command_only_replay'],local_candidate=extra['local_execution_drift'],
            absolute_drive=base['drive_errors'],absolute_registered=base['registered_errors'],
            static_admissions=base['drift']['fixes'],funnel=base['registration_frame_funnel'],
            input_audit=base['input_audit']))
    data=dict(status='COMPLETE' if len(out)==2 else 'INCOMPLETE',runs=out,
        scope='local drift aligned once at initial evaluator pose for scoring only; absolute map errors are separate; each command comparison uses the same executed trajectory',
        reproduce=f'PYTHONPATH=. python {__file__} {source_root}')
    (RUNS/'reloc18-round2/selfmap-results.json').write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data,indent=2))
if __name__=='__main__':main(sys.argv[1])
