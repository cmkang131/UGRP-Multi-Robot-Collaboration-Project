"""Runner glue for solo_carry (scripts/run_grasp_act_teacher.py). Imported only when solo_carry != 'off'.

DERIVED / UNVERIFIED (solo-e2e/20261024): never exercised by a physics run.
"""
from __future__ import annotations

from harness import solo_carry_contract as sc
from harness import solo_carry_eval as ev
from harness import solo_carry_recorder as rec


def header(plan, carry_cap_s):
    """result.json block written before the first tick."""
    return {'mode': sc.MODE, 'status': sc.STATUS, 'cargo_kind': sc.OBJECT_KIND, 'cargo': plan['solo_cargo'],
            'slot': plan['solo_slot'], 'carry_cap_s': carry_cap_s,
            'instruction_tuples': {'grasp': list(sc.grasp_instruction(False)), 'carry': list(sc.carry_instruction())}}


def finalize(report, controller, rows, plan, recorders, *, origin, cap_s, carry_cap_s):
    """Fill the report after the loop; ``controller`` is the SoloCarryTeacher or None (never handed over)."""
    lower = None
    if controller is None:
        report['carry'] = {'started': False, 'reason': 'no_stable_lift_3s'}
    else:
        lower = next((e['t'] for e in controller.events if e.get('event') == 'phase' and e.get('to') == 'lower'), None)
        report['carry'] = controller.diagnostic()
    report['solo_carry_eval'] = ev.evaluate(rows, plan['solo_slot'], sc.ROBOT_ID, lower_start_t=lower,
                                            cap_s=cap_s + carry_cap_s, t0=origin)
    report['carry_recording'] = rec.recording_summary(recorders)
    return report['solo_carry_eval']
