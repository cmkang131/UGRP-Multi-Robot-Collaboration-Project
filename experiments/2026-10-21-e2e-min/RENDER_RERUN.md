# carry_pose_render 재실행 명령 (POSE_SCENE_XML_NOT_IDENTICAL 수정 후)

대상 브랜치: `dsh/e2e-min-render-fix`. 판정 규칙과 인자는 `CARRY_POSE_RENDER_DRAFT.md` §3·§4와 같고, 바뀐 것은 장면 구성뿐입니다.

## 무엇이 바뀌었나
- 이전 실패 원인: 큐브 setup xy(x+0.2)가 `sim/zone_arena.py:426`에서 cargo body `pos`로 XML에 기록됨 → x(1.5/2.0/2.8/3.5)마다 XML이 달라짐 → `carry_pose_render.py`의 동일성 검사(이전 115-117행)에서 실패.
- 수정: 모든 world를 같은 setup 큐브 xy(`SETUP_CUBE_X=1.7`, 레인 y)로 빌드합니다. 로봇 spawn·팔 자세·큐브 위치(on: 손가락 중점, off: (x+0.2, 레인 y, −0.5))는 컴파일 뒤 qpos/ctrl로만 넣습니다. 그래서 한 자세 배치 안의 XML은 바이트 단위로 같아야 합니다.
- 동일성 검사는 그대로 남아 있습니다. `measure.json.scene_identity[<pose>]`에 `raw_sha256`, `normalized_sha256`, `normalized_fields`, `differing_fields`가 기록됩니다. 정상이면 `raw_identical=true`, `differing_fields=[]`입니다.

## 명령 (gcp6 또는 gcp2의 L4, nav `.venv-warp`)
```bash
BR=dsh/e2e-min-render-fix
SHA=$(git ls-remote https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project.git refs/heads/$BR | cut -f1)
SRC=/home/ugrp/ugrp-sim/src/e2e-min-render-fix-${SHA:0:8}
git clone --branch $BR https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project.git $SRC   # [확인 필요] VM의 clone 방식/인증(기존 관례가 있으면 그쪽을 따름)
cd $SRC && test "$(git rev-parse HEAD)" = "$SHA" && test -z "$(git status --porcelain)" && echo CLEAN_OK
TS=$(date -u +%Y%m%dT%H%MZ)
OUT=/home/ugrp/ugrp-sim/runs/e2e-min-carry-pose-render-$TS
/home/ugrp/ugrp-sim/ugrp/.venv-warp/bin/python experiments/2026-10-21-e2e-min/carry_pose_render.py \
  --out $OUT --expected-source-sha $SHA
jq '.verdict' $OUT/measure.json
jq '.scene_identity | map_values({raw_identical, identical, raw_sha256, normalized_sha256, differing_fields})' $OUT/measure.json
sha256sum $OUT/measure.json $OUT/frames/*.jpg > $OUT/SHA256SUMS
```
- 반드시 clone 루트에서 실행합니다(`CWD_MUST_BE_CLONE_ROOT`). `--out`은 새 디렉터리여야 합니다(`OUTPUT_EXISTS`).
- [확인 필요] venv 경로: `/home/ugrp/ugrp-sim/ugrp/.venv-warp`는 gcp6 기준입니다. gcp2에서 돌린다면 gcp2의 nav venv 경로를 확인해야 합니다.

## 실패 시 보고할 것
- `POSE_SCENE_XML_NOT_IDENTICAL:<pose>`: 정규화(free-joint body `pos`만 제거) 뒤에도 XML이 다릅니다. 즉 다른 장면입니다. `$OUT/scene-identity-<pose>.json` 전체를 보고합니다.
- `POSE_SCENE_XML_RAW_DIFFERS_POSE_ONLY:<pose>:<fields>`: 자세/spawn 필드만 다르지만 `transport()`가 배치당 바이트 동일 모델을 요구해서 멈춘 경우입니다. 같은 파일과 필드 목록을 보고합니다(이번 수정 뒤에는 나오지 않아야 합니다).
- `transport()`의 `one exact scene model per batch required`(ValueError): 위 검사를 통과했다면 나오면 안 됩니다. 나오면 traceback 전체를 보고합니다.
