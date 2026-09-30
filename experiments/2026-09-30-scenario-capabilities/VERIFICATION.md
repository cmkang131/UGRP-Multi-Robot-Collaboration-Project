# P09 검증과 재현

최종 재검사 결과와 raw 해시는 이 파일에 기록한다. 실행 범위는 정적 연산/pytest뿐이다.

## import/실행 부작용 사전 확인

첫 import 전에 AST와 소스를 읽었다. `harness/__init__.py`, `sim/__init__.py`는 비어 있다. `zone_scenario_feasibility`는 geometry 함수/자료형을 정의하고, 경유하는 `static_keepouts`, `zone_team_footprint`, `zone_arena`, `zone_cargo`, `research_dispatch_arena`의 모듈 수준 호출은 상수·도형/카탈로그 생성·Path뿐이다. `_divider/_door/_corridor_walls/_corridor_passages`, `_build`, `_same_top` 본문은 수치/사전 생성이다. MuJoCo world/Scene 생성·step·renderer·모델 요청은 없다.

`zone_final_env`는 NumPy 및 `zone_map_schematic`(Pillow import)을 경유한다. `maps_dir_for/reachability`는 파일 resolver/격자 연산이며 렌더러를 호출하지 않는다. 기존 `validate/bundle_for`는 `schematic=False`다. 테스트의 임시 파일 쓰기는 pytest tmp 경로만 사용하며 원본 덮어쓰기 거절 검사를 포함한다.

`audit.py`는 다음 방어를 켠 뒤 evaluator와 pytest를 실행한다.

- `StaticOnly` import finder: MuJoCo, 주요 모델 SDK/추론 라이브러리, HTTP client, `sim.session_scenes/warehouse_mission` import를 거절한다.
- socket connect/DNS audit hook으로 외부 연결을 거절한다.
- `zone_map_schematic.render_schematic`을 항상 거절하는 함수로 바꾼다. Pillow가 import되었다는 것과 이미지 생성은 다르다.
- pytest plugin 자동 로드를 끄고 지정된 정적 파일만 실행한다.
- controller/host/Scene를 instantiate하지 않는다. `make_plan`은 기존 M2 실행/제어 모듈을 lazy import하므로 코드만 읽었다. 사건 host 구현도 코드만 읽었다.

## 재현 명령

기존 환경만 사용한다. output은 새 절대 경로를 지정해야 하며 덮어쓰지 않는다. driver가 `outputs/agent-locks/physics`를 자기 PID로 원자적으로 획득한 뒤 evaluator/pytest를 실행하고 반환한다. 기본은 점유 중 즉시 거절하며, `--lock-wait-s`를 주면 그 시간 안에서 원자적 획득을 재시도한다. 다른 잠금을 반환하거나 우회하지 않는다.

```sh
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 MKL_NUM_THREADS=1 \
PYTHONDONTWRITEBYTECODE=1 \
/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -u \
experiments/2026-09-30-scenario-capabilities/audit.py \
--output /Users/changmin/projects/ugrp/outputs/p09-static-capabilities-NEW --lock-wait-s 600 --tests
```

driver는 지정 branch `codex/scenario-capabilities`에서만 실행한다. `evaluate(scenario, maps_dir=maps_dir_for(map_id))` 기본 격자 .05 m/yaw12/여유 .03 m/sweep ON을 사용한다. `reachability`의 격자는 .02 m이며 원판 반지름 .17/.21 m 두 개다. event 추가 경로는 evaluator가 반환한 event-only rects로 계산한다. 시뮬레이터 시간은 흐르지 않는다.

## 실행 기록

- 1차 `outputs/p09-static-capabilities-20260930-01`: 6시나리오 재검사 및 기존 pytest **121 passed in 23.42s**, driver exit0, 입력 해시 불변, 금지 모듈 로드0, 잠금 반환. 총 실행69.75 wall초는 정적 작업 기록이며 SIM 처리량/벤치마크가 아니다. 결과/로그는 로컬 raw에 보존했다.
- 1차 결과를 읽다가 `passages_used`가 확장 입구 방문이라는 점을 확인하여 **정적 보고 보조 코드만** 보강했다. 중심선 양쪽의 점이 있어야 crossing으로 세며 문 입구 방문·중심선 touch→후퇴 음성 대조를 추가했다. 기존 evaluator/시나리오를 바꾸지 않았다.
- 2차 시작 시도 `outputs/p09-static-capabilities-20260930-02.log`: 직전의 읽기 전용 free 확인과 실제 acquire 사이에 다른 작업이 먼저 획득해 `lock held`로 종료했다(exit1). evaluator/pytest는 시작하지 않았다. 이 로그/빈 출력 폴더를 보존하고, driver 자체의 원자적 획득에 유한 재시도를 붙였다.
- 최종 `outputs/p09-static-capabilities-20260930-03`: **124 passed in 25.12s**, driver exit0. 기존31+90건과 새 보조3건이다. evaluator/입력은 기준 SHA와 동일(`audit_base_inputs_equal=true`), 실행 전후 입력/source 해시 불변, 금지 모듈 로드0, renderer/모델/물리0, 자기 잠금 반환을 확인했다. 유한 잠금 대기 91.495 wall초와 실제 정적 실행 72.65 wall초를 구분했다. 부하 평균(1분)은 12.94→11.63; 처리량/속도 비교에 쓰지 않는다.
- 최종26개 기본 경로의 forward sweep/원본→격자 연결/reverse sweep 모두 true. 정방향 중심선 교차는 서→동, 같은 경로 역순은 동→서다. s2 막힘 뒤4개 event 경로의 중심선 교차는 모두 `door_wide`뿐이다.
- [validation.log](data/validation.log), [manifest](data/manifest.json), [복사 바이트/해시 대조](data/artifact_checksums.json). 복사본4개는 raw와 SHA-256이 같다. Python 3.12.13; 패키지 버전은 artifact_checksums.json에 기록했다.

## 보존 및 전달 경계

- 최종 `inventory.json`, `feasibility.json`, `manifest.json`, pytest 로그를 Git 문서 기록의 `data/`에 바이트 그대로 복사하고 크기·SHA-256을 대조한다. manifest는 감사 기준·HEAD·입력/source 해시·audit script/test 해시·Python/플랫폼·잠금 PID·금지 import0·원본 불변 여부를 포함한다. 기존 evaluator/입력은 커밋된 HEAD에 고정했고 새 audit driver는 파일 SHA로 고정했다. 요청대로 검증 후 커밋하므로 기록의 `source_head`를 새 driver의 사전 커밋 SHA로 해석하지 않는다.
- 정적 계산 기록이며 학생 성공률·실제 SIM초·명령·모델비용은 `null`/미측정이다. 실제 이 작업의 물리/렌더/모델 호출 수만0으로 기록한다.
- shared registry/기존 문서/시나리오/map/controller diff0을 확인한다. 공용 pytest 보호 실행기를 바꾸지 않았으며 새 보조 검사3건은 이 driver의 명시 pytest 목록에만 포함된다. 전체 CI 목록/공용 registry에는 추가하지 않았다.
- 커밋·push·draft PR은 로컬 검사 뒤 별도로 확인한다. 사용자 요청에 따라 병합하지 않는다. Drive 업로드와 TensorBoard 성공 scalar 변환은 하지 않는다.
