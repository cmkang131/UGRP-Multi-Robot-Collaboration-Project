"""Exactly one registered full S2 DEV with real carry and visibility integration."""
import sys
from harness import zone_s2_realism_contract_v124 as contract
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_real_carry_dev import Runtime
from scripts import run_s2_realism_v123 as previous
from scripts import run_s2_realism_v117 as loop
from scripts import run_s2_realism_v118 as entry


def parser():
    p=previous.parser();p.description=__doc__
    for key in ('carry_pose','camera_calibration','measurement_model','visibility_mask'):
        p.add_argument('--'+key.replace('_','-'),choices=('off',contract.NEW_OPTIONS[key]),default='off')
    return p


def result_record(value,bundle,record):
    previous.result_record(value,bundle,record)
    value.update(camera_calibration=record.get('camera_calibration'),
        carry_pose=record.get('carry_pose'),soft_measurement=record.get('soft_measurement'),
        visibility_mask=record.get('visibility_mask'),full_dev_run_limit=1,
        user_override_old_geometry_gate=True)
    return value


def run(bundle,out,*,stage='place',runtime_factory=None,backend_factory=None):
    contract.require_execution(bundle)
    if stage!=bundle['stage_probe']:raise ValueError('stage mismatch')
    if runtime_factory is None:
        def runtime_factory(*args,**kwargs):
            return Runtime(*args,**kwargs,**{k:v for k,v in bundle['options'].items()
                if k not in ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')},
                motion_model=bundle['motion_model'],pulse_calibration=bundle['pulse_calibration'],
                extrinsic_calibration=bundle['extrinsic_calibration'])
    if backend_factory is None:
        from sim.s2_pulse_cal import backend_class
        backend_factory=backend_class()
    record={}
    def write(path,value):
        if path.name=='student_record.json':record.update(value)
        if path.name=='result.json':
            result_record(value,bundle,record)
            if record and (out/'eval_only/trajectory.jsonl').exists():
                from scripts.evaluate_s2_real_carry import metrics
                try:
                    score=metrics(out,record,bundle)
                    value['posthoc_evaluation']=score
                    loop.write(out/'eval_only/metrics.json',score)
                except Exception as exc:
                    value['posthoc_evaluation_error']=str(exc)

        loop.write(path,value)
    return bind(loop.run,contract=contract,write=write)(bundle,out,stage=stage,
        runtime_factory=runtime_factory,backend_factory=backend_factory)


def main(argv=None):return bind(entry.main,contract=contract,parser=parser,run=run)(argv)

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(2)
