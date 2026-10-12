"""Default-off diagnostic entrance candidates; real RGB/GO gates remain intact."""
import json
from pathlib import Path

OPTIONS=('off','saved_phase','local_servo')


def attach(ep,option='off',*,source='test_route_provider'):
    if option=='off':return ep
    if option not in OPTIONS or source!='test_route_provider':raise ValueError('TEST_ENTRANCE_ONLY')
    ctl=ep.controller
    if option=='saved_phase':
        from scripts.run_s3_alignment_probe import resume_alignment_phase,STAGE_T
        p=Path(__file__).resolve().parents[1]/'experiments/2026-10-09-s3-no-prior/s3fix8/alignment-phase.json'
        phase=json.loads(p.read_text())
        if phase['gt_fields'] or phase['source_t']!=STAGE_T:raise ValueError('OWN_HISTORY_ONLY')
        resume_alignment_phase(ep,ctl.state_t,phase['robots'][ep.own.robot_id],STAGE_T)
        ctl.log(ctl.rid,'test_saved_phase',ctl.state_t,source=str(p),synthetic_stage_entrance=True)
        return ep
    old=ctl._on_beam_obs
    def observe(now,beam):
        previous=getattr(ctl,'pending_reapproach',None)
        first=not ctl.vo_obs
        old(now,beam)
        obs=ep.own.last_obs;grip=beam.get('grip_base_m');heading=beam.get('axis_heading_rad')
        near=(first and previous is None and getattr(ctl,'pending_reapproach',None) is not None
            and ctl.state=='align' and ctl.seg==0 and not ctl.beam_grasp_confirmed
            and ep.own.servo.get(1)==2000 and beam.get('visible') and beam.get('end_visible')
            and beam.get('reason')=='BAND_VISIBLE' and grip is not None and heading is not None
            and .10<=grip[0]<=.30 and abs(grip[1])<=.05 and abs(heading)<=.25
            and obs is not None and abs(obs['sim_time']-now)<1e-8)
        if near:
            ctl.pending_reapproach=None
            ctl.log(ctl.rid,'test_local_alignment_owner',now,frame_id=obs['frame_id'],sha256=obs['sha256'],
                    grip_base_m=grip,heading_rad=heading,source='fresh own RGB',
                    legacy_far_prestation_check='not applicable to near S3 fixture',GO_bypassed=False)
    ctl._on_beam_obs=observe
    return ep
