"""Build the 72-case plan for the blinded b-v6h1 confirmatory cohort (unsealed stage-probe admission).
Cases come from scripts.run_pair_stage_probes.prepare_cases (no --prereg): seed 941 x 60 placements + seed 943 x first 12.
Verified equal to experiments/2026-09-30-pair-v6h-carry build_prereg_v6h.build()['cases'] minus registration_run_id."""
import hashlib, importlib, json, subprocess, sys
from pathlib import Path
ROOT = Path('/Users/changmin/projects/ugrp-wt/v6h1-confirm'); RAW = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from scripts.run_pair_stage_probes import parser, prepare_cases, write_json
from harness import pair_stage_probe as sp
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
P941 = ROOT/'experiments/2026-09-30-pair-v6h-carry/placements_confirmatory_DRAFT.json'; P943 = RAW/'placements_seed943_first12.json'
def mk(seed, pl):
    a = parser().parse_args(['--stage','chain','--policies','b-v6h1','--sources','teacher','--seeds',str(seed),'--nominal-seeds',str(seed),
        '--env-placements',str(pl),'--render-profile','floor_light_v1','--chain-stop-leg','1','--pf-track','--contact-track','--workers','4','--omp-threads','1','--output','/x/y'])
    return json.loads(json.dumps(prepare_cases(a)[1], allow_nan=False))
cases = mk(941, P941) + mk(943, P943)
b = importlib.import_module('experiments.2026-09-30-pair-v6h-carry.build_prereg_v6h').build()
assert len(cases) == 72 and cases == [{k:v for k,v in c.items() if k!='registration_run_id'} for c in b['cases']]
assert len({c['case_id'] for c in cases}) == 72
assert json.loads(P941.read_text())[:12] == json.loads(P943.read_text())
from harness.zone_pair_v6_policy import pair_policy
import dataclasses
plan = {'schema':'v6h1-confirm-blinded.plan.v1','source_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
  'source_status_porcelain':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
  'admission':'unsealed_stage_probe (no --prereg; prereg_v6h.json not yet sealed); cases byte-equal to build_prereg_v6h.build() cases minus registration_run_id',
  'policy':'b-v6h1','policy_fields':dataclasses.asdict(pair_policy('b-v6h1')),
  'stage':'chain','chain_stop_leg':1,'sources':['teacher'],'render_profile':'floor_light_v1','pf_track':True,'contact_track':True,
  'workers':4,'omp_threads':1,'clock':'SIM','weld':False,'model_calls':0,'case_timeout_wall_s':1500.0,
  'stage_budget_s':sp.STAGES['chain'].get('budget_s'),'stage_spec':sp.STAGES['chain'],
  'primary':{'seed':941,'n':60,'placements':str(P941.relative_to(ROOT)),'placements_sha256':sha(P941)},
  'sensitivity':{'seed':943,'n':12,'placements':str(P943),'placements_sha256':sha(P943),'note':'first 12 rows of the 60-row file'},
  'rerun_rule':'PREREG_DRAFT sec.8: HOST_ERROR case rerun once, same placement/seed, original record preserved',
  'cases':cases}
write_json(RAW/'plan.json', {'labels':sp.LABELS, **plan})
print(len(cases), sha(RAW/'plan.json'))
