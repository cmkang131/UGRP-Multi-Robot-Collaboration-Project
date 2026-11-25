"""Admission, outstanding reservations and settled usage for one invocation."""
from contextlib import contextmanager
from decimal import Decimal
from time import sleep

from storage import locked, read_json, write_json

CALL_CEILING = "failure over call ceiling"
COST_LIMIT = "failure over invocation cost limit"
CALL_LIMIT = "failure over invocation call limit"
CLIENT_LIMIT = "failure over client budget"
TOKEN_LIMIT = "failure over token length limit"
MODEL_SERVICE = "failure model service"
# The gateway answered, but every reply-bearing attempt was unreadable or otherwise
# unusable.  This is distinct from a transport service that never supplied a reply.
UNUSABLE_REPLY = "failure unusable model reply"
OUTPUT_LIMIT = "failure output limit"


class StopEpisode(Exception):
    def __init__(self, label, detail="", interrupted=False):
        super().__init__(detail or label)
        self.label = label
        self.detail = detail
        self.interrupted = interrupted


class Invocation:
    def __init__(self, out, path):
        self.out = out
        self.path = path

    def create(self, max_calls, max_cost, model, requested=(), *, shuffle=None, jobs=1, selectors=None):
        write_json(self.path, dict(model=model, max_calls=max_calls, max_cost_usd=str(max_cost),
                                   requested=list(requested), shuffle=shuffle, jobs=jobs, selectors=selectors, reservations={},
                                   calls=0, reported_cost_usd="0", guard_cost_usd="0",
                                   stop_label=None, stop_detail=""))

    @contextmanager
    def transaction(self):
        with locked(self.out / ".requests.lock"):
            state = read_json(self.path)
            try:
                yield state
            finally:
                write_json(self.path, state)

    @staticmethod
    def stop(state, label, detail):
        state.update(stop_label=label, stop_detail=detail)
        raise StopEpisode(label, detail, interrupted=True)

    @classmethod
    def check(cls, state, reserve=Decimal(0)):
        if state["stop_label"]:
            raise StopEpisode(state["stop_label"], state["stop_detail"], interrupted=True)
        if state["max_calls"] is not None and state["calls"] >= state["max_calls"]:
            cls.stop(state, CALL_LIMIT, "Invocation attempt count reached")
        spent, cap = Decimal(state["guard_cost_usd"]), Decimal(state["max_cost_usd"])
        if spent >= cap or spent + reserve > cap:
            detail = "Invocation cannot fund the next reservation" if spent < cap else "Invocation cost reached"
            cls.stop(state, COST_LIMIT, detail)

    def reserve(self, key, amount):
        while True:
            with self.transaction() as state:
                self.check(state, amount)
                pending = state["reservations"]
                if key in pending:
                    raise ValueError(f"Duplicate outstanding reservation: {key}")
                call_room = state["max_calls"] is None or state["calls"] + len(pending) < state["max_calls"]
                held = sum(map(Decimal, pending.values()), Decimal(0))
                remaining = Decimal(state["max_cost_usd"]) - Decimal(state["guard_cost_usd"]) - held
                if call_room and amount <= remaining:
                    pending[key] = str(amount)
                    return
            # Another worker can settle for less than its upper bound and free this slot.
            sleep(0.025)

    def settle(self, key, calls, reported, charged):
        with self.transaction() as state:
            reserved = Decimal(state["reservations"].pop(key))
            state["calls"] += calls
            state["reported_cost_usd"] = str(Decimal(state["reported_cost_usd"]) + reported)
            if charged is None:
                charged = reserved
                state.update(stop_label=CLIENT_LIMIT, stop_detail="Unresolved client settlement")
            state["guard_cost_usd"] = str(Decimal(state["guard_cost_usd"]) + charged)
