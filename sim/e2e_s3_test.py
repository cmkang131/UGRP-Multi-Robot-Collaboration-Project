"""Test-only beam-to-B scene owner. Legacy S3 physics; no eval control inputs."""
import copy
import json
from pathlib import Path
from harness.zone_final_pair_binding import bind
from sim.zone_s3_no_prior import PhysicsBackend as Constructor
from sim.s3_release_epoch import PhysicsBackend as Previous, CheckpointCarryPort

ROOT = Path(__file__).resolve().parents[1]


def test_scenario():
    from sim.zone_scenario_scene import load_scenario
    scenario = load_scenario('e2e_one_beam_ownmap')
    fixture = json.loads((ROOT/'experiments/2026-10-09-s3-no-prior/s3fix10/scene-setup.json').read_text())['cases']['pair']
    beam = fixture['truth']['items']['beam_1']
    # Omit S1/S2 navigation: carriers enter the same S3 alignment fixture.
    # The scene beam remains at the scenario's ORIGINAL initial placement.
    for rid in ('r1','r2'):
        row = fixture['robots'][rid]['pose']
        p = copy.deepcopy(row['robot_xyz_m'])
        p[0] += 1.275-beam['x']; p[1] += .05-beam['y']
        scenario['eval']['setup']['robot_spawns'][rid] = [*p,row['robot_yaw_rad']]
    return scenario


def make_scene(bundle, seed):
    from sim.zone_scenario_scene import ScenarioFinalV3Scene
    from sim.render_profile import install
    from sim.final_pair_highpose_nearclip import wrap
    from sim import masterpi_camera_review_v3 as camera
    from sim.s2_servo_stiffness import transform_xml
    scene = wrap(install(ScenarioFinalV3Scene.from_scenario(test_scenario(), seed), 'floor_light_v1'))
    original = scene.robot_transform
    def transform(xml, **kwargs):
        xml = camera.transform_xml(original(xml, **kwargs),profile_id=camera.PROFILE_ID)
        for rid in ('r1','r2','r3'):
            xml = transform_xml(xml,servo_stiffness='real_v1',robot_id=rid)
        return xml
    scene.robot_transform = transform
    return scene


class PhysicsBackend(Previous):
    def __init__(self, bundle, out, *, seed):
        self.io_mode = bundle['options']['s3_io']; self.host_timing = {}
        bind(Constructor.__init__,make_scene=make_scene)(self,bundle,out,seed=seed)

    def reset(self, cap):
        from sim.solo_cyan_v106 import PhysicsBackend as Reset
        from sim.s3_motion_ports import attach
        from scripts.run_final_environment_checks import write
        from scripts.run_zone_study_integration import placements_match
        elapsed = Reset.reset(self,cap)
        self.spec = self.scene.spec
        placements_match(test_scenario(),self)
        attach(self,pair_heading=self.bundle['options']['pair_heading'])
        for rid in ('r1','r2'):
            self.ports[rid] = CheckpointCarryPort(self.world,rid,
                coupled=lambda:all(self.commands.get(r,{}).get(1,2000)<=1600 for r in ('r1','r2')),
                allow_reverse=True,allow_mecanum=True,min_wheel_cmd='real_v1',alignment_pulse='real_fine_v1')
        write(self.out/'eval_only/drive-v7.json',self.world.drive_profile_record)
        write(self.out/'eval_only/test-setup-scope.json',dict(source='test_route_provider',
            scene='e2e_one_beam_ownmap',carrier_entrance='synthetic S3 alignment fixture',
            beam_initial_placement_unchanged=True,r3='idle',E2E_success_eligible=False,
            controller_feedback=False))
        return elapsed

    def eval_sample(self):
        from sim.e2e_s3_final_release import supported_final
        from sim.zone_s3_no_prior import PhysicalStop
        option=self.bundle.get('final_release_guard','off')
        final=getattr(self,'final_segment_getter',lambda:False)()
        row=self.setdown_row()
        supported=supported_final(row,final,option)
        if option=='floor_latch':
            if supported:
                self.lifted.discard('beam_1')
                self._final_floor_latched=True
            elif getattr(self,'_final_floor_latched',False):
                # An unsupported next frame re-arms the unchanged drop guard.
                self.lifted.add('beam_1');self._final_floor_latched=False
        try:super().eval_sample()
        except PhysicalStop as exc:
            if option!='supported_phase' or str(exc)!='LOAD_DROP:beam_1' or not supported:raise
            self.record_dynamics()
            self._append('eval_only/setdown.jsonl',row)
            self.progress()
        if supported:
            self._append('eval_only/final-release-classification.jsonl',dict(row,
                option=option,classification='supported_final_release_before_OPEN_dispatch',
                final_segment=True,free_fall=False,controller_feedback=False))
        import numpy as np
        m,d=self.world.model,self.world.data
        bounds=[]
        for g in self._box_geom['beam_1']:
            if int(m.geom_type[g])!=6:raise ValueError('BEAM_BOX_OUTLINE_REQUIRED')
            extent=abs(d.geom_xmat[g].reshape(3,3))@m.geom_size[g]
            bounds.append((d.geom_xpos[g]-extent,d.geom_xpos[g]+extent))
        self._append('eval_only/beam-outline.jsonl',dict(t=self.now,
            min_xyz_m=np.min([a for a,b in bounds],axis=0).tolist(),
            max_xyz_m=np.max([b for a,b in bounds],axis=0).tolist(),controller_feedback=False))
