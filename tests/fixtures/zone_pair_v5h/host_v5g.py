def _apply(self, rid, action, now):
        row = {'t': round(float(now), 4), **action}
        self._sink(rid, row)
        self.robots[rid].port.apply(action, now)

def _hold(self, rid, now):
        self._sink(rid, {'t': round(float(now), 4), 'kind': 'hold'})
        self.robots[rid].port.hold(now)
