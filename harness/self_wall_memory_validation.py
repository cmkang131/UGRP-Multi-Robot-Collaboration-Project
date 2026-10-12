"""Opt-in validated wall output on the frozen robust own-map memory."""
from harness.self_wall_memory_robust import SelfWallMemory as Previous
from harness.self_wall_validation import OPTION, validated_grid
from harness.self_odom_grid import OdomGrid


class SelfWallMemory(Previous):
    def __init__(self,*args,wall_validation='off',**kwargs):
        if wall_validation not in ('off',OPTION):raise ValueError('UNKNOWN_WALL_VALIDATION')
        super().__init__(*args,**kwargs)
        if wall_validation!='off' and not hasattr(self.self_map,'ledger'):
            raise ValueError('WALL_VALIDATION_REQUIRES_POSE_LEDGER')
        self.wall_validation=wall_validation

    def validated_map(self):
        grid=self._graph_view if self._graph_view is not None else self.self_map
        if grid is None:return None,None
        if self.wall_validation=='off':return grid.export(),None
        rows=self.pose_graph_result['ledger'] if self.pose_graph_result else self.self_map.ledger
        return validated_grid(grid.export(),[dict(r,robot_id=self.robot_id) for r in rows],
            robot_id=self.robot_id,wall_validation=self.wall_validation)

    def snapshot(self):
        result=super().snapshot()
        if self.wall_validation!='off':
            grid,support=self.validated_map()
            view=OdomGrid(self.robot_id,resolution_m=grid['resolution_m'],
                text_top_k=self.self_map.text_top_k,text_max_tokens=self.self_map.text_max_tokens)
            view.cells={tuple(c[:2]):c[2] for c in grid['cells']}
            result['self_map_text']=view.text()
            result['self_map_validated']=grid
            result['self_map_support']=support
        return result
