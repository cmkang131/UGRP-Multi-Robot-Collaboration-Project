# 재현 경계와 명령

실행 기록이다. Mac에서 physics/render를 실행하지 않는다. 원본이 있는 gcp2 기존 L4를 별도로 승인된 사용 시간 안에서 재사용하며, 새 VM/첫 프로젝트를 쓰지 않는다. 현재 L4는 정지했다.

모든 gcloud 명령에는 `--account changmin5781@gmail.com --project ugrp-sim-b-1014`를 붙인다. zone은 `asia-northeast3-a`다. `gcloud compute instances describe ugrp-act-l4-gcp2 --zone asia-northeast3-a --account changmin5781@gmail.com --project ugrp-sim-b-1014`로 호스트·수명과 예산 상태를 먼저 확인한다.

원본 root는 `/home/ugrp/ugrp-sim/runs/simalt4`, 원래 fixture/source/환경은 옆 `simalt3`다. 아래 `NEW`는 존재하지 않는 새 폴더여야 하며 기존 결과를 덮어쓰지 않는다. 각 source는 Git의 해당 SHA에서 scripts를 추출해 전송한 사본이다. VM에는 GitHub/모델/Kaggle 자격 증명을 보내지 않는다.

```bash
ROOT=/home/ugrp/ugrp-sim/runs/simalt4
OLD=/home/ugrp/ugrp-sim/runs/simalt3
NEW=/home/ugrp/ugrp-sim/runs/simalt4-repro-NEW
export MUJOCO_GL=osmesa LP_NUM_THREADS=1

# R1 같은 버전 C3.16 / Warp. rev4585는4585ac91의 scripts.
"$OLD/warp-env/bin/python" "$ROOT/rev4585/scripts/simalt_step_probe.py" \
 --enabled --fixture "$OLD/fixture" --out "$NEW/warp-baseline-grip" \
 --engine warp --case grip --sha 4585ac9178d44784f00cce8c6ffb13270e92a56c \
 --capacity-reference "$OLD/cpu-n1/result.json"

# R2. rev5는5ce41464의 scripts. dense-capacity.json은 C129/Warp134 원본 최대값.
"$OLD/warp-env/bin/python" "$ROOT/rev5/scripts/simalt_step_probe.py" \
 --enabled --fixture "$OLD/fixture" --out "$NEW/capacity-grip" \
 --engine warp --case grip --sha 5ce41464efe3d3687aeecf8ebd7a76dcbeb9dfce \
 --capacity-reference "$ROOT/rev5/dense-capacity.json" --dense-capacity-v1 \
 --backend-mode baseline --record-own-rgb "$OLD/runtime/source"

# R3. R2와 같은 입력에서 기본 off collision mode만 추가한다.
"$OLD/warp-env/bin/python" "$ROOT/rev5/scripts/simalt_step_probe.py" \
 --enabled --fixture "$OLD/fixture" --out "$NEW/legacy-grip" \
 --engine warp --case grip --sha 5ce41464efe3d3687aeecf8ebd7a76dcbeb9dfce \
 --capacity-reference "$ROOT/rev5/dense-capacity.json" --dense-capacity-v1 \
 --backend-mode legacy-plane-v1 --record-own-rgb "$OLD/runtime/source"
```

전진/측면/회전은 `--case forward/side/turn`을 각각 새 out에 쓴다. C3.12는 `$OLD/c-env/bin/python`, C3.16은 `$OLD/warp-env/bin/python`에 `--engine cpu`를 썼다. native 로거의 실제 source는e2c2a4c4, metadata의 script SHA와 함께 확인한다. C3.13은 기존 C 환경에 의존성을 바꾸지 않고 별도 target `mujoco313`에 `--no-deps` 설치해 `PYTHONPATH`로 분리했다. [run-version313.py](run-version313.py).

[run-round2.py](run-round2.py), [run-round3.py](run-round3.py)는 실제 유한 실행 기록이다. 실제 queue는 원본 root의 `rev5/round2-plan.json`, `round3-plan.json`이며 각각 존재하는 절대경로 `rejection_table`을 포함한다. R3는 R2 완료·거부 표 작성 뒤에만 시작했다. 실행 후 소스 변경을 과거 SHA로 표시하지 않는다.

분석은 `scripts/simalt_step_analysis.py --fixture ... --reference ... --candidate ... --out NEW`를 쓴다. native3.16 대 Warp와 native3.12 대 native3.13/3.16을 따로 분석한다. R1 중단 prefix는 `--partial-evidence`가 필수이며 성공으로 수용하지 않는다. 각 비교 summary에 실제 argv와 분석 script SHA, 원본/압축 CSV SHA가 있다. [25개 전체 스텝 표 색인](evidence/remote/step-tables.json).

검토는 `scripts/simalt_review_physics.py --gcp2-v1 --source "$OLD/runtime/source" --fixture "$OLD/fixture" --run RUN --out NEW_REVIEW --case grip --failure-time-s 23.8`을 위 OSMesa 환경에서 실행했다. overflow prefix만 anchor14.5다. 전체2Hz·직전10초10Hz 띠와4배속 MP4를 만들며 MP4 검증은 ffprobe다. Mac은 띠·요약 파일만 읽었다.

최종 수집의 실행 소스는a27836a6의 `collect-results.py`였고, writer 종료 뒤2828b743의 `finalize-hashes.py`로 canonical SHA를 만들었다. 앞선 collector의 자기 완료 로그 때문에 달라진 파일은 collector.log 하나였다. 모든 raw writer가 끝난 최종 검증을 따른다. 파생 모듈 감사는 검사 항목을44→48로 확장했으며 raw physics step/state를 덮어쓰지 않았다.

회수 bundle308,700bytes SHA는 `44c296c562c90db434cff6faa5187073f7a3790775f55fe3f9689a46cf0b5bcf`다. 대형 JSON은 zstd 복원 SHA를 확인한다. 전체 raw는 L4 영속 디스크에만 있고 외부 전체 백업은 아니다. n4 비교/처리량/두 로봇/학습은 이번에 실행하지 않았다.
