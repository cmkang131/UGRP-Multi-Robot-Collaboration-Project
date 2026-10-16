"""egomap49 registered schedule; original egomap43 arrival/AMCL unchanged."""
from harness.self_map_closed_loop import RememberedGoal
from harness.active_navfn_start import StartCycleNavigator

OPTION='remembered_goal_360_v1'


def attach(explorer,*,map_utility='off',seed=49001,return_policy='off'):
    if map_utility=='off':
        if return_policy!='off':raise ValueError('RETURN_POLICY_REQUIRES_MAP_UTILITY')
        return explorer
    if map_utility!=OPTION:raise ValueError('UNKNOWN_MAP_UTILITY')
    controller=Return360(explorer,seed=seed)
    if return_policy!='off':
        from harness.own_traversal_graph import attach as attach_traversal
        return attach_traversal(controller,return_policy=return_policy)
    return controller


class Return360(RememberedGoal):
    def loss_due(self,t):
        return t-self.started>=360.

    def make_navigator(self):
        # Same egomap47 start-cell/recovery and exploration cycle implementation.
        return StartCycleNavigator()

    def lose(self,t,frame_id):
        if self.goal is not None:
            assert self.goal['t_sim']<t and self.goal['first_t']<=self.goal['t_sim']
        super().lose(t,frame_id)
        self.events.append(dict(t=float(t),frame_id=frame_id,reason='remembered_target_assigned',
            target=None if self.goal is None else self.goal['candidate_id'],
            first_detection_t=None if self.goal is None else self.goal['first_t'],
            first_confirmation_t=None if self.goal is None else self.goal['t_sim']))
