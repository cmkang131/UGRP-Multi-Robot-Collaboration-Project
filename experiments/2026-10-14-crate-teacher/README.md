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

## 진단 d43d17b1 결과와 원인 (2026-10-14, 3개 모두 들기 실패)
원본: `outputs/gcp1-runs/crate-diag-7790{0,1,2}-d43d17b1`. 원본 프레임은 VM에서만 읽었다(fetch-lite가 jpg를 제외).

잘 된 것: `held_world_reads` 0, `invisible_measurements` 0, 두 로봇이 서로 다른 lug 3/3. GO/ACK/START 정상(77900 둘째 장벽 23.1 s, 77901 23.9 s).

원인 판정 (확인한 범위와 근거):
1. **들기 실패의 원인 = 팔 서보 토크 한계(상자 0.9 kg이 실제 서보 모델의 한계 밖). 기존 4개 후보 중 어느 것도 아님.**
   - 이 장면은 `real_v1` 서보 강성을 쓴다(`sim/grasp_act_scene.py:31`, `sim/s2_servo_stiffness.py`): 어깨 1.275 N m, 팔꿈치·손목 0.1765 N m(1.8 kgf cm, LFD 공식표). 화물 목록의 0.66–0.68 kg 한 대 한계(2026-09-25)는 서보 토크가 이렇게 낮게 들어가기 전 값이다.
   - 로봇 한 대가 mass m을 들 때 팔꿈치 토크: scene.xml을 MuJoCo로 읽어 자코비안(J^T F)으로 계산하면 pick 자세 0.389, lift 자세 0.432 N m (m=0.45 kg, 두 대가 정확히 반씩 들 때). 한계 0.1765의 2.2–2.4배. 한 대 최대는 lift 자세에서 0.1765/0.432*0.45 = 0.184 kg, 두 대 합 약 0.37 kg(자체 무게 제외). 빔 0.15 kg/대는 0.144 N m(82%)로 통과한다.
   - 관측과 일치: 77900에서 상자는 t=23.6에 뜨기 시작해 최대 최저점 23 mm(24.2–24.4 s)까지 올랐다가 0 mm로 돌아왔다. 기울기 7도. 두 로봇 손가락 힘은 계속 4–7 N(잡은 채). 로봇 r2의 차체 z가 0.032→0.056 m(+24 mm)로 올라갔다. 77901은 상자가 한 번도 뜨지 못했다(최저점 > 0 없음, 기울기 6도). 정지 유지 최대 0.5 s / 0 s.
   - 영상(자기 카메라, 77900 r1·r2 t=18.8·21.8·23.8·24.8·25.8·26.8, 77901 r1·r2 t=11.8·21.8·24.8·25.8·26.8·28.8, 77902 r1·r2 t=1.8·11.8·21.8·31.8·41.8·60.8): 두 로봇 모두 lug를 집게로 문 채 유지한다(lug 색이 화면을 채움). 77901 r1은 25.8 s 이후 상자 밑면(어두운 분홍)이 보여 상자가 기울었다. 집게가 빠진 것이 아니라 팔이 하중을 못 버틴 모양이다. 위에서 본 전체 시점은 해상도가 낮아(320x240 4분할) 기울기를 구별하지 못했다.
   - 아닌 것: IK 자세 없음(pick/lift 자세가 모두 풀렸다, 마지막 pick에서 팔꿈치 5번 서보 2494–2498은 한계 2500 근처이나 빔 파지도 같은 자세), 집게 미끄러짐(손가락 힘 유지, 한계는 팔꿈치), 두 로봇 시각 어긋남(GO/ACK 같은 틱, 시작 0.1 s 차이. 다만 한쪽이 먼저 뜨는 순서 효과는 서보가 모자라서 구분 안 됨).
2. **IK 거절은 원인이 아니다.** 77900 r1 14회, 77901 r1 39회 r2 14회, 77902 r2 13회는 모두 align 단계(반경이 pad 창 14.6–15.8 cm 밖일 때 `reachable=False`로 정지 후 재조정)이고, 이후 모든 로봇이 ready→pick→closed까지 갔다(pick 4 s). 거절이 들기 실패를 만들었다는 증거는 없다.
3. 77902: r1이 60 s 동안 상자를 못 봄(0/593). 다른 에이전트의 `search_body_scan_v1`(claude/e2e18-grasp-rootcause)로 고친다. 이 PR에서는 고치지 않는다.

## 수정 (모두 토글, 기본 = 이전 동작)
- `--crate-mass-kg X` (기본 없음 = 0.900 kg): 상자 geom 질량 전부를 합이 X가 되게 곱한다(`sim/crate_scene.py scale_crate_mass`, 관성은 MuJoCo가 다시 계산). 진단은 **0.30 kg**: 빔과 같은 대당 0.15 kg이라 팔꿈치 82%(이미 통과한 부하 수준)이고, 한 대 한계 0.184 kg보다 커서 두 대가 필요하다. **장면 정의(화물 목록 질량) 변경이므로 사용자/조정자 확인 필요.** 0.9 kg 그대로는 이 서보 모델에서 물리적으로 불가능하다.
  - 같은 이유로 tri_frame 1.5 kg(대당 0.5 kg)도 이 서보 모델에서는 들 수 없다(미검증 추정).
- `--rgb-lift crate_rgb_lift_v1` (기본 off): 자기 손목 카메라 프레임 두 장(자기 lift 허가 시점, 자기 lift 명령열 완료 시점)만으로 `confirmed / not_confirmed / undetermined`를 `result.json prefix.rgb_lift`에 기록한다(`sim/crate_rgb_lift.py`). 잡힌 물체(lug+몸통) 픽셀의 비율 유지, lug/몸통 비율 변화(집게 안에서 움직임), 배경(바닥) 픽셀 변화로 판정한다. **기록 전용이며 임계값은 보정 전이다**(성공한 들기 프레임이 아직 없음). 평가용 GT 들림과 나란히 저장해 일치를 센다. 77900의 기울어진 상태 프레임으로 `not_confirmed`가 나오는 것만 확인했다.
- 평가 전용 기록 추가: `eval-only.jsonl` 그라스프 행에 `servo_load`(로봇별 어깨/팔꿈치/손목 서보 힘/한계). 팔꿈치 포화(|ratio|≈1)를 직접 확인하려는 것이며 제어 입력이 아니다.
- 대기열: 77900–77902(재현, 질량 0.30)와 새 시드 77910–77912(`diag_plan_77910.json`).

## 참고 자료 (추가)
- 정적 관절 토크 τ = J^T F: Craig, Introduction to Robotics ch.5(static forces); Siciliano et al., Robotics: Modelling, Planning and Control §3.7 (원문 미확인, 표준식). 여기서는 MuJoCo `mj_jacSite`로 계산했다.
- 서보 토크 근거: `experiments/2026-10-07-servo-stiffness/REFERENCES.md`(LFD 1.8 kgf cm @6V, 공식 표). 화물 한계 근거: `experiments/2026-09-25-zone-cargo-catalogue/README.md`(real_v1 도입 전 측정).
- 쌍 협조 운반의 하중 분담이 팔 토크 한계로 정해진다는 일반 설명: 협조 조작 문헌(Khatib 계열, 원문 미확인).

## 이번 수정에서 확인 안 된 것
- 0.30 kg에서 실제로 들리는지(물리 실행 전), RGB 판정의 정확도, 두 로봇 하중 불균형(한쪽이 먼저 뜨는 순서 효과)이 0.30 kg에서 문제가 되는지.
