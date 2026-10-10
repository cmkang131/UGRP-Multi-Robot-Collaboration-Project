"""Opt-in line-map view of the same private memory. Default delegates unchanged."""
import copy
from harness.self_wall_memory_motion import SelfWallMemory as Previous
from harness.self_wall_segments import OPTION,build_segment_map


class SelfWallMemory(Previous):
    def __init__(self,*args,wall_map='off',**kwargs):
        if wall_map not in ('off',OPTION):raise ValueError('UNKNOWN_WALL_MAP')
        super().__init__(*args,**kwargs)
        if wall_map!= 'off' and self.self_map is None:raise ValueError('SEGMENTS_REQUIRE_OWN_MAP')
        self.wall_map=wall_map
        self._segment_observations={}

    def observe_wall(self,record,*,wall_points=None,**kwargs):
        if self.wall_map!='off' and wall_points is None:raise ValueError('ACTUAL_CONTACT_POINTS_REQUIRED')
        result=super().observe_wall(record,**kwargs)
        if self.wall_map!='off':
            self._segment_observations[record['view_index']]={**copy.deepcopy(wall_points),
                'pose_covariance':self.self_map.odom.covariance.tolist()}
        return result

    def segment_map(self):
        if self.wall_map=='off':return None
        rows=self.pose_graph_result['ledger'] if self.pose_graph_result else self.self_map.ledger
        return build_segment_map([dict(r,robot_id=self.robot_id) for r in rows],self._segment_observations,
            robot_id=self.robot_id,wall_map=self.wall_map)

    def snapshot(self):
        result=super().snapshot()
        if self.wall_map!='off':result['self_wall_segments']=self.segment_map()
        return result
