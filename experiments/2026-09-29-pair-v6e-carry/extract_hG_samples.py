#!/usr/bin/env python3
"""hG: grasp_lift entries = recorded ALIGN end states of the b-v6d align probes (offline; pre-registered rule below).

Why: the recorded grasp_lift probes all start from the coarse-sheet plan-station prior (5 cm y error), which the real job never
has (one localizer object from approach through carry, localizer_object_replaced = 0). Chain it from the recorded align end
instead: GT poses at align stop + the recorded PF posterior at that stop as the start prior.
Rule (fixed before any hG grasp_lift case ran): raw 052e3eba-v6d-venv-align-combined, policy b-v6d, category PASS, checkpoint present:
  the 6 E2E-checkpoint cases (v6-s911/s912-v5h x seeds 911..913; real E2E align-entry priors) + 4 teacher cases picked by
  index round(i*(n-1)/3), i = 0..3, over the sorted teacher case ids -> 10 samples.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stage_end_samples as S

rows = [json.loads(l) for l in open(S.OUT/'pair-stage-probes-052e3eba-v6d-venv-align-combined/cases.jsonl')]
ok = []
for r in rows:
    d = S.case_dir(r)
    if r['stage'] == 'align' and r['pair_policy'] == 'b-v6d' and r.get('category') == 'PASS' and d and (d/'checkpoints/stage_stop.npz').exists():
        ok.append((r, d))
e2e = sorted([t for t in ok if ':e2e:' in t[0]['case_id']], key=lambda t: t[0]['case_id'])
tea = sorted([t for t in ok if ':teacher:' in t[0]['case_id']], key=lambda t: t[0]['case_id'])
print(len(e2e), 'e2e', len(tea), 'teacher')
pick = [(t, 'e2e') for t in e2e] + [(tea[round(i*(len(tea) - 1)/3)], 'teacher') for i in range(4)]
samples = [S.sample('hG%02d' % (i + 1), r, d, 'align end (%s start)' % kind) for i, ((r, d), kind) in enumerate(pick)]
json.dump({'rule': __doc__.strip(), 'samples': samples}, open(Path(__file__).with_name('hG_samples.json'), 'w'), indent=1)
S.show(samples)
