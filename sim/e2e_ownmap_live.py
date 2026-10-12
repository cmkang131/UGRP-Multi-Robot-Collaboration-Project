"""Standard initial scene, native v7 physics, write-only referee.

Unlike the S3 stage probe, never restores grasp fixtures or moves the beam.
Only capture() RGB and commanded actuator history cross to the runtime.
"""
from harness.zone_final_pair_binding import bind
from sim.zone_s3_no_prior import PhysicsBackend as Constructor
from sim.e2e_s3_test import PhysicsBackend as Evaluation


def make_scene(bundle,seed):
    from sim.zone_scenario_scene import load_scenario,ScenarioFinalV3Scene
    from sim.render_profile import install
    from sim.final_pair_highpose_nearclip import wrap
    from sim import masterpi_camera_review_v3 as camera
    from sim.s2_servo_stiffness import transform_xml
    scene=wrap(install(ScenarioFinalV3Scene.from_scenario(load_scenario('e2e_one_beam_ownmap'),seed),'floor_light_v1'))
    original=scene.robot_transform
    def transform(xml,**kwargs):
        xml=camera.transform_xml(original(xml,**kwargs),profile_id=camera.PROFILE_ID)
        for rid in ('r1','r2','r3'):xml=transform_xml(xml,servo_stiffness='real_v1',robot_id=rid)
        return xml
    scene.robot_transform=transform
    return scene


class PhysicsBackend(Evaluation):
    def __init__(self,bundle,out,*,seed):
        self.io_mode=bundle['options']['s3_io'];self.host_timing={}
        self.authorize_pulse=lambda rid,action,now:False
        bind(Constructor.__init__,make_scene=make_scene)(self,bundle,out,seed=seed)

    def reset(self,cap):
        from sim.solo_cyan_v106 import PhysicsBackend as Reset
        from sim.e2e_pulse_port import ResidualPulsePort
        from sim.s2_align_pulse import FinePulsePort
        from sim.zone_scenario_scene import load_scenario
        from scripts.run_zone_study_integration import placements_match
        elapsed=Reset.reset(self,cap)
        self.spec=self.scene.spec
        placements_match(load_scenario('e2e_one_beam_ownmap'),self)
        for rid in ('r1','r2'):
            self.ports[rid]=ResidualPulsePort(self.world,rid,
                coupled=lambda:all(self.commands.get(r,{}).get(1,2000)<=1600 for r in ('r1','r2')),
                allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1',
                pulse_budget=self.bundle['e2e_options']['pulse_budget'],
                require_authorization=self.bundle['e2e_options'].get('pulse_authorization')=='current_go_v1',
                authorize_pulse=lambda action,now,rid=rid:self.authorize_pulse(rid,action,now))
        self.ports['r3']=FinePulsePort(self.world,'r3',allow_reverse=True,allow_mecanum=True,
                                     min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
        return elapsed
