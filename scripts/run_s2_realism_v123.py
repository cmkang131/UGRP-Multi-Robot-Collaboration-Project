"""One full S2 DEV run: unconfirmed visual grasp is recorded, not a stop gate."""
import sys
from harness import zone_s2_realism_contract_v123 as contract
from harness.zone_final_pair_binding import bind
from harness.zone_solo_cyan_visual_fix import Runtime
from scripts import run_s2_realism_v120 as previous
from scripts import run_s2_realism_v117 as loop
from scripts import run_s2_realism_v118 as entry


def parser():
    p=previous.parser();p.description=__doc__
    p.add_argument('--dev-grasp-policy',choices=('off','log_only_v1'),default='off')
    p.add_argument('--eval-camera-trace',choices=('off','pose_v1'),default='off')
    p.add_argument('--pulse-motion-model',choices=('off','v7_pulse_cal_v1'),default='off')
    p.add_argument('--visual-update',choices=('off','accepted_scan_v1'),default='off')
    p.add_argument('--visual-stall',choices=('off','lk_pulse_v1'),default='off')
    return p


def result_record(value,bundle,record):
    hold=value.get('pickup_site_status','unknown')
    value.update(result_condition=bundle['result_condition'],pool_with_previous_s2=False,
        comparison_metrics=['wall_per_sim'],hold_status=hold,pickup_site_status='not_evaluated_inhand_selected',
        grasp_verification_policy=bundle['options']['dev_grasp_policy'],
        visual_unknown_stops=False,effective_motion_model=bundle['effective_motion_model'],physical_success=value.get('evaluation',{}).get('success',False),
        dev_light_would_stop=record.get('dev_light_would_stop',{}),
        would_stop_events=[e for e in record.get('events',[]) if e['event']=='dev_light_would_stop'])
    value['visual_update']=record.get('visual_update')
    flow=record.get('visual_stall',{}).get('rows',[])
    from collections import Counter
    value['visual_stall_summary']=dict(status_counts=dict(Counter(x['status'] for x in flow)),would_stop=sum(x['would_stop'] for x in flow),control_feedback=False)
    return value


def run(bundle,out,*,stage='place',runtime_factory=None,backend_factory=None):
    contract.require_execution(bundle)
    if stage!=bundle['stage_probe']:raise ValueError('stage mismatch')
    if runtime_factory is None:
        def runtime_factory(*args,**kwargs):
            return Runtime(*args,**kwargs,**{k:v for k,v in bundle['options'].items()
                if k not in ('drive_profile','stagnation_watch','idle_robot_contacts','dev_grasp_policy','eval_camera_trace')},
                motion_model=bundle['motion_model'],pulse_calibration=bundle['pulse_calibration'])
    if backend_factory is None:
        from sim.s2_pulse_cal import backend_class
        backend_factory=backend_class()
    record={}
    def write(path,value):
        if path.name=='student_record.json':record.update(value)
        if path.name=='result.json':result_record(value,bundle,record)
        loop.write(path,value)
    return bind(loop.run,contract=contract,write=write)(bundle,out,stage=stage,
        runtime_factory=runtime_factory,backend_factory=backend_factory)


def main(argv=None):return bind(entry.main,contract=contract,parser=parser,run=run)(argv)

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(2)
