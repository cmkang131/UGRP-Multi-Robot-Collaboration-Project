"""Evaluation-only T13b denominators; never imported by the controller.

Applying an open fault is not evidence that an item physically fell. Likewise,
a student command/claim is not physical recovery. A separate referee supplies
physical_effect/discovered/recovered after the trial, with raw evidence links.
"""
from dataclasses import asdict, dataclass

from harness.zone_study_contract import ContractViolation

EFFECTS = {'item_moved': ('item_moved', 'none_item_held'),
           'item_dropped': ('gripper_fault_open', 'none_item_not_held')}


@dataclass(frozen=True)
class EventTrial:
    run_id: str
    event_id: str
    kind: str
    terminal: str  # completed / cap / host_error / unexecuted
    effect: str | None = None
    physical_effect: bool | None = None
    discovered: bool | None = None
    recovered: bool | None = None


def summarize(trials):
    """Keep every assignment, including missing effects, caps, errors and no-ops.

    The caller provides one row per run/event, including unexecuted allocations.
    No-op rows are excluded only from *effective-event* recovery denominators.
    A zero denominator yields None, never a perfect rate or a fabricated fail.
    """
    rows, seen = [], set()
    for row in trials:
        if not isinstance(row, EventTrial) or not isinstance(row.kind, str) or row.kind not in EFFECTS:
            raise ContractViolation('unsupported event trial')
        if not all(isinstance(v, str) and v for v in (row.run_id, row.event_id)) \
                or (row.run_id, row.event_id) in seen:
            raise ContractViolation('invalid/duplicate run-event assignment')
        seen.add((row.run_id, row.event_id))
        if row.terminal not in ('completed', 'cap', 'host_error', 'unexecuted') \
                or row.effect not in (*EFFECTS[row.kind], None):
            raise ContractViolation('unsupported terminal/effect')
        if any(v is not None and type(v) is not bool
               for v in (row.physical_effect, row.discovered, row.recovered)):
            raise ContractViolation('judgments must be boolean or unknown')
        noop = row.effect == EFFECTS[row.kind][1]
        if row.terminal == 'unexecuted' and any(v is not None for v in
                (row.effect, row.physical_effect, row.discovered, row.recovered)):
            raise ContractViolation('unexecuted assignment cannot have results')
        if row.effect is None and row.physical_effect is not None:
            raise ContractViolation('physical effect needs application evidence')
        if noop and any(v is not None for v in (row.discovered, row.recovered)):
            raise ContractViolation('no-op has no event discovery/recovery verdict')
        if noop and row.physical_effect is True:
            raise ContractViolation('no-op cannot have a physical event effect')
        if row.physical_effect is not True and any(v is not None for v in (row.discovered, row.recovered)):
            raise ContractViolation('recovery denominator needs a verified physical effect')
        if row.recovered is True and (row.discovered is not True or row.terminal != 'completed'):
            raise ContractViolation('recovery needs discovery and completed event trial')
        rows.append(row)
    output = {'basis': 'eval_only', 'assignments': len(rows), 'rows': [asdict(r) for r in rows], 'by_kind': {}}
    for kind, (applied, noop) in EFFECTS.items():
        group = [r for r in rows if r.kind == kind]
        effective = [r for r in group if r.physical_effect is True]
        recovered = sum(r.recovered is True for r in effective)
        output['by_kind'][kind] = {
            'assigned': len(group), 'applied': sum(r.effect == applied for r in group),
            'noop': sum(r.effect == noop for r in group),
            'effect_unrecorded': sum(r.effect is None for r in group),
            'physical_effective': len(effective),
            'applied_without_verified_effect': sum(r.effect == applied and r.physical_effect is not True for r in group),
            'discovered_effective': sum(r.discovered is True for r in effective),
            'recovered_effective': recovered,
            'recovery_unknown': sum(r.recovered is None for r in effective),
            'recovery_rate_effective': recovered / len(effective) if effective else None,
            'recovery_verdict_complete': bool(effective) and all(r.recovered is not None for r in effective),
            'event_establishment_insufficient': not effective,
            'terminal_counts': {t: sum(r.terminal == t for r in group)
                                for t in ('completed', 'cap', 'host_error', 'unexecuted')},
        }
    return output
