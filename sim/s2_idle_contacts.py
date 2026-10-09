"""Explicit constructor binding of #407 freeze, after S2 bundle validation.

Uses the inherited constructor-scoped world-factory binding in the single-SIM
process. Restores the factory even when construction fails; no global default.
"""
from harness.idle_robot_contacts_contract import validate, policy


def backend_class(base=None):
    if base is None:
        from sim.s2_align_pulse import backend_class as previous
        base = previous()

    class Backend(base):
        def __init__(self, bundle, *args, **kwargs):
            option = validate(bundle)  # refuse foreign/research bundles before creating a world
            if option == 'off':
                super().__init__(bundle, *args, **kwargs)
                return
            from sim import s2_realism_camera_binding as camera
            original = camera.build_world

            def build(*a, **kw):
                return original(*a, **kw, roller_collision='mesh', idle_robot_contacts=option)

            try:
                camera.build_world = build
                super().__init__(bundle, *args, **kwargs)
            finally:
                camera.build_world = original
            if (self.world.idle_robot_contacts != option or self.world.roller_collision != 'mesh'
                    or self.world.drive_profile_record.get('idle_robot_contacts') != option):
                self.close()
                raise ValueError('IDLE_CONTACTS_NOT_APPLIED')

        def reset(self, cap):
            elapsed = super().reset(cap)
            if validate(self.bundle) != 'off':
                from scripts.run_final_environment_checks import write
                write(self.out/'eval_only/idle-contacts-option.json',dict(
                    option=self.world.idle_robot_contacts,roller_collision=self.world.roller_collision,
                    policy=policy(),controller_feedback=False))
            return elapsed

    return Backend
