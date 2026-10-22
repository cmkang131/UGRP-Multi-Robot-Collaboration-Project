"""pairact-r1 v7 XML 의존집합 대조 (CPU, 로드만, mj_step 없음).

사용: python scripts/pairact_r1_xml_load_check.py REPO_ROOT SCENE_XML > result.json
harness.pairact_collect.xml_dependencies(base=REPO_ROOT)가 MuJoCo from_xml_string(cwd=REPO_ROOT)이
실제로 여는 파일 집합과 같은지 대조한다: 의존집합만 임시 디렉터리에 복사해 로드(⊇), 하나씩 빼서 로드(⊆).
/home/ugrp/ 절대경로 의존은 REPO_ROOT/sim/ 아래 같은 꼬리 경로 사본으로 치환한다(VM에서는 원본이 그대로 쓰임).
로컬에 없는 의존 파일은 8x8 PNG 자리표시자로 채운 결과를 따로 보고한다. 원본 결과: V7_1B_NOTES.md.
"""
import json, os, shutil, sys, tempfile, time
import mujoco
repo, xml = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo)
from harness import pairact_collect as pc
t0 = time.time()
text = open(xml).read()
deps = sorted(pc.xml_dependencies(xml, base=repo))
res = dict(xml=os.path.relpath(xml, repo), mujoco=mujoco.__version__, n_deps=len(deps))
def load(cwd, txt):
    old = os.getcwd(); os.chdir(cwd)
    try:
        mujoco.MjModel.from_xml_string(txt); return 'ok'
    except Exception as e:
        return f'fail: {str(e).splitlines()[0][:160]}'
    finally:
        os.chdir(old)
res['load_as_is_cwd_repo'] = load(repo, text)
res['load_as_is_cwd_xmldir'] = load(os.path.dirname(xml), text)
vm = [p for p in deps if p.startswith('/home/ugrp/')]
local = [p for p in deps if not p.startswith('/home/ugrp/')]
res['vm_only_deps'] = vm
res['missing_local'] = [p for p in local if not os.path.isfile(p)]
# mirror: only the dependency set, VM-absolute paths replaced by a repo copy with the same relative tail
subst = {}
for p in vm:
    tail = p.split('/sim/', 1)[1] if '/sim/' in p else None
    cand = os.path.join(repo, 'sim', tail) if tail else None
    subst[p] = cand if cand and os.path.isfile(cand) else None
res['vm_substitutes'] = {k: (os.path.relpath(v, repo) if v else None) for k, v in subst.items()}
mirror = tempfile.mkdtemp(prefix='v7-mj-mirror-')
txt2 = text
for p, c in subst.items():
    if c:
        dst = os.path.join(mirror, '_vm', os.path.basename(c)); os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(c, dst); txt2 = txt2.replace(p, dst)
for p in local:
    if os.path.isfile(p):
        dst = os.path.join(mirror, os.path.relpath(p, repo)); os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy(p, dst)
import struct, zlib
def png(path, n=8):
    raw = b''.join(b'\x00' + b'\x80\x80\x80' * n for _ in range(n))
    ch = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    open(path, 'wb').write(b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', n, n, 8, 2, 0, 0, 0))
                           + ch(b'IDAT', zlib.compress(raw)) + ch(b'IEND', b''))
res['mirror_without_placeholders'] = load(mirror, txt2)
for p in res['missing_local']:
    dst = os.path.join(mirror, os.path.relpath(p, repo)); os.makedirs(os.path.dirname(dst), exist_ok=True); png(dst)
res['placeholder_png_for_missing'] = len(res['missing_local'])
res['mirror_full'] = load(mirror, txt2)
extra = os.path.join(mirror, 'sim/assets/_unreferenced_probe.png'); png(extra)
drops = {}
for p in local + [os.path.join(repo, 'sim/assets/_unreferenced_probe.png')]:
    if time.time() - t0 > 540: drops['_timeout'] = True; break
    dst = os.path.join(mirror, os.path.relpath(p, repo))
    if not os.path.isfile(dst): continue
    tmp = dst + '.away'; os.rename(dst, tmp)
    drops[os.path.relpath(p, repo)] = load(mirror, txt2).split(':')[0]
    os.rename(tmp, dst)
res['drop_one'] = drops
res['drop_one_all_fail'] = all(v == 'fail' for k, v in drops.items() if not k.startswith('_'))
res['seconds'] = round(time.time() - t0, 1)
shutil.rmtree(mirror)
print(json.dumps(res, indent=1, ensure_ascii=False))
