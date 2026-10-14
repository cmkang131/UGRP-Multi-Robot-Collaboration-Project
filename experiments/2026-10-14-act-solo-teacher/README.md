# 1대 화물 교사 (solo_visible_only_v1)

2026-10-14. Codex가 만든 초안(미적용 패치)을 Claude가 이어받아 `origin/claude/grasp-act-probes` 3635a226 위에 적용하고
남은 결함을 고쳤다. **물리 실행은 0회다**(Mac에서는 단위 시험만). 아래 모든 성공 문장은 "코드가 이렇게 만들어졌다"이지
"로봇이 해낸다"가 아니다. 진단 3개와 새 시드 40개 관문은 GCP(`gcp1`)에서 돌려야 알 수 있다.

범위: 로봇 1대, 화물 1개(상자 4색 / can / tile)를 집어 올려 3초 들고, 제자리에 내려놓고, 둘러본다.
운반·배달 E2E가 아니다. 학습 데이터 기록은 하지 않는다(`training_rgb=false`, 성공 확인 뒤에 따로).

## 화물 조사: v4 시나리오와 s1–s8

`v4`는 시나리오 버전이다. `sim/zone_scenario_scene.py:55`의 로봇 모델은
`masterpi_v3`다. 장면·카메라·물리 설정은 변경하지 않았다.

| 1대 화물 | 전체 치수 | 질량 | 근거 |
|---|---|---|---|
| cyan / red / green / yellow 상자 | 34 × 40 × 32 mm | 30 g | `sim/zone_arena.py:44`–46 색상·반치수; `sim/research_dispatch_arena.py:135`–137 실물체 규격·질량; `sim/zone_arena.py:418`–428 원형 복제 후 색만 변경 |
| can | 지름 38 × 높이 50 mm | 80 g | `sim/zone_cargo.py:131`–137, 1대·질량·충돌 원통 반지름/반높이 |
| tile | 60 × 40 × 12 mm | 25 g | `sim/zone_cargo.py:139`–145, 1대·질량·충돌 상자 반치수 |

`maps/zones_final_v3/zone_wide_two_doors_final_v3.json:308`–312에는 네 상자
색상이 있다. 이 디렉터리의 지도는 정적 형상·구역을 정의하며 can/tile의 질량은
위 cargo catalogue에 있다. `hardmaps1_catalog.json`의 두 held-out 지도는
개발용으로 사용하지 않았다. 전체 종류·치수 확인은 소스 조사이며 적재 성능의
새 물리 검증이 아니다.

| v4 시나리오 파일 (`configs/zone_study_scenarios_v4/`) | 1대 주문 (`kind` 줄) |
|---|---|
| `s1_normal_mixed_v4.json` | cyan×2 :14, red×1 :26, can×1 :38, tile×1 :50, green×1 :77 |
| `s2_unmapped_blockage_v4.json` | cyan×2 :14, green×1 :26 |
| `s3_late_rendezvous_v4.json` | cyan×1 :29, tile×1 :41, red×1 :53 |
| `s4_narrow_door_standoff_v4.json` | cyan×1 :14, red×1 :26, green×1 :38 |
| `s5_moved_dropped_item_v4.json` | cyan×1 :14, red×2 :29, can×1 :41 |
| `s6_novel_relation_v4.json` | can×1 :14, cyan×1 :44 |
| `s7_trio_rendezvous_v4.json` | cyan×1 :29, tile×1 :41 |
| `s8_mixed_tiers_v4.json` | yellow×2 :14, can×1 :26 |

각 주문의 `required_robots=1`도 확인했다. 전체 8개 설정 파일 해시와 각 줄은
별도 `cargo-inventory.json`에 기록했다. long_beam / heavy_crate / tri_frame은
이번 1대 대상에서 제외했다.

## 교사 구조 (규칙 준수)

- 행동 결정에는 지금 자기 카메라에 보이는 대상의 상대 위치만 쓴다(`InputAudit.measure`가 지연 콜백으로 막는다:
  가시 비율 1/3 미만이거나 잡은 동안에는 위치 콜백 자체를 호출하지 않는다). 기억은 자기 발행 명령으로만 갱신하고 5.2초 뒤 버린다.
- `held_object_hidden_v1`: 닫기 명령 시작부터 열기 명령 완료까지 잡은 물체 위치를 읽지 않는다.
- 들기 확인은 자기 RGB와 자기 명령뿐이다(`sim/grasp_act_solo_rgb.py`). 정답 접촉·높이·평가는 `sim/grasp_act_solo_evaluation.py`
  (교사에 import되지 않음)와 `eval-only.jsonl`에만 있다. weld는 항상 끈다(`eq_active`가 켜지면 `WELD_ACTIVE`로 중단).
- 카메라 팬(`gaze_pose`)으로 대상을 화면 안에 두고, 단계별 가시 비율과 가장 긴 비가시 구간을 평가용으로 기록한다.
- 모든 동작은 `--teacher-profile solo_visible_only_v1 --held-object-hidden-v1 --setdown-lookaround-v1`을 명시해야 켜진다.
  기본값은 옛 동작(실행 거부)이다.

## 이번에 고친 것

### 1. tile 7 mm 파지 (`tile_low_reach_v1`)

원인(순수 명령 공간 IK 계산, 물리 아님):
- 상자 기준 서 있는 거리(팔 축에서 15.2 cm)에서 목표 높이 7 mm이면 모든 도구 피치에서 어깨 서보(5번)가 2500 펄스를 넘는다
  (피치 -55~-60도에서 최소 2545). 그래서 호버 95 mm → 7 mm 수직 경로가 0/36 반경에서 없다(`ik-feasibility-box-station-codex.json`).
  `CALIBRATED_GRASP_RADIUS_CM=(14.5, 18.0)`은 상자 기준 보정이고, tile은 그보다 가까이 서야 한다.
- 같은 IK에서 반경 보정 범위만 풀면 몸 앞 x=0.150~0.185 m(팔 반경 10.2~13.7 cm)에서 전체 경로가 가능하다.
  기존 `harness/tile_own_skill.py`(T05)도 같은 영역(x 0.176~0.180, 범위 해제, 피치 -40)을 후보로 쓰고 있었다(물리 검증은 그쪽도 0).

해법(집게·tile·`CALIBRATED_GRASP_RADIUS_CM` 상수는 그대로, tile만):

| 선택 | 값 | 근거 |
|---|---|---|
| 서는 거리 | x = 0.172 m, 정렬 허용 ±6 mm | T05 영역 안. 창 [0.166, 0.178] 전체에서 경로 가능 |
| 집는 높이 | 9 mm (카탈로그 7 mm) | 패드 길이 14.3 mm, 피치 -73도에서 패드 아래 끝이 바닥 위 2.2 mm(7 mm이면 0.5 mm 이하). 패드는 12 mm 옆면의 아래쪽 9 mm를 덮는다 |
| 도구 피치 | 목표 x의 일차식: -73도 + 750도/m·(x-0.172), 한 경로 동안 고정 | 관절 한계 여유가 창 안에서 서보 3·4·5 모두 최소 44 펄스(T05의 고정 -40도 후보는 8 펄스, 기본 -66도는 창 안 0~16 펄스) |
| 범위 해제 | `calibrated_grasp_only=False`, tile에만 | 위 원인 |

시험(`tests/test_grasp_act_solo_teacher.py`): 상자 서는 거리 원인 재현, 창 9점 × 호버+하강 8단계 전부 가능·여유 ≥ 40 펄스·패드 바닥 여유 ≥ 1.9 mm,
정렬됐지만 닿을 수 없는 목표(패드가 바닥 아래)는 3틱 뒤 `visible_target_ik_unreachable`.
**확인 안 됨**: 실제 MuJoCo에서 9 mm 파지로 tile이 들리는지, 범위 밖(보정 안 된) 팔 반경에서 FK와 렌더가 맞는지,
패드 외 부위(손가락 판, 손목)가 바닥에 닿는지. 진단 tile 1개가 이를 처음 확인한다.

### 2. 자기 RGB 들기 확인 (`sim/grasp_act_solo_rgb.py`)

Codex 초안은 v1 `judge_holding_item`(고정 CARRY 영역)을 썼다. 이는 can에서 항상 `unknown`이고 자세가 맞지 않으면 `NOT_IN_CARRY_POSTURE`다.
대신 `zone_own_perception_v3_1.judge_held_item(..., grasp_pose=교사가 얼린 파지 자세)`를 쓴다: 자기 발행 펄스로 예측한 "손에 든 물건의 화면 실루엣" 안에
주문 종류의 색이 있는지(영상 정보 관문 포함). 합성 실루엣 시험: 상자·tile은 yes, 바닥만이면 no, 다른 색이면 no, 검은 화면은 unknown.
- 상자 실루엣 약 65 000 px, tile 약 193 000 px(둘 다 5 000 px 문턱 이상).
- **can은 도달 가능한 모든 피치(-90~-40도)에서 예측 실루엣이 0 px**다(카메라가 can 안쪽/근접 절단면에 가려짐). 그래서 can에만 대체 증거를 쓴다:
  교사가 얼린 "파지 전에 보였던 바닥 자리"를 다시 보고 맨 바닥이면 들어 올렸다고 본다(`judge_slot_item`). 이는 "손에 있다"보다 약한 증거다
  ("들었다"와 "치웠다"를 구별 못 함). 결과에 증거 종류(`lift_rgb_evidence_ticks`)를 남기므로 보고에서 구분한다. 물리적 들기는 평가기가 따로 채점한다.
- **확인 안 됨**: 실제 렌더 프레임에서 yes가 나오는지(합성 프레임만 확인). 문턱은 새로 고르지 않았다.

### 3. 지형지물 인식과 set-down 둘러보기 (`sim/grasp_act_solo_lookaround.py`)

Codex의 `MapLookaround`(검출기 연결 없음, 넓은 prior)를 버리고, Opus 구현과 같은 코드를 쓴다: `sim/lookaround_localization.py`의
`LookaroundLocalizer`(정적 지도의 벽·구역선·문 → `active_lookaround.plan_views` 정보 이득 시야 선택 → OpenCV 벽·구역선·문 검출 → 격자 갱신)와 `ScriptRunner`.
이 모듈은 그 스크립트를 교사의 10 Hz 바퀴 펄스 명령으로 옮기는 얇은 어댑터다.
- 640×480 자기 RGB만 쓴다. 예측된 지형지물은 관측으로 세지 않는다.
- 자기 위치 추정은 장면 소유자(runner)가 set-down 기술이 시작될 때 `실제 위치 + plan['handoff_pose_error']`(에피소드별 고정, σ 5 cm / 2도)로 만들어
  `arm()`으로 넘긴다. 짝 릴리스가 지도 코드의 추정을 만드는 방식과 같다. 교사는 이 값의 출처를 보지 못한다. 이후는 자기 발행 바퀴 펄스의 주행 거리 계산(`visible_belief.odometry`)으로만 움직인다.
- 접근 구간의 주행 거리 계산은 쓰지 않는다: 교사의 `command_delta`(0.1초 펄스당 17.9 mm, 회전 1.42 rad/s)와 `visible_belief`(12.9 mm, 0.35 rad/s)는 값이 다르고
  자유 로봇 단독 회전율은 측정되지 않았다. 이 차이를 열린 문제로 남긴다.
- 평가용 기록(`eval-only.jsonl`의 `lookaround_view`와 `result.json`): 시야마다 추정 대비 실제 위치 오차(전/후), FK 카메라와 렌더 카메라 차이. 교사로 되돌리지 않는다.
- **확인 안 됨**: 단독 로봇이 몸을 돌리는 회전율, 실제 검출 수·오차 감소량(진단 3개의 `lookaround.evaluation`을 봐야 한다).

### 4. 실행 보조

- `scripts/make_solo_teacher_plan.py`: 진단 3(cyan·can·tile, 시드 76900–76902)과 관문 40(시드 76000–76039, cyan 7·red 5·green 5·yellow 3·can 10·tile 10,
  종류 순환 배치)의 계획. 홀드아웃 지도 시나리오 s4 제외. 시작은 화물 서쪽 0.6–1.1 m, 화물 쪽 ±25도.
  `configs/grasp_act_seed_splits.json`에 `solo_gate`·`solo_diagnostic` 등록(키만 추가, 학습 금지 목록에 포함).
  같은 파일을 #500(`crate_gate` 77000대)도 고치므로 병합 순서에 따라 키 합치기 충돌이 날 수 있다.
- `scripts/grasp_act_host.py`: `claude/e2e18-grasp-rootcause` a746935f의 파일을 그대로 가져옴(runner가 import, 기반 브랜치에는 없었음).
- runner는 `eyes.region_visible`로 보이는 장애물 목록을 2 Hz로만 갱신한다(10 Hz에서는 벽 지오메트리마다 레이캐스트라 느림). 실제 wall/SIM은 확인 안 됨.

## 검증 범위

- 단위 시험 5개 파일(solo 4 + `test_grasp_act_release_teacher.py`, 시드 등록부 사용): 모두 통과, 위 "확인 안 됨"을 제외한 전부 실제 공유 IK·명령 검증·둘러보기 계획 코드로 실행.
  runner의 지연 import 24개 이름 전부 해석 시험 포함(`test_runner_deferred_imports_resolve`).
- Mac 물리·렌더 0회. GCP 진단 0/3, 새 시드 관문 0/40, 학습 데이터 0.
- 합격 기준 제안(관문): 40개 중 38개 이상, 종류별 n/N을 따로 보고(종류별로 40개로 인증하는 것이 아님). 가시 비율·최장 비가시 구간·입력 감사(비가시 측정 0, 잡은 물체 읽기 0) 함께 보고.

## 참고 자료

Codex 초안 작성 시 확인(수치 성능을 우리 과제로 옮기지 않음):
1. [Chaumette & Hutchinson, Visual Servo Control Part I (2006)](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf): 관측된 목표를 화면에 유지하는 서보 설계.
2. [ACT / ALOHA (2023)](https://arxiv.org/html/2304.13705)와 [공식 scripted_policy.py](https://github.com/tonyzhaozh/act/blob/main/scripted_policy.py): 교사가 만든 waypoint 보간. 정답 전체 초기화는 채택하지 않음.
3. [Warrington et al., Robust Asymmetric Learning in POMDPs (ICML 2021)](https://proceedings.mlr.press/v139/warrington21a.html): 교사/학생 관측 차이.
4. [MimicGen 데이터 생성 문서](https://mimicgen.github.io/docs/tutorials/datagen_custom.html): 물체 중심 하위 작업.
5. [Qian et al., Scene Graphs for imitation (CVPR 2026) 프로젝트](https://pengqinhe.github.io/Scene-Graph-CVPR2026-website/): 비가시 대상 기억(논문 전체·코드 미검증).

이번 추가 조사(tile 도달·관절 한계):
6. Zacharias, Borst, Hirzinger, "Capturing robot workspace structure: representing robot capabilities," IROS 2007 ([서지 기록](https://elib.dlr.de/62685)):
   팔 작업 공간은 방향에 따라 닿는 범위가 다르다. 쪽수는 출처마다 다름(4490–4495 / 3229–3236), 본문은 못 읽음.
7. Vahrenkamp, Asfour, Dillmann, "Robot placement based on reachability inversion," ICRA 2013, pp. 1970–1975 ([PDF](https://h2t.iar.kit.edu/pdf/Vahrenkamp2013.pdf)):
   목표를 잡을 수 있는 몸 위치를 팔 도달성 지도를 뒤집어 고른다. 우리는 지도를 만들지 않고 같은 생각(목표가 닿는 곳에 서기)을 한 변수(서는 거리)로만 적용했다.
8. Liégeois, IEEE Trans. SMC 7(12), 1977, DOI 10.1109/TSMC.1977.4309644 (본문 미열람, 2차 출처로만 확인):
   여유 자유도로 관절 한계에서 멀어지는 고전 방법. 우리 팔은 여유가 피치 하나뿐이라 피치를 한계 여유가 큰 쪽으로 정하는 단순한 형태만 썼다.
9. 둘러보기 방법의 출처(정보 이득 시야 선택, Active Markov Localization, 격자 위치 추정)는 `sim/active_lookaround.py`와 `sim/lookaround_localization.py` 머리말의 목록을 따른다(Opus, PR #484/#491).
10. 자기 영상 판단: 저장소의 `harness/zone_own_perception_v3_1.py`(재사용). 새 임계값은 만들지 않았다.
