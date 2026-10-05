"""Bounded scripted T13 actor; no event schedule or private state is accepted."""

from harness.zone_target_identity import BOX_KINDS


class TargetActor:
    def __init__(self, executor, *, order_id, start_after_s, max_searches=12):
        self.executor = executor
        self.order_id = order_id
        self.start_after_s = float(start_after_s)
        self.max_searches = int(max_searches)
        self.searches, self.last_sequence = 0, None
        self.actions = []
        self.finished = False
        order = executor.jobs._orders[order_id]
        first = order['initial_location']['slot']
        self.search_slots = [first] + sorted(s for s in executor.slots if s != first)
        self.search_phase = 'goto'

    def tick(self, now):
        ex = self.executor
        if self.finished or now < self.start_after_s or ex.stopped is not None:
            return
        if ex.jobs.claim(self.order_id)['state'] == 'observed_delivered':
            self.finished = True
            return
        f = ex.recognizer.frame
        if f is None or f.sequence == self.last_sequence:
            return
        self.last_sequence = f.sequence
        if ex.job is not None or ex.target is not None:
            return
        order = ex.jobs._orders[self.order_id]
        if order['kind'] not in BOX_KINDS:
            self.finished = True
            return
        item = order['item_ids'][0] if order['identity'] == 'specific_item' else None
        # Own image ordering only. No item lookup / nearest GT / host selection.
        candidates = sorted((d for d in f.detections if d.kind == order['kind']),
                            key=lambda d: (abs(d.bbox[0]+d.bbox[2]-1.), d.detection_id))
        for d in candidates:
            result = ex.jobs.submit(self.order_id, d.detection_id, item_id=item, now_sim_s=now)
            self.actions.append({'sim_s': now, 'frame_sequence': f.sequence, 'operation': 'submit', 'result': result})
            if result['state'] == 'running':
                return
            if result['reason'] in ('RECOVERY_LIMIT', 'IDENTITY_RELOOK_LIMIT'):
                self.finished = True
                return
        if self.searches >= self.max_searches:
            self.finished = True
            return
        if self.search_phase == 'goto':
            target = self.search_slots[(self.searches//2) % len(self.search_slots)]
            ack = ex.inner.goto(target)
            self.search_phase = 'look'
        else:
            ack = ex.inner.look_around()
            self.search_phase = 'goto'
        self.searches += 1
        self.actions.append({'sim_s': now, 'frame_sequence': f.sequence, 'operation': 'search', 'ack': ack})
