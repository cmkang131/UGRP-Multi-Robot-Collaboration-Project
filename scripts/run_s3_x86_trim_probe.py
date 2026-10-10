"""All candidate conditions use the same frozen, held-out-qualified model."""
import argparse,copy,hashlib,json,functools
from pathlib import Path
from types import SimpleNamespace
from scripts import run_s3_x86_probe as stage
from harness.zone_final_pair_binding import bind
from harness.zone_s3_measured_visual_servo import attach_endpoint,attach_solo,OPTION
from sim.s3_visual_trim import PhysicsBackend,OPTION as PORT_OPTION

BUNDLE_ID='zone-s3-x86-trim-probe-v158'


def bundle(sha,condition,model_path,model_sha,case='pair'):
    raw=model_path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=model_sha:raise ValueError('fixed calibration hash mismatch')
    model=json.loads(raw)
    if not model['qualified'] or model['host']!='oracle-x86' or model['runtime_gt']:raise ValueError('qualified Oracle model required')
    b=stage.bundle(sha,case,condition=condition)
    b.update(execution_bundle_id=BUNDLE_ID,workflow_version='7.51.0',servo_option=OPTION,
        visual_trim=PORT_OPTION,measured_trim_model=model,measured_trim_sha256=model_sha,concurrent_probe_limit=10)
    from harness.python_source_closure import source_closure
    for p in source_closure(stage.ROOT,['scripts/run_s3_x86_trim_probe.py']):
        b['source_sha256'][p]=hashlib.sha256((stage.ROOT/p).read_bytes()).hexdigest()
    b['source_sha256']['configs/simulation_workflows.d/s3_x86_trim_probe_v158.json']=hashlib.sha256((stage.ROOT/'configs/simulation_workflows.d/s3_x86_trim_probe_v158.json').read_bytes()).hexdigest()
    return b


def run(b,out):
    def enter(rt,now,option):
        eps=stage.previous.enter_pair(rt,now,'off')
        for ep in eps.values():attach_endpoint(ep,b['measured_trim_model'],option=OPTION)
        return eps
    def configure(own,option):return attach_solo(own,b['measured_trim_model'],option=option)
    previous=SimpleNamespace(**{**vars(stage.previous),'enter_pair':enter,
        'run':functools.partial(stage.previous.run,solo_configure=configure)})
    result=bind(stage.run,previous=previous,StageBackend=PhysicsBackend)(b,out)
    environment=json.loads((out/'environment.json').read_text());environment['concurrent_probe_limit']=10
    stage.previous.write(out/'environment.json',environment);stage.previous.artifact_manifest(out)
    return result


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--expected-source-sha',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--condition',type=int,choices=range(6),default=0)
    p.add_argument('--case',choices=('pair','cyan'),default='pair')
    p.add_argument('--model',type=Path,required=True);p.add_argument('--model-sha256',required=True)
    p.add_argument('--execute',action='store_true');a=p.parse_args(argv)
    if not a.execute:print(json.dumps(dict(execution_started=False,host='oracle-x86',bundle_id=BUNDLE_ID)));return 0
    stage.archive_guard(a.expected_source_sha,a.output)
    from harness.zone_pair_highpose_exact_speedups import install
    _,undo=install('v98-exact-v6')
    try:r=run(bundle(a.expected_source_sha,a.condition,a.model,a.model_sha256,a.case),a.output)
    finally:undo()
    print(json.dumps(r));return int(r['status']=='HOST_ERROR')


if __name__=='__main__':raise SystemExit(main())
