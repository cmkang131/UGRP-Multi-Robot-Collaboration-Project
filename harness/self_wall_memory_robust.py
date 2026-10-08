"""Opt-in offline robust graph / evidence view, preserving the frozen frontend."""
import copy

from harness.self_wall_memory_motion import SelfWallMemory as Previous
from harness.self_loop_rejection import VALUES as LOOP_VALUES, refine_cached_graph
from harness.self_wall_evidence import VALUES as EVIDENCE_VALUES, build_evidence
from harness.self_pose_graph import rebuild


class SelfWallMemory(Previous):
    def __init__(self, *args, loop_rejection='off', wall_evidence='off', wall_export='off', map_update='off', graph_acceleration='off', **kwargs):
        if wall_export not in ('off', 'segments_confidence_v1'):
            raise ValueError('UNKNOWN_WALL_EXPORT')
        if loop_rejection not in LOOP_VALUES or wall_evidence not in EVIDENCE_VALUES:
            raise ValueError('UNKNOWN_ROBUST_MAP_OPTION')
        if (loop_rejection != 'off' or wall_evidence != 'off') and kwargs.get('pose_graph') != 'own_submap_v1':
            raise ValueError('ROBUST_MEMORY_REQUIRES_OWN_SUBMAP')
        super().__init__(*args, **kwargs)
        self.loop_rejection, self.wall_evidence = loop_rejection, wall_evidence
        self.evidence_view = None
        if wall_export != 'off' and not hasattr(self.self_map, 'ledger'):
            raise ValueError('WALL_EXPORT_REQUIRES_OWN_POSE_LEDGER')
        self.wall_export = wall_export
        self._export_observations = {}
        from harness.self_camera_grid import install
        install(self.self_map, map_update=map_update)
        self.map_update = map_update
        from harness.self_graph_cache import install as install_graph_cache
        install_graph_cache(self,graph_acceleration=graph_acceleration)

    def command(self, row):
        super().command(row)
        self.evidence_view = None

    def observe_wall(self, *args, observation_id=None, frame_sha256=None, **kwargs):
        result = super().observe_wall(*args, **kwargs)
        self.evidence_view = None
        if self.wall_export != 'off':
            record = args[0] if args else kwargs['record']
            fid = record['view_index']
            self._export_observations[fid] = dict(robot_id=self.robot_id,
                obs_id=observation_id or f'{self.robot_id}-obs-{fid:06d}', frame_sha256=frame_sha256,
                pose_covariance=self.self_map.odom.covariance.tolist())
        return result

    def export_wall_memory(self):
        if self.wall_export == 'off':
            return None
        from harness.self_wall_export import export_walls
        view = self._graph_view if self._graph_view is not None else self.self_map
        rows = self.pose_graph_result['ledger'] if self.pose_graph_result else self.self_map.ledger
        if self.map_update != 'off':
            view = self.self_map.camera_map
            rows = view.ledger
        return export_walls(view.export(), [dict(r, robot_id=self.robot_id) for r in rows],
            robot_id=self.robot_id, wall_export=self.wall_export, observations=self._export_observations,
            pose_covariance=self.self_map.odom.covariance, now=self.self_map.odom.t)

    def snapshot(self):
        result = super().snapshot()
        if self.map_update != 'off':
            result['self_map_text'] = self.self_map.camera_map.text().replace(
                'drift uncorrected', 'online own pose; independent camera integration')
        if self.wall_export != 'off':
            from harness.self_wall_export import memory_text
            exported = self.export_wall_memory()
            result['self_wall_export_text'] = memory_text(exported)
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
