"""B1 checkpoint-sweep renders (same poses, arm equilibrium, pans, labels as B1) under a synthetic floor/light/wall look (sim env).

usage: python render_b1_look.py <out_dir> <look name from render_static_set.all_looks()>
Writes the B1 render layout (render_manifest.json, frames/, eval_only/labels/); render_manifest['render_profile'] = look name.
"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import render_static_set as rs  # noqa: E402  (adds B1 to sys.path)
import render_checkpoints as rc  # noqa: E402

out, name = sys.argv[1], sys.argv[2]
look = rs.all_looks()[name]
rc.build_world = lambda profile: rs.build_world_look(look)
rc.main([out, '--profile', 'floor_light_v1'])
mp = Path(out) / 'render_manifest.json'
m = json.loads(mp.read_text())
m['render_profile'] = name
m['look'] = look
mp.write_text(json.dumps(m, indent=1))
