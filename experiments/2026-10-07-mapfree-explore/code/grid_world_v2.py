"""Evaluation correction only: the same oriented rectangle as the planner.

The v1 circle evaluator and all sensor/noise/temporal models remain unchanged.
No actor imports this module or receives its collision labels.
"""
from grid_world import GridWorld
from diagnose_environment import OracleWorld, rectangle_contacts


class RectangleWorld(GridWorld):
    def collision(self, xy):
        return bool(rectangle_contacts([*xy, self.pose[2]], self.rects, self.static['bounds_m']))


class RectangleOracleWorld(OracleWorld, RectangleWorld):
    pass
