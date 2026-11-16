"""Use frozen egomap22 metrics, explicitly distinguish frontend fallback."""
from pathlib import Path
import importlib.util,json
ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('egomap22_metrics',ROOT/'experiments/2026-10-07-active-wall-map/code/score.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.RAW=Path('/Users/changmin/projects/ugrp/outputs/rbpf-motion-gate-v1')
m.EXP=Path(__file__).resolve().parents[1]
def prediction(case,partial=False):
 ep=m.RAW/case;m.verify(ep);return ep
m.prediction=prediction
result=json.loads((m.RAW/'baseline/result.json').read_text())
m.evaluate('baseline',partial=result['prediction_view']!='completed_graph')
