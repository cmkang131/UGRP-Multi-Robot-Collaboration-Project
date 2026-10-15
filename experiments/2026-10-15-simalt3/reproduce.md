# 재현 경계와 실제 명령

이 문서는 실행 기록이며 새 VM 시작/배치를 자동 제출하지 않는다. Mac 물리·렌더 금지, gcp1/첫 프로젝트 사용 금지다. 같은 gcp2 L4에서 시작할 때도 비용 정지 장치·8h STOP·idle20분·3h 자원 상한과 소스 SHA를 먼저 확인한다.

원래 영속 입력은 `/home/ugrp/ugrp-sim/runs/simalt3`다. 소스는 동결 교사6f057f7e의 sim/harness/scripts/configs/maps만 `git archive`한 것이며 가중치·에이전트/모델/Kaggle 자격 증명은 없다. fixture는 scene.xml SHA`ad46cd87ef4188daa9a4dbebd79c470fac6f1b3fcb5e5a1fe0d9dfa3c2261849`, fixture.npz SHA`d3548742053aa18ee526297baa2611bb37b32f923b504097dc5a0c17f4184577`이다.

원본에서64KiB 초과 JSON/JSONL21개는 lossless zstd로 보존했다. compression-map.json의 original→stored 매핑과 전체 복원 SHA를 따른다. 기존 파일을 덮지 않고 별도 새 폴더로 복원한다. 예를 들어 명령 trace는 `zstd -dc "$ORIG/trace.jsonl.zst" > "$NEW/trace.jsonl"`이다. SHA256SUMS는 현재 저장 표현의 해시이며, uncompressed SHA는 compression-map에 있다.

먼저 Mac Git에서 해당 진단 커밋의 스크립트를 추출해 새 VM 하위 폴더에 전송한다. 다음 파일을 모두 같은 scripts 디렉터리에 두어 상대 import를 보존한다: simalt_physics_compare.py, simalt_numeric_audit.py, simalt_host.py, simalt_pilot.py, simalt_analyze_physics.py, simalt_review_physics.py. `git archive <SHA> scripts/<각 파일>`로 실제 해당 커밋을 추출하며, 현재 diag를 과거 SHA로 표시하지 않는다. 교사 source archive는 별도로6f057f7e다.

실제 사용한 명령을 새 out 폴더로 재현하는 예시(원래 C/warp 환경과 원래 source/fixture가 존재하는 같은 호스트):

```bash
ORIG=/home/ugrp/ugrp-sim/runs/simalt3
NEW=/home/ugrp/ugrp-sim/runs/simalt3-repro-NEW
SOURCE="$ORIG/runtime/source"
# DIAG25/DIAG737/DIAG01 = 각 Git 커밋을 추출한 scripts 디렉터리
mkdir -p "$NEW"
export MUJOCO_GL=osmesa LP_NUM_THREADS=1

# 최초 fixture 생성(25bf9995). 원래 source/plan은 그대로, trace만 lossless 복원.
zstd -dc "$ORIG/trace.jsonl.zst" > "$NEW/trace.jsonl"
"$ORIG/c-env/bin/python" "$DIAG25/simalt_physics_compare.py" prepare \
  --source "$SOURCE" --plan "$ORIG/plan.json" --trace "$NEW/trace.jsonl" \
  --out "$NEW/fixture" --sha 25bf9995 --enabled --gcp2-v1

# 원래 고정 fixture로 C 기준과 Warp 동등성 비교
"$ORIG/c-env/bin/python" "$DIAG25/simalt_physics_compare.py" run \
  --source "$SOURCE" --fixture "$ORIG/fixture" --out "$NEW/cpu-n1" \
  --engine cpu --sha 25bf9995 --enabled --gcp2-v1
"$ORIG/warp-env/bin/python" "$DIAG25/simalt_physics_compare.py" run \
  --source "$SOURCE" --fixture "$ORIG/fixture" --out "$NEW/warp-n1" \
  --engine warp --reference "$NEW/cpu-n1/result.json" --sha 25bf9995 \
  --enabled --gcp2-v1 --unused-efm-v1

# C3.16 추가 대조: warp-env의 C engine, Warp step은 호출하지 않음
"$ORIG/warp-env/bin/python" "$DIAG737/simalt_physics_compare.py" run \
  --source "$SOURCE" --fixture "$ORIG/fixture" --out "$NEW/cpu316-n1" \
  --engine cpu --sha 737f5a0e --enabled --gcp2-v1

# throughput 각 N=16,64,128,256: physics source737f5a0e
"$ORIG/warp-env/bin/python" "$DIAG737/simalt_physics_compare.py" run \
  --source "$SOURCE" --fixture "$ORIG/fixture" --out "$NEW/warp-n64-forward" \
  --engine warp --reference "$NEW/cpu-n1/result.json" --sha 737f5a0e \
  --enabled --gcp2-v1 --unused-efm-v1 --only forward --nworld 64

# RGB 각 N=1,16,64,128,256: source01cd2a9c
"$ORIG/warp-env/bin/python" "$DIAG01/simalt_physics_compare.py" run \
  --source "$SOURCE" --fixture "$ORIG/fixture" --out "$NEW/warp-n64-forward-rgb" \
  --engine warp --reference "$NEW/cpu-n1/result.json" --sha 01cd2a9c \
  --enabled --gcp2-v1 --unused-efm-v1 --only forward --nworld 64 --batch-render-v1

# evaluator 전용: 물리 진행 없음
"$ORIG/c-env/bin/python" "$DIAG25/simalt_analyze_physics.py" \
  --fixture "$ORIG/fixture" --reference "$NEW/cpu-n1" --candidate "$NEW/warp-n1" \
  --out "$NEW/comparison.json" --asset-source "$SOURCE" --gcp2-v1
"$ORIG/c-env/bin/python" "$DIAG737/simalt_review_physics.py" \
  --source "$SOURCE" --fixture "$ORIG/fixture" --run "$NEW/warp-n1" \
  --out "$NEW/review-warp-grip" --case grip --gcp2-v1 --failure-time-s 25.1
```

N1 물리 표는 전체4구간의 forward 구간을 사용했다. 다른 N은 forward4초만 재생한다. N1 전체의1096.010초를 forward cold wall로 오인하지 않는다. 물리 N1 cold 값은 전체 suite의 설치/컴파일 이후 실행 창이며, 나머지 N cold는 해당4초 실행이다. 비교용 주 처리량은 구간 physics timer와 RGB timer다. 명령 tape 일치와 qpos/qvel 유한성을 확인했으나 모드/N 간 상태 비트 일치나 독립 seed 성공률을 검증한 것은 아니다.

[run-batch.sh](run-batch.sh)는 원래 고정 root를 쓰는 짧은 실행 기록이다. 다른 out 디렉터리가 필요하면 위의 명시적인 `--out` 명령을 사용한다. 각 실행 원장·최종 수집/압축/해시 검증은 [collect-results.py](collect-results.py)와 evidence/measurements.json에 있다. 수집 스크립트는 모든 측정이 끝난 뒤에만 실행한다.
