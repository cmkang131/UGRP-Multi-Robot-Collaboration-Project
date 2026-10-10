"""Evaluation-only reuse of pinned PR406 functions; no Runtime/worker created.

Only the explicitly named function ASTs are executed, unchanged, avoiding the
unrelated controller imports/side effects in the complete archived sources.
"""
import ast
import copy
import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace as NS

import numpy as np
from harness.zone_final_pair_camera import floor_camera
from harness.vision_pose_source_final import CalibrationError
from harness.zone_final_pair_contract import camera_record
from sim.masterpi_camera_profile import scaled_camera_matrix, CAMERA_FISHEYE_D

EXP = Path(__file__).resolve().parents[1]
ROOT = EXP.parents[1]
MANIFEST = json.loads((EXP/'sources.json').read_text())


def verify_sources():
    for source, row in MANIFEST['files'].items():
        assert hashlib.sha256((EXP/row['copy']).read_bytes()).hexdigest() == row['sha256']
        # Imported geometry helpers must be byte-identical to the pinned source.
        if source in ('harness/zone_final_pair_camera.py', 'harness/vision_pose_source_final.py',
                      'harness/zone_final_pair_contract.py'):
            assert (ROOT/source).read_bytes() == (EXP/row['copy']).read_bytes()


def function(filename, name, namespace):
    path = EXP/'sources'/filename
    tree = ast.parse(path.read_text())
    nodes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name]
    assert len(nodes) == 1
    # Neither literal replacement nor rewriting of a function body is allowed.
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


def models():
    verify_sources()
    env = dict(copy=copy, np=np, floor_camera=floor_camera,
               scaled_camera_matrix=scaled_camera_matrix, CAMERA_FISHEYE_D=CAMERA_FISHEYE_D)
    # Both assignments and the function body are the source AST, not new constants.
    tree = ast.parse((EXP/'sources/zone_solo_cyan_real_carry_dev.py').read_text())
    constants = [n for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id in ('OPTION', 'SAG_DELTA_RAD') for t in n.targets)]
    exec(compile(ast.Module(body=constants, type_ignores=[]), '<s2 constants>', 'exec'), env)
    table = json.loads((EXP/'sources/s2_camera_v3_unloaded_sag_v1.json').read_text())
    return table, function('zone_solo_cyan_real_carry_dev.py', 'approximate', env)(table)


def column_model_factory(mp, columns, *, loaded=False):
    table, value = models()
    measured = function('vision_pose_source_final.py', 'measured_column_model',
                        dict(np=np, CalibrationError=CalibrationError))
    pan = function('vision_loc.py', 'pan_yaw', dict(Mapping=Mapping))
    env = dict(np=np, math=math, pf=NS(load=NS(loaded=loaded), columns=columns),
               contract=NS(camera_record=camera_record), vl=NS(mp=mp, pan_yaw=pan),
               cal=dict(camera_models=value, pan_base_yaw=table['pan_base_yaw']),
               measured_column_model=measured)
    return function('vision_pose_source_highpose.py', 'column_model_for', env)
