"""S3 pair heading uses the same command-only finite pulse ports as S2.

Off keeps every existing port and record byte-for-byte. This declares actuator
capability only; it does not supply state, pose priors or evaluation to control.
"""
from sim.s2_align_pulse import FinePulsePort
from sim.camera_robot_port import CameraRobotPort
from sim.s3_buffered_io import PhysicsBackend as Previous
from harness.zone_s3_pair_heading import OPTION
from scripts.run_final_environment_checks import write


class PairPhasePort(FinePulsePort):
    def __init__(self, *args, coupled, **kwargs):
        super().__init__(*args, **kwargs)
        self.coupled = coupled

    def apply(self, action, sim_time):
        if self.coupled() and action['kind'] in ('drive', 'mecanum'):
            return CameraRobotPort.apply(self, action, sim_time)
        return super().apply(action, sim_time)


def attach(backend, *, pair_heading='off'):
    if pair_heading == 'off':
        return backend
    if pair_heading != OPTION:
        raise ValueError('unknown S3 pair motion port option')
    for rid in ('r1', 'r2'):
        backend.ports[rid] = PairPhasePort(backend.world, rid,
            coupled=lambda: all(backend.commands.get(r, {}).get(1, 2000) <= 1600 for r in ('r1','r2')),
            allow_reverse=True,
            allow_mecanum=True, min_wheel_cmd='real_v1', alignment_pulse='real_fine_v1')
    write(backend.out/'eval_only/pair-motion-ports.json', dict(option=pair_heading,
        ports={r:type(p).__name__ for r,p in backend.ports.items()},
        min_wheel_cmd='real_v1', alignment_pulse='real_fine_v1',
        scope='S2 heading pulse; both issued grips closed permits unchanged pair continuous commands', state_feedback=False))
    return backend


class PhysicsBackend(Previous):
    def __init__(self, bundle, *args, **kwargs):
        mode=bundle.get('options', {}).get('pair_heading', 'off')
        if mode not in ('off',OPTION):
            raise ValueError('unknown S3 pair motion port option')
        super().__init__(bundle, *args, **kwargs)
        try:
            attach(self, pair_heading=mode)
        except Exception:
            self.close()
            raise
