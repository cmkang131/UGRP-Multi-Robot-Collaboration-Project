"""Gemma/English study adapter. Preparation only until Azure + own-map admission.

No simulator is imported by the CLI. Prior v183 stays a Korean reproduction
entrypoint; new runs use this English-default profile and distinct cohort keys.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
from harness.s4_event_policy import Options, Host, Driver, Link
from harness.s4_compact_prompt import legacy_condition, external_condition
from harness.zone_study_llm_driver import load_registry
from harness.zone_study_contract import digest
from harness.zone_final_pair_binding import bind

BUNDLE_ID='zone-s4-study-v184'
VERSION='7.77.0'
RECORD='experiments/2026-10-11-s4-gemma-standard'
WORKFLOW='configs/simulation_workflows.d/s4_study_v184.json'
DEFAULT_PROFILE='study_gemma4_31b_v1'


def bundle(sha,condition,seed=601,*,profile=DEFAULT_PROFILE,options=Options()):
    if profile not in (DEFAULT_PROFILE,'main_study_gemini_v1'):raise ValueError('single model required')
    if seed not in (601,602,603):raise ValueError('registered DEV seed required')
    b=dict(schema='ugrp.s4_study_preparation.v1',source_sha=sha,seed=seed,source_sha256={},
           parent_bundle='zone-s4-pair-live-v183',research_result=False,
           physical_configuration='inherit only after Azure and own-map adapter integration')
    registered=load_registry()['driver_profiles'][profile]
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version=VERSION,workflow_catalog=WORKFLOW,
        driver_profile=profile,driver_profile_sha256=digest(registered),study_options=asdict(options),
        condition=external_condition(condition,options.prompt_lang),
        legacy_channel_codec=legacy_condition(condition),model=registered['model'],
        cohort_key=f'{profile}:{options.prompt_lang}:event{int(options.event_driven_llm)}:compact{int(options.compact_prompt_v1)}'
            +f':coalesce{int(options.event_coalesce_v1)}:mapimage{int(options.map_as_image_v1)}:trim{int(options.context_trim_v1)}',
        execution_admitted=False,admission_blockers=['Azure readiness notification','own-map E2E integration'],
        pool_historical_results=False,research_result=False)
    from harness.python_source_closure import source_closure
    import hashlib
    root=Path(__file__).resolve().parents[1]
    paths=set(source_closure(root,['scripts/run_s4_study_v184.py','scripts/s4_proxy_relay.py']))|{
        WORKFLOW,'configs/zone_study_integration/llm_driver.json'}
    b['source_sha256'].update({p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths})
    return b


def extension_type():
    """Inject only S4 policy into existing S3 adapter. Does not start a runtime."""
    from scripts import run_s4_pair_live11 as prior
    class Extension(prior.Extension):
        def components(self):
            link,_,extra=super().components()
            extra['handshake'].study_options=Options(**self.b['study_options'])
            return Link,Host,extra
        def driver(self,host,runtime):
            # Reuse exactly the old on_admit S3 toggles, replace its S4 driver.
            old=super().driver(host,runtime)
            self.pair_driver=Driver(host,runtime,go_ack_retry=old.go_ack_retry,on_admit=old.on_admit)
            return self.pair_driver
    return Extension


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--condition',choices=('no_comm','peer_en','leader_en','structured','peer_ko','leader_ko'),required=True)
    p.add_argument('--seed',type=int,choices=(601,602,603),default=601)
    p.add_argument('--prompt-lang',choices=('en','ko'),default='en')
    p.add_argument('--driver-profile',choices=(DEFAULT_PROFILE,'main_study_gemini_v1'),default=DEFAULT_PROFILE)
    p.add_argument('--event-driven-llm',action='store_true');p.add_argument('--compact-prompt-v1',action='store_true')
    p.add_argument('--event-coalesce-v1',action='store_true');p.add_argument('--map-as-image-v1',action='store_true')
    p.add_argument('--context-trim-v1',action='store_true')
    p.add_argument('--expected-source-sha',required=True);p.add_argument('--execute',action='store_true')
    p.add_argument('--output',type=Path)
    a=p.parse_args(argv)
    if a.execute:raise ValueError('AZURE_AND_OWN_MAP_ADMISSION_REQUIRED: preparation only')
    result=bundle(a.expected_source_sha,a.condition,a.seed,profile=a.driver_profile,
        options=Options(a.event_driven_llm,a.compact_prompt_v1,a.prompt_lang,
                        a.event_coalesce_v1,a.map_as_image_v1,a.context_trim_v1))
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
