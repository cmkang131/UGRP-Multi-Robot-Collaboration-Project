"""Opt-in offline robust graph / evidence view, preserving the frozen frontend."""
import copy

from harness.self_wall_memory_motion import SelfWallMemory as Previous
from harness.self_loop_rejection import VALUES as LOOP_VALUES, refine_cached_graph
from harness.self_wall_evidence import VALUES as EVIDENCE_VALUES, build_evidence
from harness.self_pose_graph import rebuild


class SelfWallMemory(Previous):
    def __init__(self, *args, loop_rejection='off', wall_evidence='off', **kwargs):
        if loop_rejection not in LOOP_VALUES or wall_evidence not in EVIDENCE_VALUES:
            raise ValueError('UNKNOWN_ROBUST_MAP_OPTION')
        if (loop_rejection != 'off' or wall_evidence != 'off') and kwargs.get('pose_graph') != 'own_submap_v1':
            raise ValueError('ROBUST_MEMORY_REQUIRES_OWN_SUBMAP')
        super().__init__(*args, **kwargs)
        self.loop_rejection, self.wall_evidence = loop_rejection, wall_evidence
        self.evidence_view = None

    def command(self, row):
        super().command(row)
        self.evidence_view = None

    def observe_wall(self, *args, **kwargs):
        result = super().observe_wall(*args, **kwargs)
        self.evidence_view = None
        return result

    def finalize_pose_graph(self, poses=None):
        if self.loop_rejection == self.wall_evidence == 'off':
            return super().finalize_pose_graph(poses)
        rows = [{**copy.deepcopy(r), 'robot_id':self.robot_id} for r in self.self_map.ledger]
        if poses is None:
            poses = [dict(robot_id=self.robot_id, t=r['t'], pose=r['pose']) for r in rows]
        legacy = super().finalize_pose_graph(poses)
        ledger, path, diagnostics = refine_cached_graph(rows, poses,
            (legacy['ledger'], legacy['poses'], legacy['diagnostics']), robot_id=self.robot_id,
            loop_rejection=self.loop_rejection)
        self._graph_view = rebuild(self.robot_id, ledger)
        if path:
            self._graph_view.odom._predictor.px[0] = path[-1]['pose']
        self.evidence_view = build_evidence(ledger, robot_id=self.robot_id, wall_evidence=self.wall_evidence)
        self.pose_graph_result = dict(ledger=ledger, poses=path, diagnostics=diagnostics)
        if self.evidence_view is not None:
            self.pose_graph_result['wall_evidence'] = self.evidence_view
        return self.pose_graph_result
