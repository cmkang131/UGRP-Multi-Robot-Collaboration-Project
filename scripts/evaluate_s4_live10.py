"""Server-only offline judgment: complete route, cycles, supported distance and drops."""
import argparse,json
from pathlib import Path
from scripts.evaluate_s4_live9 import evaluate as previous
from scripts.evaluate_s4_live5 import read,rows


def evaluate(raw):
    v=previous(raw);h=read(raw/'pair-handshake.json');cyan=rows(raw/'eval_only/r3/com-contact-supervisor.jsonl') if (raw/'eval_only/r3/com-contact-supervisor.jsonl').exists() else []
    suppressed=rows(raw/'eval_only/r3/height-stop-classification.jsonl') if (raw/'eval_only/r3/height-stop-classification.jsonl').exists() else []
    v.update(cycles={'GO_ACK_epochs':len(h['permits']),'completed_supported_carry_legs':len(v['goal_route']['held_segments']),
        'supported_restarts':sum(s>0 for s in v['goal_route']['held_segments'])},
        total_supported_carry_path_m=v['distance']['contact_supported_path_m'],
        goal_arrival={'n':v['goal_route']['n'],'N':1},
        cyan_drop={'n':int(any(r['drop'] for r in cyan)),'N':1},
        cyan_height_stops_suppressed=len(suppressed),
        cyan_suppression_bilateral={'n':sum(r['bilateral_finger_contact'] for r in suppressed),'N':len(suppressed)},
        same_epoch_snapshot_reconnections=h.get('snapshot_reconnections',[]),
        epoch_transitions=read(raw/'epoch-reconnections.json'),
        GO_ACK_rounds=h.get('rounds',{}))
    return v


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--raw-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    if a.output.exists():raise FileExistsError(a.output)
    values=[evaluate(a.raw_root/r['name']/'raw') for r in read(a.plan)['runs']]
    a.output.write_text(json.dumps(values,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'goal_arrival':{'n':sum(v['goal_arrival']['n'] for v in values),'N':len(values)},
        'cyan_drop':{'n':sum(v['cyan_drop']['n'] for v in values),'N':len(values)},
        'paths_m':[v['total_supported_carry_path_m'] for v in values]}))


if __name__=='__main__':raise SystemExit(main())
