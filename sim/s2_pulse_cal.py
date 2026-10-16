"""S2 opt-in port binding; fine pulse support already exists, shared port untouched."""
from sim.s2_align_pulse import FinePulsePort


def backend_class(base=None):
    if base is None:
        from sim.s2_eval_camera_trace import backend_class as previous
        base=previous()
    class Backend(base):
        def reset(self,cap):
            elapsed=super().reset(cap)
            option=self.bundle['options'].get('pulse_motion_model','off')
            if option not in ('off','v7_pulse_cal_v1'):raise ValueError('unsupported pulse model')
            if option!='off':
                if self.bundle['options'].get('alignment_pulse')!='real_fine_v1':
                    raise ValueError('calibrated S2 navigation requires fine port')
                if not all(isinstance(p,FinePulsePort) for p in self.ports.values()):
                    raise ValueError('fine port lost at reset')
            return elapsed
    return Backend
