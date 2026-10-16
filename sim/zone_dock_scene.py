"""Dock-only successor of the frozen tagged cargo Scene; old sources untouched."""
from __future__ import annotations

import copy

from sim.research_dispatch_arena import digest
from sim.zone_arena import MAP_DIR
from sim.zone_start_dock import MAP_ID, PARENT_MAP_ID, apply_spawn_layout, dock_map
from sim.zone_tagged_cargo_scene import TaggedCargoZoneScene


class DockTaggedCargoZoneScene(TaggedCargoZoneScene):
    """Resolve the unchanged parent, then apply one versioned setup-only translation."""

    def _resolve(self):
        if self.selection != 'zones/' + MAP_ID:
            raise ValueError('dock scene requires its versioned selection ID')
        selected = self.selection
        try:
            self.selection = 'zones/' + PARENT_MAP_ID
            super()._resolve()
        finally:
            self.selection = selected
        self._read(MAP_DIR / (MAP_ID + '.json'))
        static = dock_map()
        self.config.update(static_map=static, static_map_sha256=digest(static), tagged_map_id=MAP_ID)
        apply_spawn_layout(self.config)

    def transform(self, xml):
        xml = super().transform(xml)
        self.manifest['start_dock'] = copy.deepcopy(self.config['static_map']['start_dock'])
        return xml
