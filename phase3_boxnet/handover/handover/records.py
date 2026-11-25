"""Raw evidence written as it is observed. Each output directory belongs to one invocation."""
import csv
import json
import math

from handover import layout


class StopTrial(Exception):
    def __init__(self, stage, reason):
        super().__init__(reason)
        self.stage = stage


def write_json(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


class Recorder:
    def __init__(self, out, trial, stack):
        self.out, self.trial = out, trial
        self.events = stack.enter_context((out / "events.jsonl").open("x", buffering=1))
        self.observations = stack.enter_context((out / "observations.jsonl").open("x", buffering=1))
        self.observation_count = 0
        stream = stack.enter_context((out / "chassis.csv").open("x", newline="", buffering=1))
        self.csv = csv.writer(stream)
        self.csv.writerow(["step", "sim_s", *[r+"_"+k for r in ("r1", "r2")
                          for k in ("x", "y", "xmin", "xmax", "ymin", "ymax")]])
        self.rooms = [layout.room(trial, r) for r in ("r1", "r2")]
        self.step = -1
        self.now = 0.
        self.last_write = -1
        self.window = None
        self.last = None
        self.seq = 0

    def event(self, name, **data):
        row = {"seq": self.seq, "sim_s": self.now, "event": name, **data}
        self.events.write(json.dumps(row, allow_nan=False) + "\n")
        self.seq += 1
        return row

    def observe(self, name, *, jpg=None, **data):
        """Diagnostic measurements share the event clock but never advance a scoring milestone."""
        if jpg is not None:
            filename = f"obs-{self.observation_count:04d}-{name}.jpg"
            with (self.out / filename).open("xb") as image:
                image.write(jpg)
            data["frame"] = filename
        row = dict(observation=name, sim_s=self.now, next_event_seq=self.seq, **data)
        self.observations.write(json.dumps(row, allow_nan=False) + "\n")
        self.observation_count += 1

    def sample(self, now, x1, y1, x2, y2):
        """Called at setup and immediately after every mj_step, using integrated free-joint qpos."""
        self.step += 1
        self.now = now
        points = ((x1, y1), (x2, y2))
        self.last = points
        if self.window is None:
            self.window = [[x, x, y, y] for x, y in points]
        for i, (x, y) in enumerate(points):
            w = self.window[i]
            w[:] = [min(w[0], x), max(w[1], x), min(w[2], y), max(w[3], y)]
        for i, (x, y) in enumerate(points):
            if not (math.isfinite(x) and math.isfinite(y)):
                raise StopTrial("room_trace", "nonfinite chassis coordinate")
            if layout.margin(self.rooms[i], x, y) <= 0:
                self.flush()
                self.event("room_violation", robot=("r1", "r2")[i], xy=[x, y], step=self.step)
                raise StopTrial("room_limit", "chassis centre reached or crossed its room boundary")
        if self.step == 0:
            self.flush()

    def flush(self):
        if self.last_write == self.step:
            return
        values = []
        for (x, y), envelope in zip(self.last, self.window):
            values.extend((x, y, *envelope))
        self.csv.writerow([self.step, f"{self.now:.12f}", *values])
        self.window, self.last_write = None, self.step
