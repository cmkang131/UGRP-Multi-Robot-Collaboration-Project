"""Study configuration for the v64 event queue; no private message lifecycle."""
from dataclasses import asdict, dataclass

from harness.zone_event_scheduler import EventScheduler

DECISION_POLICY = 'v64_tagged_event_inputs.v4'
MESSAGE_LANE = 'message'


@dataclass(frozen=True)
class DecisionLimits:
    max_calls_total: int = 90
    max_utterances_per_actor: int = 2
    max_utterances_total: int = 6

    def __post_init__(self):
        for name, value in asdict(self).items():
            if type(value) is not int or value < 1:
                raise ValueError(f'{name} must be a positive integer')


class DecisionScheduler(EventScheduler):
    """Configure event inputs; all lifecycle handling is inherited from v64."""

    def __init__(self, *args, own_job, decision_limits, external_budget_spent=lambda: False, **kwargs):
        self.decision_limits = decision_limits
        super().__init__(*args, received_event_cause=MESSAGE_LANE,
                         event_available_at=lambda actor, cause: (
                             float('inf') if cause and own_job(actor) is not None else self.clock),
                         max_calls_total=decision_limits.max_calls_total,
                         external_budget_spent=external_budget_spent, **kwargs)
