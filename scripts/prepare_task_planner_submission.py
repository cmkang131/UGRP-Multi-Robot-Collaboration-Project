"""Write the paired supervisor submission; never start a VM, relay or simulation."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.run_e2e_ownmap_live import bundle
from harness.e2e_runtime_registration import require_current
from harness.s4_event_policy import Options
from harness.zone_study_contract import digest

def prepare(sha):
    options=json.loads((ROOT/'configs/e2e_task_planner_options.json').read_text())
    result=dict(schema='ugrp.task_planner.supervisor_request.v1',source_sha=sha,pr=473,
        host='azure3',only_vm='VM3',other_vms='deallocated; supervisor verifies',concurrent=16,gate_limit=3.5,
        speed_gate_sim_s=30,seeds=list(range(61006,61014)),condition='peer_en',submitted=False,
        budget=dict(cells=16,case_cap_sim_s=1800,wall_cap_per_cell_s=25200,token_cap_per_cell=800000,
                    total_token_cap=12800000,model_requests_per_cell=300,max_output_tokens=768,
                    storage_estimate_gib_per_cell=2,total_storage_reservation_gib=32,
                    storage_basis='conservative request estimate, supervisor must reconcile actual pending writes and floor before admission'),
        provider_prerequisite='Existing Mac study_gemma4_31b_v1 OpenRouter relay restored from HTTP 402; task-planner-v1 enabled on same SHA, dialogue-decider code_v1, decider off. No credentials transferred.',
        first30=['actual model/HTTP requests including repairs','charged and known tokens per SIM second','token and call cap expected SIM time','act and executed-act distributions','fallback counts'],
        stop_rules='Existing physical-failure stops, VM lease <=8 hours and idle expiry; gate wall/SIM <=3.5. No automatic override.',cells=[])
    flags=['--event-driven-llm','--compact-prompt','--decider','off','--stall-recovery','off','--stall-noise','off','--body-skills','off']
    for key,value in options.items():
        flag={'enabled':'e2e-live','relook':'setdown-only-when-relook'}.get(key,key.replace('_','-'))
        if isinstance(value,bool):
            if value:flags+=['--'+flag]
        else:flags+=['--'+flag,json.dumps(value,separators=(',',':')) if isinstance(value,dict) else str(value)]
    for seed in result['seeds']:
        for mode in ('gemma_v1','rule_v1'):
            b=bundle(sha,seed,'study_gemma4_31b_v1',**options,options=Options(True,True,'en'),planner=mode)
            require_current(b,ROOT)
            rid=f"{b['execution_bundle_id']}-s{seed}-r4732"
            result['cells'].append(dict(run_id=rid,seed=seed,planner=mode,bundle_id=b['execution_bundle_id'],bundle_sha256=digest(b),
                argv=['scripts/run_e2e_ownmap_live.py','--expected-source-sha',sha,'--seed',str(seed),'--driver-profile','study_gemma4_31b_v1',
                    '--output',f'<persistent-runs>/{rid}/raw','--relay-receipt','<same-sha-task-relay-identity.json>',*flags,'--planner',mode,
                    '--expected-workflow-id',b['execution_bundle_id'],'--execute']))
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-sha',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise SystemExit('new manifest required')
    a.out.write_text(json.dumps(prepare(a.source_sha),indent=2)+'\n')
