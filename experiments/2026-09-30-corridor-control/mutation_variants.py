"""Targeted in-memory mutations; never edit production or sealed source files."""
import hashlib
import importlib
from pathlib import Path

VARIANTS = {
    'remove_control': ('harness.zone_corridor_control',
                       '        p, now = self.plan, self.last_now\n',
                       '        return self._hold()  # MUTATION: remove all decisions\n',
                       'test_solo_entry_translation_full_exit_not_waypoint_or_delivery'),
    'remove_yield': ('harness.zone_corridor_control',
                     '                self._choose_yield(view)\n',
                     "                self._begin_wait('FOLLOW')  # MUTATION\n",
                     'test_capable_solo_decides_to_yield_then_reenters_on_own_clear_frames'),
    'remove_heartbeat': ('harness.zone_corridor_control',
                         "        if not self.bus.partner_view(self.robot_id, self.last_now)[peer]['alive']:\n",
                         '        if False:  # MUTATION: no heartbeat expiry\n',
                         'test_heartbeat_boundary_uses_actual_delivery_not_private_partner_state'),
    'remove_wait_timeout': ('harness.zone_corridor_control',
                            '            if now - self.wait_started >= self.config.wait_timeout_s:\n',
                            '            if False:  # MUTATION: unbounded wait\n',
                            'test_wait_timeout_boundary'),
    'remove_exit_check': ('harness.zone_corridor_control',
                          ' or not self._full_exit(view.reference_pose)', '',
                          'test_waypoint_proximity_cannot_override_full_exit'),
    'remove_route_refusal': ('harness.zone_corridor_control_plan',
                             "        if result['static_ok'] is not True:\n",
                             '        if False:  # MUTATION: accept blocked route\n',
                             'test_impossible_and_disconnected_routes_refused'),
}


def install(name):
    module_name, old, new, test = VARIANTS[name]
    module = importlib.import_module(module_name)
    path = Path(module.__file__)
    original = path.read_text()
    if original.count(old) != 1:
        raise ValueError('mutation anchor must match once: ' + name)
    mutated = original.replace(old, new, 1)
    exec(compile(mutated, str(path), 'exec'), module.__dict__)
    return {'name': name, 'module': module_name, 'selected_test': test,
            'original_sha256': hashlib.sha256(original.encode()).hexdigest(),
            'mutated_in_memory_sha256': hashlib.sha256(mutated.encode()).hexdigest(),
            'file_bytes_unchanged': path.read_text() == original}
