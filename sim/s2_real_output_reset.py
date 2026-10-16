"""v114 lifecycle binding: IntegerClock.reset rebuilds the camera ports."""
from sim.s2_real_output import RealPrimitivePort,StagnationGuard


def backend_class(base=None):
    if base is None:
        from sim.s2_real_output import backend_class as previous
        base=previous()
    class Backend(base):
        def reset(self,cap):
            elapsed=super().reset(cap)
            option=self.bundle['options'].get('min_wheel_cmd','off')
            self.ports={rid:RealPrimitivePort(self.world,rid,allow_reverse=True,allow_mecanum=True,
                        min_wheel_cmd=option) for rid in self.ports}
            self.stagnation=StagnationGuard(self.bundle['options'].get('stagnation_watch','off'))
            if hasattr(self,'out'):
                from scripts.run_final_environment_checks import write
                write(self.out/'eval_only/output-option.json',dict(min_wheel_cmd=option,
                    ports={rid:dict(type=type(p).__name__,option=p.min_wheel_cmd) for rid,p in self.ports.items()},
                    applied_after='IntegerClock.reset and grid snap'))
            return elapsed
    return Backend
