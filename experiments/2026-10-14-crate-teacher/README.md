# heavy_crate 정답 교사 (2026-10-14, 브랜치 claude/act-crate-teacher)

상태: 코드 완료, 시험 39 passed / 1 skipped(Mac, 물리 없음). 물리 실행(진단 3회, 관문 40회)은 아직 안 함 = 확인 안 됨.
목적: 로봇 2대가 0.9 kg 상자(heavy_crate)를 함께 집어 올리고 내려놓는 시연 교사. ACT 학생 하나가 1/2/3대 시연을 섞어 배운다는 계획의 2대 부분.

## 상자 수치와 출처
- 몸통 140x100x60 mm, 손잡이(lug) 60x40x46 mm가 중심에서 +-0.09 m (`sim/zone_cargo.py:168-179`, `LUG_HEIGHT_M` 53행, `HANDLE_*` 41행).
- 잡는 자리 (+-0.10, 0, 0.024), 질량 0.900 kg, 착지 반폭 (0.12, 0.05).
- 한 대 들기 한계 0.66-0.68 kg < 0.9 kg이라 두 대가 동시에 들어야 한다.
- 장면: s2_v4(crate_1 (1.275,-2.15), 자리 P2-1), s8_v4(crate_1 (0.125,-2.15), 자리 P1-1). 목적 구역 B 중심 (4.6,-2.1), 반폭 (0.3,0.7).
- 교사 지점: 잡는 점에서 0.203 m 앞 = 상자 중심에서 0.303 m.

## 같은 자리 방지 (이유)
- 두 자리는 상자의 서쪽/동쪽 lug다. 계획이 시연 감독 규칙(`nearest`: 두 출발점에서 두 자리까지 직선거리 합이 작은 배정)으로 서로 다른 끝을 정한다. 정답 좌표는 시연 배정에만 쓰고 학생 입력이 아니다.
- 학생 번호표는 west/east. 내부 이름 teal/blue = west/east (빔과 같은 부호 규칙).
- 상자는 180도 대칭이고 lug가 둘 다 검정이라 자기 카메라로 서/동을 구분할 수 없다(빔 검정 끝과 같은 문제). 그래서 토글 `crate_lug_colors_v1`(서 청록, 동 파랑, RGBA만, 형상·질량·접촉 불변)을 둔다. 사용자 허용은 빔 끝 색이므로 상자 lug로 넓히는 것은 조정자 결정이고 사용자 확인 대기. 색을 켠 실행은 검정 lug 실행과 합치지 않는다.
- `alternating` 배정(교차 포함)은 학습 다양성용이며 관문에는 쓰지 않는다.

## 들기 장벽
- 잡은 뒤 두 번째 READY/GO/ACK 장벽(`GraspStartSync`/`PairCarrySync`)을 통과해야 동시에 든다. READY-TO-LIFT는 자기가 낸 닫기 명령열이 끝난 것(자기 명령 이력)만 근거로 한다(`CrateGraspTeacher.lift_ready`). GT 접촉·높이는 성공 판정과 평가에만 쓴다. RGB로 들림을 확인하는 단계는 구현하지 않았다(명령 이력 기반만; 후속 과제). 20 s 안에 장벽이 안 열리면 `lift_barrier_timeout`.
- 내려놓기는 `PairReleaseCode` + 상자 치수 서브클래스(`sim/crate_release_teacher.py`).

## 규칙 준수
- visible_only: 결정에는 지금 자기 카메라에 보이는 대상의 상대 위치만 쓴다(`BandVisibility`, `VisibleWorld` 기억 5.2 s).
- held_object_hidden_v1 (`--held-object hidden_v1`): 든 동안 화물 세계 좌표 읽기는 오류. `input_audit.invisible_measurements`, `held_world_reads` 모두 0이어야 한다 (GCP 실행에서만 확인 가능).
- 학생 시계·데이터 선택에 GT 거리를 쓰지 않는다. 빔 교사의 `t.handoff` GT 거리 <= 0.8 m 같은 규칙은 복사하지 않았다. 계획이 상자를 구역 B 옆(<= 0.8 m)에 두는 것은 실행 설정이지 학생 시계가 아니다.
- 접근·정렬 동안 맡은 lug를 카메라 pan으로 화면에 두고, 가시 비율과 가장 긴 비가시 구간을 기록한다.
- weld OFF. 모든 변경은 토글이고 기본값은 이전 동작. 빔 경로 시험 통과.
- 내려놓은 뒤 둘러보기 `setdown_lookaround_v1`: `sim/crate_lookaround.py`는 Opus의 `sim/active_lookaround.py`(미커밋)에 의존한다. 그 파일이 이 트리에 없으므로 기본 off이며 켜면 명확한 오류. 이번 대기열에서도 off. 켠 경로는 시험하지 않았다.

## 코드 변경 (기본값 보존)
- 새 파일: `sim/cargo_teacher_profile.py`, `sim/crate_grasp_teacher.py`, `sim/crate_release_teacher.py`, `sim/crate_scene.py`, `sim/crate_lookaround.py`, `scripts/make_crate_teacher_plan.py`, `scripts/run_crate_teacher.py`, `tests/test_grasp_act_crate_teacher.py`.
- 공용 파일은 `profile=None` 기본 매개변수만 추가: `scripts/audit_grasp_act_visibility.py`, `harness/grasp_act_visible_world.py`, `sim/grasp_act_visible_route.py`, `sim/grasp_act_teacher_v3.py`. 시드 등록 `configs/grasp_act_seed_splits.json`(crate_gate 77000-77039, crate_diagnostic 77900-77999, 둘 다 학습 금지), 워크플로 `grasp-act-crate-teacher`.
- 해제 실행기는 `run_grasp_act_release.py`를 고치지 않고 `run_crate_teacher.py`로 갈라냈다(Opus 수정과 충돌 방지). 합치는 일은 후속.

## 계획 파일 (sha256)
- `gate_plan_77000.json` 9f2c87330c0239c39703435e33fad1e7b1def7e69b19c230ae99206fd4f0a0d0 (40개, 77000-77039)
- `diag_plan_77900.json` 4b6d96fc2a0db9e8e8c1ce5fb2f8606bd22071ea1b14c5d09f3ed0c42fb8c1ac (3개, 77900-77902)
- 분포: s2/s8 교차, 동료 위치 4종(other_end/approaching/near_own/absent), 상자 축 두 방향, 두 방향 모두 바라봄, 로봇 거리 0.5-2.0 m.

## 판정 기준 (실행 후)
- 교사 성공 >= 95% (최소 40회 = 38/40). 들기: 양쪽 >= 0.5 N, 상자 최저점 >= 12 mm, 기울기 <= 10도, 3 s 유지. 내려놓기: 착지 사각형이 구역 안, z < 0.05, 속도 < 0.01 m/s, 기울기 < 3도, 집게 열림, 2 s. 단계별 보고(들기 N=40, 내려놓기는 든 것 기준과 전체 기준 둘 다).
- 학습용 카메라 기록 OFF(성공 먼저). 진단 3회 결함은 한 묶음으로 고친 뒤 관문 40회. 결함을 확인하면 관문을 끝까지 채우지 않고 멈춘다.
- 합산 금지: GCP gcp1 n4-highcpu-64 전용. Azure, 다른 머신, 다른 프로파일(lookaround·lug 색)과 합치지 않는다.

## 확인 안 된 것
- 물리 실행 전부(Mac은 시험만). RGB 기반 들림 확인(미구현), 손목 간격(상자 lug와 손목/집게 충돌), 낙하 감지, held 읽기 0(GCP 실행에서만), 둘러보기(의존 모듈 미커밋), lug 색 사용자 승인, 가시 비율 수치(실행 전).

## 참고 자료
조사 요약(열어 읽지 않은 자료는 표시):
- Smith/Dimarogonas 계열 다중 로봇 협조 운반 개관과 Khatib의 operational-space 협조 조작: 서로 다른 접점에 하중을 분담하고 동기 들기를 장벽으로 둔다는 구조를 참고 (원문 미확인, 일반 지식 수준).
- 병렬 수행기 협조 파지의 동시 접촉 동기화: 본 코드의 READY/GO/ACK 장벽에 해당 (원문 미확인).
- 시연 생성: ACT(Zhao et al. 2023, ALOHA) 양팔 시연 + 시간 앙상블, 정답 교사 시연 + 학생 모방 (원문 미확인, 저장소의 docs/act_execution_decisions.md가 기존 근거).
- 저장소 내부: `sim/grasp_act_teacher_v3.py`(2대 빔 교사), `sim/grasp_act_release_teacher.py`, `docs/act_execution_decisions.md`, AGENTS.md의 held_object_hidden_v1 / setdown_lookaround_v1 규칙(PR #497).
