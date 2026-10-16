"""Offline PNG-only color/ORB/repetition audit. No scene build or renderer."""
from __future__ import annotations
import argparse
import ast
import hashlib
import importlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image

from sim.natural_scene_texture import ASSETS, manifest, checked_file

ROOT = Path(__file__).resolve().parents[1]


def literal(node, env):
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, (ast.Tuple, ast.List)):
        return [literal(n, env) for n in node.elts]
    if isinstance(node, ast.Dict):
        return {literal(k, env): literal(v, env) for k,v in zip(node.keys,node.values)}
    if isinstance(node, ast.Subscript):
        return literal(node.value, env)[literal(node.slice, env)]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('array', 'asarray'):
        return literal(node.args[0], env)
    return ast.literal_eval(node)


def color_ranges():
    rows, inventory = [], []
    def add(label, source, ranges):
        rows.append({'label': label, 'source': source, 'ranges': ranges})
    # Read literal range definitions/calls without executing detector modules.
    # Unresolved dynamic expressions are retained in the inventory, with the
    # relevant frame-relative detectors explicitly bounded below.
    for folder in ('harness', 'sim', 'scripts'):
        for path in sorted((ROOT/folder).rglob('*.py')):
            if path.name in ('audit_scene_textures.py', 'generate_scene_textures.py'):
                continue
            source = path.read_text()
            if not any(word in source for word in ('HSV', 'hsv', 'inRange')):
                continue
            tree, env, calls = ast.parse(source), {}, []
            nodes = sorted(ast.walk(tree), key=lambda n: getattr(n, 'lineno', 0))
            for node in nodes:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    target = node.targets[0] if isinstance(node, ast.Assign) else node.target
                    if isinstance(target, ast.Name):
                        try: env[target.id] = literal(node.value, env)
                        except (ValueError, KeyError, TypeError, IndexError): pass
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'inRange':
                    loc = f'{path.relative_to(ROOT)}:{node.lineno}'
                    try:
                        lo, hi = literal(node.args[1], env), literal(node.args[2], env)
                        assert len(lo) == len(hi) == 3 and all(isinstance(v, (int,float)) for v in lo+hi)
                        # Only HSV calls (some helpers accept unrelated arrays).
                        if 'hsv' in ast.unparse(node.args[0]).lower():
                            add('literal:'+loc, loc, [(lo,hi)])
                            status = 'measured_literal'
                        else: status = 'non_hsv_or_indirect'
                    except (ValueError, KeyError, TypeError, IndexError, AssertionError):
                        status = 'dynamic_or_shared_definition'
                    calls.append({'line': node.lineno, 'expression': ast.unparse(node), 'classification': status})
            inventory.append({'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                              'inRange_calls': calls})
    for module, symbol in [('zone_color_boxes','OWN_HSV'),('zone_color_boxes','TOP_ZONE_HSV'),
                           ('zone_perception','HSV_RANGES'),('zone_cargo_perception','CARGO_HSV')]:
        values = getattr(importlib.import_module('harness.'+module),symbol)
        for key,ranges in values.items(): add(symbol+':'+key, f'harness/{module}.py:{symbol}',ranges)
    from harness import zone_color_boxes as boxes, zone_own_perception as own
    from harness import zone_own_perception_v2 as own2
    from harness import visual_navigation as nav
    from harness.opencv_wall_observation_robot_mask import ROBOT_MASK_CONFIG as robot
    add('own_zone:cyan','harness/zone_color_boxes.py:OWN_ZONE_CYAN_HSV',boxes.OWN_ZONE_CYAN_HSV)
    for k,v in own.APPEARANCE.items():
        add('adaptive_own:'+k,'harness/zone_own_perception.py:hue_mask',
            [((lo,own.ABS_MIN_SAT,own.ABS_MIN_VALUE),(hi,255,255)) for lo,hi in v['hue']])
    for k,v in own2.TEAM_MASK.items():
        add('adaptive_team:'+k,'harness/zone_own_perception_v2.py:team_mask',
            [((v['hue'][0],v['sat'][0],v['value'][0]),(v['hue'][1],v['sat'][1],v['value'][1]))])
    for k,v in nav._GOAL_HSV.items(): add('legacy_goal:'+k,'harness/visual_navigation.py:_GOAL_HSV',[v])
    add('robot_orange','harness/opencv_wall_observation_robot_mask.py:ROBOT_MASK_CONFIG',
        [(robot['hsv_lower'],robot['hsv_upper'])])
    add('floor_goal_B','harness/floor_goal.py:FloorGoalOptions',[((100,35,30),(130,255,255))])
    # Conservative superset of mapped paint bands (all H), static AMCL S window.
    add('AMCL_all_paint_hues','harness/zone_solo_cyan_landmarks.py:PARAMS',[((0,20,35),(179,150,255))])
    add('production_cyan','harness/markerless_box.py:_cyan_components',[((73,65,45),(104,255,245))])
    add('legacy_dark_bands','harness/owncam_pair_beam_v2.py:BAND_V_MAX/BAND_S_MAX',[((0,0,0),(179,89,60))])
    add('washed_white','harness/zone_cargo_perception.py:WHITE_HSV',[((0,0,225),(179,45,255))])
    # Open-PR definitions pinned as source snippets with whole-file sha256.
    pinned = json.loads((ROOT/'experiments/2026-10-15-scene-floor-texture/color_external_sources.json').read_text())
    for k,v in pinned['beam_ranges'].items(): add('beam_band:'+k,pinned['beam_source'],[v])
    return rows, inventory, pinned


def features(gray):
    kps, desc = cv2.ORB_create(nfeatures=800).detectAndCompute(gray, None)
    pts = np.array([k.pt for k in kps])
    repeated = 0
    if desc is not None and len(desc)>1:
        # Only spatially distant descriptors count as repetition, not the same
        # keypoint detected on two pyramid levels.
        distances, indices = cv2.batchDistance(desc,desc,cv2.CV_32S,normType=cv2.NORM_HAMMING,K=len(desc))
        far = np.linalg.norm(pts[:,None]-pts[indices],axis=2)>=64
        repeated = int(((distances<=24)&far).any(axis=1).sum())
    small = cv2.resize(gray,(512,512),interpolation=cv2.INTER_AREA).astype(float)
    high = small-cv2.GaussianBlur(small,(0,0),3)
    ncc=[]
    for axis in (0,1):
        for lag in (32,64,128,256):
            a,b = (high[:-lag,:],high[lag:,:]) if axis==0 else (high[:,:-lag],high[:,lag:])
            denom=float(np.linalg.norm(a)*np.linalg.norm(b))
            ncc.append(float(np.sum(a*b)/denom) if denom else 0.)
    patches=[gray[y:y+32,x:x+32].tobytes() for y in range(0,gray.shape[0]-31,32) for x in range(0,gray.shape[1]-31,32)]
    return {'orb_count':len(kps),'distant_hamming_le24_n':repeated,'descriptor_N':len(kps),
            'distant_repeat_fraction':repeated/len(kps) if kps else None,
            'highpass_ncc_lags_32_64_128_256_max':max(ncc),
            'duplicate_32px_patch_fraction':1-len(set(patches))/len(patches) if patches else None}


def audit():
    record=manifest(); ranges,inventory,pinned=color_ranges()
    values=np.arange(256,dtype=np.uint8)
    swatches=np.repeat(values[None,:,None],3,axis=2)
    hsv=cv2.cvtColor(swatches,cv2.COLOR_RGB2HSV)
    counts={'floor':np.zeros(256,np.int64),'walls':np.zeros(256,np.int64)}
    images=[]
    for key in record['images']:
        path=checked_file(key,record,ASSETS)
        rgb=np.asarray(Image.open(path).convert('RGB'))
        if not np.all(rgb[:,:,0]==rgb[:,:,1]) or not np.all(rgb[:,:,1]==rgb[:,:,2]):
            raise ValueError(f'non-neutral texture: {key}')
        gray=rgb[:,:,0]; kind='floor' if key=='floor' else 'walls'
        counts[kind]+=np.bincount(gray.reshape(-1),minlength=256)
        images.append({'key':key,'sha256':record['images'][key]['sha256'], 'pixels':gray.size,
                       'value_min':int(gray.min()),'value_max':int(gray.max()),**features(gray)})
    measured=[]
    for spec in ranges:
        mask=np.zeros((1,256),np.uint8)
        for lo,hi in spec['ranges']: mask |= cv2.inRange(hsv,np.asarray(lo,dtype=np.uint8),np.asarray(hi,dtype=np.uint8))
        measured.append({**spec,**{k:{'hits':int(hist[mask[0]>0].sum()),'N':int(hist.sum()),
                                       'fraction':float(hist[mask[0]>0].sum()/hist.sum())} for k,hist in counts.items()}})
    # crate_rgb_lift uses RGB inequalities, not HSV; keep that distinction.
    r=g=b=values.astype(np.int16)
    rgb_masks={'crate_blue':(b>140)&(r<90)&(g<90),
               'crate_teal':(g>140)&(b>60)&(b<g)&(r<90),
               'crate_pink':(r>90)&(r>g+25)&(b>g-5)&(r>b)}
    for name,mask in rgb_masks.items():
        measured.append({'label':name,'source':pinned['crate_source'],'RGB_expression':pinned['crate_expressions'][name],
                         **{k:{'hits':int(hist[mask].sum()),'N':int(hist.sum()),'fraction':float(hist[mask].sum()/hist.sum())} for k,hist in counts.items()}})
    yy,xx=np.indices((512,512)); checker=np.where((xx//32+yy//32)%2,158,92).astype(np.uint8)
    floor=np.asarray(Image.open(ASSETS/'floor.png'))[:,:,0]
    return {'schema':'ugrp.scene_texture_offline_audit.v1','scope':'PNG pixels only; no camera, simulator, renderer or remote execution',
            'environment':{'python':sys.version.split()[0],'opencv':cv2.__version__,'numpy':np.__version__},
            'color_ranges':measured,'source_inventory':inventory,'images':images,
            'floor_640x480_native_crops':[features(floor[y:y+480,x:x+640]) for x,y in ((128,128),(1152,128),(128,1152),(1152,1152))],
            'controls':{'flat':features(np.full((512,512),146,np.uint8)), 'synthetic_checker_32px':features(checker)},
            'camera_verified':False,'ready_for_execution':False}


def write_audit(result, path):
    """Keep each JSON below 64 KiB; detailed range/source tables are Markdown."""
    path = Path(path)
    images = result.pop('images')
    image_path = path.with_name('image-metrics.json')
    image_path.write_text(json.dumps(images, separators=(',', ':'))+'\n')
    inventory = result.pop('source_inventory')
    lines = ['# 색 검출 코드 탐색 목록', '',
             '현재 main 기반 harness/sim/scripts의 HSV·hsv·inRange 소스를 전수 검색했다. ',
             '동적 범위·형상·주변 대비 조건은 단순 픽셀 범위와 구분한다. ',
             '상자/화물 적응형 하한, 지도 페인트 전체 hue 상위집합, 외부 PR 끝 띠/손잡이는 별도 측정표에 포함한다.', '']
    for entry in inventory:
        lines += [f"## {entry['path']}", '', f"SHA256 `{entry['sha256']}`", '']
        for call in entry['inRange_calls']:
            lines.append(f"- L{call['line']} {call['classification']}: `{call['expression']}`")
        lines.append('')
    path.with_name('color-source-inventory.md').write_text('\n'.join(line.rstrip() for line in lines).rstrip()+'\n')
    result['image_metrics'] = {'path': image_path.name, 'sha256': hashlib.sha256(image_path.read_bytes()).hexdigest()}
    path.write_text(json.dumps(result, indent=2)+'\n')
    lines = ['# 색 범위 침범률 (PNG 원본)', '',
             'OpenCV HSV: H 0–179, S/V 0–255. 적응형 범위는 가장 느슨한 절대 하한으로 검사. ',
             '81개 측정 범위에 대해 바닥 9,437,184 픽셀·벽 39,321,600 픽셀 전체를 집계. ',
             '무채색 256종의 빈도와 실제 cv2.inRange 결과를 곱해 계산했다. 조명/JPEG/주변 대비 검증은 미실행.', '',
             '| 검출 범위 | 코드 근거 | HSV 범위 또는 RGB 식 | 바닥 침범 n/N (%) | 벽 침범 n/N (%) |',
             '|---|---|---|---|---|']
    for r in result['color_ranges']:
        ranges = r.get('ranges', r.get('RGB_expression'))
        lines.append(f"| {r['label']} | {r['source']} | `{ranges}` | {r['floor']['hits']}/{r['floor']['N']} ({100*r['floor']['fraction']:.4f}%) | {r['walls']['hits']}/{r['walls']['N']} ({100*r['walls']['fraction']:.4f}%) |")
    path.with_name('color-ranges.md').write_text('\n'.join(line.rstrip() for line in lines).rstrip()+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); result=audit()
    print(json.dumps({'images':len(result['images']),'ranges':len(result['color_ranges']),
                      'max_hit_fraction':max(r[k]['fraction'] for r in result['color_ranges'] for k in ('floor','walls')),
                      'floor':result['images'][0], 'crops':[r['orb_count'] for r in result['floor_640x480_native_crops']]}))
    write_audit(result,args.output)
