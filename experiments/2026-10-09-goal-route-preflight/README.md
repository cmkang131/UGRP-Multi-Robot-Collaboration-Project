# egomap58 — P1 지도 원천 자산·물리 전 검사·HOST 차단

2026-10-09 사용자 승인. egomap57의 55001–55009는 전부 초기화 HOST_ERROR이며 RGB 0·유효 물리 과제 0이다. **이번 사용자 결정에 따라 이전 묶음은 ‘실행 오류, 결과 아님’으로 분리한다.** 이전 raw/결과/분모 기록은 수정·삭제하지 않는다. 성공/실패 성능 0/9로 해석하지 않는다. 같은 사전등록 seed를 이번 수정 실행에서 각1회 다시 실행한다.

## 실행 전 등록 — 조건·문턱 불변

[egomap56/57 사전등록](../2026-10-09-goal-route-continuous/README.md)의 acf9cc7e와 [P0/P1 설계](../../docs/selfmap-gtr-research-20261009.md)를 그대로 유지한다. T1 55001–55003(동쪽 시작), T2 55004–55009(서쪽 세 행, 각2회), 총9회. 장면 zone_wide_door_geometry_v3, SEARCH·tape_v1·real_v1·rotL·RBPF100·eg27 wide·switchable·공통 v145 heading factory·eg48 결과동일 가속, pitch/hygiene/accumulation/color gate off. 카메라/검출기/물리계수/모션/지도/제어기/예산 변경0. tape_v1 패턴 생성 규칙·seed16001·물리 스케일도 동일하며, 장면과 맞지 않던 자산 기하만 올바른 원천에서 생성한다.

| 판정 | 고정 값 |
|---|---|
| B 도착 선언 + 평가 GT 중심 B 내부 | T1 3/3, T2 ≥5/6 |
| 거짓 선언 / 벽·로봇 접촉 episode | 0 / 총9회 합계≤1 |
| 첫 목표·다음 목표·시작 귀환 | 각각270 SIM초, 최대810초; HOST60분/회 |
| 실제 지나온 시간 엣지 경로 / GT 최단(평가만) | ≤2.0; 귀환 shortcut 0 |
| 실제 경로±1m 벽 표본 커버 / 점유P / RMSE | ≥.70 / ≥.70 / ≤.20m |
| 경기장 밖≥.5m 점유 / 단서 장부 | 0 / 실행마다≥1 |

첫 확인시 즉시 접근, 자기 현재 RGB로 도달 확인, 연속추적·강제loss0, 지나온 경로로만 귀환한다. GT는 채점만. 매 실행의 시작/목표/귀환 구간별 자기·GT 경로 길이, SIM초,270초 예산 실패를 아래에 즉시 기록한다. 새 HOST_ERROR와 미실행도 모두 숨기지 않는다. 동일 HOST_ERROR 연속2회면 남은 회차를 실행하지 않고 NOT_RUN(차단)으로 기록한다. 재튜닝·임의 seed 교체·추가 재시도0.

순서: **S3의 새 s3fix 스모크 terminal 확인 + 잠금 반환** → 공유 agent_lock → 한 번에 하나. 이전 v146 종료는 이번 입장 근거가 아니다. dev_light·nice0·ugrp_session 사용, 다른 작업 프로세스 종료0,CI 대기0. 예상 총1.5–6시간+선행 대기(실측 아님),HOST 최악9시간. ENOSPC는 HOST_ERROR,10GiB 미만 시작 금지.

## 수정 범위와 원천

| 옵션 | 기본 | 이번 |
|---|---|---|
| wall_assets | off(기존 scene 함수/출력 그대로) | map_definition_v1 |
| tape pattern | 기존 | tape_v1 그대로 |
| HOST 차단 | 기존 실행기 불변 | 새 유한 cohort 실행기: type+message가 동일한 HOST_ERROR 연속2회 |

원인은 old two-door용 `tape_v1` divider_1 길이1.925m와 P1 single-door 물리 길이2.950m 불일치였다. `sim.zone_masterpi_v3_scene.static_map`의 등록·해시 검증된 지도 → 실제 장면에서 쓰는 `sim.zone_arena._geom` → `sim.wall_texture.walls_from_xml/layout/generate_assets`를 그대로 재사용한다. 별도 벽 수치 표나 복사한 XML은 원천으로 쓰지 않는다. 자산 폴더는 기하 SHA로 구분하며 source.json에 전체 지도 SHA도 고정한다. 기존 tape 생성 seed,2–3cm 폭,20–30cm 간격,2–4cm patch 규칙은 바꾸지 않았다. PNG/SVG/인쇄 위치 CSV를 같은 표에서 생성했다.

실행기는 frozen source 검증 뒤, **MjModel/MjData 생성·backend·잠금 획득 이전**에 전체 XML 변환과 벽/배치표/PNG SHA를 검사한다. 각 회차에서 재검사하며 실제 backend scene 변환에서도 다시 검사한다. 순수 XML 단계는 기존 cargo·v3·v7·강성 변환을 사용하고 step/render 0이다. 실제 hardware template의 카메라/동역학 검증을 완료했다는 뜻은 아니다. 지도 변경 시 새 기하 자산 생성 없이는 시작이 거부된다. off 함수는 입력 XML bytes 및 기존 scene dispatch를 그대로 돌려준다.

출처는 기존 검증된 프로젝트 경로 [ZoneScene](../../sim/zone_arena.py), [v3 registry](../../sim/zone_masterpi_v3_scene.py), [tape_v1 생성기](../../sim/wall_texture.py), [원래 tape 사전등록](../2026-10-07-wall-parallax-texture/README.md)다. 새 검출·제어 알고리즘이나 물리 보정은 도입하지 않았다. 원래 VT&R/heading 출처·제약도 egomap56/57에 유지한다.

## 검증·재현

- 기본 off bytes/scene identity,9 seed 전부 물리 객체 생성 없이 XML 검사,원천 지도 변경 시 자산 자동 변경,오래된 지도/배치/PNG/XML 거부,preflight 실패 시 lock/backend 호출0,동일 오류2회→남은7회 차단,제어 설정·판정 전체 동일을 해당 모듈 시험으로 고정한다.
- `python -m pytest -q tests/test_goal_route_preflight.py tests/test_goal_route_continuous.py`
- 자산 생성: `sim.goal_route_assets.generate(static_map('zone_wide_door_geometry_v3'))` (새 hash 경로에만 생성).
- 표준 workflow `goal-route-preflight-dev`, 단일 슬롯 `python -m scripts.run_goal_route_preflight --seed 55001 --expected-source-sha <SHA> --output /Users/changmin/projects/ugrp/outputs/goal-route-preflight-v1/seed55001`는 XML 검사만. `--execute`는 선행 queue 증거와 공유 잠금 필수.
- 9회 유한 실행: `python scripts/ugrp_session.py run egomap58-p1-nine -- python experiments/2026-10-09-goal-route-preflight/code/run_cohort.py --source <SHA>`.
- raw: `/Users/changmin/projects/ugrp/outputs/goal-route-preflight-v1`. 이전 raw는 `outputs/goal-route-continuous-v1`에 별도 보존. source·queue·lock·XML·해시·번들·적용 heading/speedups·각 회 결과를 보존한다.

## 로컬 검증 완료

바뀐2파일36시험 통과.9 seed XML 사전검사 모두 벽6/테이프면24,물리 객체/step/render0. 기존394파일 구현 해시 그대로,새 자산·지도·실행기 포함511파일을 동결했다. PNG/SVG/배치 전체759,778bytes. 물리 실행은 아직0/9이며 S3 s3fix 완료를 기다린다. 현재 Codex 부모 프로세스가 nice5를 상속시키는 것을 발견하여 물리 실행기로 쓰지 않는다. 별도 기존 로컬 mac CLI의 nice0을 확인했으며,실행기 자체도 nice0이 아니면 잠금/물리 전에 거부한다(renice 사용0).

## 실행별 결과 (완료 즉시 추가, 미실행은 성공 아님)

|seed/조건|B 도착/거짓 선언|귀환 선언|실행 상태/원인|구간:목표·자기/GT 거리·SIM초·270초 실패|
|---|---|---|---|---|
