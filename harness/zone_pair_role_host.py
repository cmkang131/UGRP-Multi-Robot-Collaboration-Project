"""Explicit T07 host adapter; ordinary OwnCamTeamHost stays sealed."""
from harness.zone_own_team_host import OwnCamTeamHost as LegacyHost, HOST_APIS


class RoleAwareHostMixin:
    """Select role dispatch on this host only, with the original own executors."""
    def enable_pair_carry(self, sheets, params, *, controller_factory=None, rendezvous_timeout_s=5., heartbeat_timeout_s=.15,
                          policy='v5h'):
        """Attach the M2 dispatcher; may also be used with a simulator-free host."""
        from harness.zone_pair_role_executor import PairTeam, m2_controller
        self.pairs = PairTeam({r: s.executor for r, s in self.robots.items()}, sheets, params,
                              cancel_scheduled=self._drop_scheduled,
                              contact_profile=self.contact_record['profile'], weld=False,
                              controller_factory=controller_factory or m2_controller,
                              rendezvous_timeout_s=rendezvous_timeout_s, heartbeat_timeout_s=heartbeat_timeout_s,
                              policy=policy)
        self._next_pair_arm = 0.  # original CLI clock lifetime, never reset on a submission

    def call(self, rid, api, *args):
        """The study layer's only door into an executor: the job API of THAT robot."""
        if api not in HOST_APIS:
            raise ValueError(f'unknown executor API {api!r}; known: {HOST_APIS}')
        slot = self.robots[rid]
        ex = slot.executor
        now = float(self.world.data.time)
        ex.now = now
        if self.closed:
            ack = ex.refuse(api, 'EPISODE_ENDED')
        elif slot.dead:
            ack = ex.refuse(api, 'ROBOT_STOPPED')
        elif api == 'pair_carry':
            if getattr(self, 'pairs', None) is None:
                ack = ex.refuse(api, 'PAIR_NOT_CONFIGURED')
            elif len(args) not in (3, 4):
                ack = ex.refuse(api, 'BAD_PAIR_ARGUMENTS')
            else:
                ack = self.pairs.start(rid, *args, now=now)
        else:
            ack = getattr(ex, api)(*args)
            if api == 'abort' and ack['accepted']:
                self._drop_scheduled(rid, now, 'abort')
        self._pair_safety(now)
        self.api_calls.append(ack)
        return ack


class OwnCamTeamHost(RoleAwareHostMixin, LegacyHost):
    """Opt-in construction path; no global monkeypatch or simulator changes."""
