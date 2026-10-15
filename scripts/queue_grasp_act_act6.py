"""Source-bound, entirely disabled ACT6 operations handoff. No remote actions."""
import argparse
import json
from pathlib import Path
from harness.grasp_act_data import sha256, write_json
from scripts.grasp_act_training_guard import ROOT, source_sha
from scripts.prepare_grasp_act_act6 import GATE_SEEDS, RECORD_SEEDS, STUDENT_SEED
from scripts.run_grasp_act_recovery import TEACHER_SHA

RECORD='experiments/2026-10-15-act-train'


def build_queue(source):
    short=source[:8];base=f'/mnt/act-source/act6-{short}';runs='/home/ugrp/ugrp-sim/runs'
    py='/home/ugrp/ugrp-act-env/bin/python';simpy='.venv-sim/bin/python'
    data=base+'/dataset';noise=f'{RECORD}/act6-noise.json'
    dependency='/home/ugrp/ugrp-deps/solo-teacher-6f057f7e'
    states={'approved':False,'enabled':False,'ready':False,'stage_ready':False,'submitted':False}
    def job(name,command=None,depends=(),**extra):
        return {'stage':name,**states,'command':command,'depends_on':list(depends),**extra}
    def teacher_run(seed,index,stage):
        name=f'act6-{stage}-{seed}-{short}'
        command=[simpy,'-m','scripts.sim_cli','workflow','run','grasp-act-recovery','--',
            '--plan',f'{RECORD}/act6-{stage}-plan.json','--episode',str(index),
            '--dependency-root',dependency,'--noise',noise,'--recovery-mode','dart_wheels_v1',
            '--out',f'{runs}/{name}/raw','--cap-s','90']
        if stage=='record':command+=['--training-rgb','--gate-receipt',f'{runs}/act6-{short}/gate-review.json']
        return {'name':name,'seed':seed,**states,'command':command,'source_sha':source,
            'teacher_dependency_sha':TEACHER_SHA,'training_rgb':stage=='record',
            'SOURCE_SHA_file':source,'EXIT_file_required':True}
    teacher=job('noise-teacher-gate40',depends=['preflight-receipt','full-teacher-stall-census-review'],
        host='gcp1',runs=[teacher_run(s,i,'gate') for i,s in enumerate(GATE_SEEDS)],
        N=40,minimum_success=38,training_rgb=False,max_parallel=1,
        automatic_promotion=False,stop_on_confirmed_defect=True)
    recording=job('recovery-record50',depends=['noise-teacher-gate40','gate-review-receipt'],
        host='gcp1',runs=[teacher_run(s,i,'record') for i,s in enumerate(RECORD_SEEDS)],
        max_parallel=1,training_rgb=True,first_2_then_review=True,
        first30_checks=['native 640x480/10Hz/K,D,FOV','actual noisy command history; clean aligned label',
            'held_world_reads=0, invisible_measurements=0','>=6 own frames; edge/loss/recovery vs terminal tail',
            'actual post-projection covariance and saturation rate; no success claim from noise magnitude'])
    protocol={'teacher_sha':source,'run_pattern':f'act6-record-{{seed}}-{short}',
        'train_seeds':RECORD_SEEDS[:45],'validation_seeds':RECORD_SEEDS[45:],
        'closed_loop_seeds':[STUDENT_SEED],'done_label':'last_local_row_v1',
        'recovery_mode':'dart_wheels_v1','noise_sha256':sha256(ROOT/noise),
        'admission':'new noisy teacher gate >=38/40 plus recording review required; not inherited from old teacher'}
    jobs=[teacher,recording,
        job('convert-recovery',[py,'-m','scripts.prepare_grasp_act_data','--runs-root',base+'/recovered-runs',
            '--protocol',base+'/protocol.json','--output',base+'/recovery-dataset'],
            ['recovery-record50','recording-admission-and-transfer-receipt']),
        job('compose-data',[py,'-m','scripts.merge_grasp_act_recovery_data','--original',
            '/mnt/act-source/act-main-f609979c/dataset','--recovery',base+'/recovery-dataset',
            '--output',data],['convert-recovery'])]
    approvals={}
    for arm,p in [('p0',0.),('p02',.2)]:
        root=base+'/'+arm
        common=[py,'-m','scripts.train_grasp_act','--dataset',data,'--done-loss','balanced_bce_v1',
            '--done-loss-weight','1','--command-history-dropout',str(p)]
        jobs += [job(arm+'/smoke300',common+['--output',root+'/smoke','--stage','smoke','--steps','300',
            '--max-wall-s','1800'],['compose-data','data-review-receipt']),
            job(arm+'/main10k',common+['--output',root+'/main','--stage','main','--steps','10000',
            '--max-wall-s','21600','--resume',root+'/smoke/step-000300','--smoke-summary',root+'/smoke/summary.json',
            '--approval',root+'/main-approval.json'],[arm+'/smoke300',arm+'/smoke-review-receipt']),
            job(arm+'/heldout',[py,'-m','scripts.evaluate_grasp_act_offline','--dataset',data,'--model',
            root+'/main/step-010000/actor','--output',root+'/heldout'],['p0/main10k','p02/main10k']),
            job(arm+'/heldout-analysis',[py,'-m','scripts.analyze_grasp_act_predictions','--manifest',data+'/manifest.json',
            '--predictions',root+'/heldout/predictions.jsonl','--output',root+'/heldout-analysis'],[arm+'/heldout'])]
        approvals[arm]={'approved':False,'ready':False,'stage':'main','source_sha':source,
            'dataset_manifest_sha256':None,'smoke_summary_sha256':None,'steps':10000,'blank_images':False,
            'command_history_dropout':p,'done_loss':'balanced_bce_v1','done_loss_weight':1.,
            'gate_promotion_authorized_if_all_conditions_pass':False}
    actor=f'/home/ugrp/act6-{short}/selected-actor'
    jobs.append(job('gcp1-deployment-timing',[py,'-m','scripts.benchmark_grasp_act_deployment','--model',actor,
        '--inputs',f'{runs}/act-student-main-91100-f609979c/raw/student-inputs.jsonl',
        '--rgb-root',f'{runs}/act-student-main-91100-f609979c/raw','--output',f'{runs}/act6-{short}/latency.json'],
        ['p0/heldout-analysis','p02/heldout-analysis','candidate-selection-and-transfer-receipt'],
        host='gcp1',machine_type='n4-highcpu-64',threads=[1,2,4,8,16],warmup_N=8,measured_N=32,
        deployment_grid=[{'n_action_steps':n,'temporal_ensemble_coeff':te} for n in (1,2,3,4) for te in (None,.01)]+[
            {'n_action_steps':8,'temporal_ensemble_coeff':None}],
        gate='p95 total CPU RPC+preprocess <= n_action_steps*0.1s; first30 simulator wall/SIM/load measured separately',
        prior_cpu_median_s=.323,prior_cpu_p95_s=.375,mac_measurement_forbidden=True))
    jobs.append(job('closed-loop-once',depends=['gcp1-deployment-timing','deployment-review-receipt','fresh-student-plan-receipt'],
        host='gcp1',max_runs=1,cap_sim_s=90,seed=STUDENT_SEED,
        command_template=[simpy,'-m','scripts.sim_cli','workflow','run','grasp-act-student-pilot','--',
            '--plan',f'{RECORD}/act6-student-plan.json','--protocol',f'{runs}/act6-{short}/protocol.json',
            '--model',actor,'--actor-python',py,'--cap-s','90','--output',f'{runs}/act6-student-{STUDENT_SEED}-{short}/raw',
            '--actor-threads','{measured_threads}','--n-action-steps','{measured_steps}'],
        selection={'arm':None,'actor_sha256':None,'threads':None,'n_action_steps':None,'temporal_ensemble_coeff':None},
        materialization='append --temporal-ensemble-coeff only if selected by deployment receipt; command remains null until review',
        first30_required=True,extra_closed_loop_runs_authorized=False))
    return {'schema':'ugrp.vm3_queue.act6.v1',**states,'source_sha':source,'branch':'claude/act-train','pr':504,
        'project':'ugrp-act-train-1014','status':'PREPARED_UNAPPROVED',
        'gate_promotion_authorized_if_all_conditions_pass':False,'remote_execution_started':False,
        'record':f'{RECORD}/act6.md','teacher_dependency_sha':TEACHER_SHA,'teacher_dependency_root':dependency,
        'prior_queues_untouched':['20261015-act4-40a21045.json','20261015-act5-bd140578.json'],
        'coordinator_approval':{'approved':False,'ready':False},'jobs':jobs,
        'saved_preflight_jobs':[job('full-teacher-stall-census',[py,'-m','scripts.analyze_grasp_act_stall',
            '--teacher-runs-root','/mnt/act-source/home/ugrp/ugrp-sim/runs','--output',base+'/full-teacher-stall.json'])],
        'materialize_protocol':{'paths':[base+'/protocol.json',f'{runs}/act6-{short}/protocol.json'],'value':protocol},
        'main_approval_templates':approvals,
        'data':{'train_episodes':90,'fresh_validation_episodes':5,'excluded_calibration_episodes':5,
            'same_dataset_and_seed_both_arms':True,'noise_calibration_old_holdout_is_development':True,
            'camera_unchanged':True,'recovery_counts_must_be_measured_not_assumed':True},
        'machine':{'simulation':'ugrp-sim-gcp1','simulation_type':'n4-highcpu-64','training':'ugrp-act-l4-pilot1',
            'training_type':'g2-standard-4','max_run_duration':'8h','instance_termination_action':'STOP','idle_shutdown_s':1200},
        'budgets':{'training_max_wall_s_per_arm':23400,'training_max_wall_s_total':46800,
            'gate40_wall_s':14400,'record50_wall_s':18000,'timing_wall_s':1800,'closed_loop_wall_s':1800,
            'separate_8h_windows_per_stage':True,'all_compute_price_and_credit_values':None,
            'disk_gib':{'gate_reserved':10,'record_reserved':50,'converted_and_composed_reserved':40,
                        'checkpoints_reserved':32,'gcp_sim_minimum_free_after_reserved':8,
                        'training_minimum_free_before':80,'mac_floor':20,'arm_floor_if_archive_used':25},
            'raw_estimate_mib':{'gate_per_run':32,'record_per_run':96,'gate_total':1280,'record_total':4800},
            'reserved_writes_must_include_other_approved_jobs':True},
        'required_before_start':[
            'Every stage requires new explicit approval. No previous ACT4/ACT5/f609979c approval is inherited.',
            'Check actual remaining credits/current official prices, budget-stop PubSub/function and active alerts; activation stops owned VMs and forbids restart or host switch.',
            'All gcloud resource commands include --project=ugrp-act-train-1014. Verify 8h STOP and idle 1200s before starting; never bypass.',
            'Verify exact clean ACT+teacher dependency commits and archive hashes; only missing modules come from the dependency checkout.',
            'Full 50 teacher command census still needs remote saved-file analysis; local 2/50 is insufficient for the full-data claim.',
            'Compare fresh seed proposals with live remote inventory; current preparation cannot establish remote non-use.',
            'Gate and recording use identical source/noise/host/settings; 40 gate trials have training RGB OFF. No recording before verified 38/40.',
            'Stop same-defect owned runs immediately on confirmed control/physics defect; preserve all failures and HOST_ERROR. Do not fill denominator after known defect.',
            'Check recovery approach edge/lost-return coverage, achieved noise covariance and current camera; passing success alone does not prove new recovery coverage.',
            'Recording transfer to retained L4 persistent disk requires full hashes; all raw originals remain on GCP. No Mac bulk transfer.',
            'Do not combine hosts/machine types or pass original model/teacher success forward. No online truth, teacher correction, top-camera control, or weld.',
            'Per-arm smoke300 then total10k from matching smoke; fixed final checkpoint, same seed and data. No new early model selection on fresh holdout.',
            'After timing, materialize exactly one reviewed student run and inspect first30 plus >=6 frames through 90s; no automatic remainder.'],
        'after_each_stage':['summary JSON for every run including failure/HOST_ERROR, raw locations and sha256',
            'retrieve only light evidence and verify; stop only owned processes and verify owned VM TERMINATED',
            'new selected/comparison checkpoints require unique GitHub Release assets and re-download/hash/load verification']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    source=source_sha();q=build_queue(source)
    q['analysis_summary_sha256']=sha256(ROOT/RECORD/'act6-summary.json')
    a.output_dir.mkdir(parents=True,exist_ok=True);path=a.output_dir/f'20261015-act6-{source[:8]}.json'
    if path.exists():raise FileExistsError(path)
    write_json(path,q);print(json.dumps({'path':str(path),'sha256':sha256(path),'source_sha':source,'approved':False}))


if __name__=='__main__':main()
