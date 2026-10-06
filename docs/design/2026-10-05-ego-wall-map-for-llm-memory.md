# 자기 좌표계 벽 지도 → LLM 메모리

Refs #216, #366. 작성 2026-10-05. **계획 문서다. 구현·실행 기록이 아니다.**

## 1. 목표

각 로봇이 **자기 팔 끝 카메라만** 써서 벽을 보고, 관측 시각의 **자기 좌표계 상대 위치**로 자기 지도만 쌓는다. 그 지도를 **자기 LLM 메모리**에 넣는다. 지도 공유 없음, 정답 좌표 없음, 상대 관측 없음.

왜 이게 연구 질문의 일부인가: 로봇마다 본 벽이 다르다. A는 문 왼쪽만 보고 B는 오른쪽만 본다. 그 차이를 메신저로만 메울 수 있다. 통신 조건 4개(무통신 / 자유 한국어 peer / 리더 교대 / 정형 메시지)에 구조적 이유가 생긴다.

지도 없는 로봇이 **자기 위치를 모르는** 상태이므로, 지도 공유는 곧 위치 공유가 된다. 무통신 조건에서 로봇들은 자기 감각으로만 움직여야 하고, 그 결과 차이가 통신 효과의 분자가 된다.

## 2. 사용자 결정

| 결정 | 내용 | 날짜 |
|---|---|---|
| 좌표계 | 관측 시각의 자기 좌표계 상대 좌표. pose·융합·루프 클로저 없음 | 2026-10-05 |
| 공개 맵 | 제거 대상 | 2026-10-05 |
| **벽 높이 가정** | **금지. 0.40 m도 예외가 아니다. 높이는 입력값이 아니라 측정값이다** | 2026-10-05 |

## 3. 현재 상태 (확인한 것)

### 3.1 벽 검출기는 "벽"을 모른다

`experiments/2026-09-26-markerless-probe/markerless_probe.py:457` `detect_boundaries`
→ 카메라 기하로 "벽이면 있을 row" 예측 → 그 row의 명도·색조 계단 검출 → band 출력. 끝.
**신원 검사 없음.**

그리고 **높이를 가정한다.** `DEFAULT_DETECTOR['wall_height_m'] = .10`(`markerless_probe.py:78`), 현행 `harness/opencv_wall_observation.py:16`은 `.40`.
이 값은 `t_of_row`로 상단 row `vt`를 예측하고, band 비율 `vb - vt >= 4px`로 수용 여부를 정한다(`markerless_probe.py:80`, `:140`).

즉 **0.40 m 벽에 대해서만 작동하는 필터다.** 벽 높이가 다른 환경에서 이 필터는 벽을 놓친다.

> **지도 없으면 현재 코드는 벽을 벽으로 아는 수단이 없다.**
> **높이 가정까지 겹치면, 특정 높이의 벽을 아는 게 전부다.**

벽 = 바닥과의 접선 + 여러 컬럼에 걸친 연속 면 + 뒤를 가림. 이 중 아무것도 쓰지 않는다. 컬럼마다 독립으로 band를 뽑고 끝이다.

### 3.2 운반물 가림 장치가 배선 안 되어 있다

`carried_mask_top`(`markerless_probe.py:432`)이 그 장치다. cyan 상자 테스트(`g > 1.6*r + 8`)이고, 자기 명령이 loaded일 때만 쓰라고 docstring에 명시.

grep 결과: **`self_top`을 넘기는 호출이 없고 `carried_mask_top`을 부르는 곳이 없다.**
`harness/opencv_wall_observation.py:30`이 인자 없이 호출 →
`self_top = np.full(n_c, HEIGHT)` → 가림 없음 → `self_margin_px` 게이트 무효화.

대체로 쓰인 색은 beam용이었다. `experiments/2026-10-03-vo-feasibility/code/vo_eval.py:23`:
```python
green = cv2.inRange(hsv, (25, 90, 60), (55, 255, 255))
black = cv2.inRange(hsv, (0, 0, 0), (180, 255, 35))
```

실경로 게이트 `LEGACY = {'wall_band_saturation_max': 80, ...}`(`harness/own_image_gates.py:16`):
- beam의 초록(S=255) → 채도 게이트에 걸려 제외됨
- beam의 **검정 가운데 띠(V≤35)** → 채도 낮음 → **통과**
- 검정 띠는 로봇에 붙어 있어 카메라에서 가장 가깝다. `Scan` docstring상 candidate 0이 pseudo range scan(가장 가까운 것)이라, 후보가 beam 하나뿐인 프레임에서 근거리 측정값을 통째로 차지할 수 있다.

**beam과 벽을 동시에 검증한 실행은 이 저장소에 없다.** VIS6은 빈 손 조건이었다.

### 3.3 벽 검출기가 거의 안 돈다

`harness/vision_pose_source_highpose.py:146`
```python
enabled = loaded and self.loc._pf.settled(now) and pose.at_high(self.servo)
```
빔을 들고 + HIGH 자세일 때만 ON. 빈손이거나 평상시 자세면 꺼진다. 현재 용도는 "빔 든 상태에서 벽 근처 위치 보정" 하나뿐이다.

`zone_pair_highpose_edge.py`의 `HIGH_EDGE_INFORMATIVE` — v98에서 "HIGH edge는 beam edge가 아니라 near-clip trace"로 정의를 바꿨다. beam 구분을 피한 우회로 읽힌다.

### 3.4 공개 맵이 이미 입력이다

`harness/vision_pose_source_highpose.py:4`
> "camera calibration, own RGB, own commands and **the public map** are the inputs."

공개 맵은 PF에 들어간다. LLM 메모리에는 안 들어간다. 목표는 이 의존을 없애고 자기 지도만 쓰는 것.

### 3.5 LLM 메모리 주입점

`harness/coela_modules.py:30` `class Memory`
- `observe(observation, sim_time)` (:42) — `observation["cargo"]`를 소비
- `snapshot()` (:75) — `observations` / `peer_reports` / `peer_observations` / `expired_peer_intents` / `own_execution_history` / `own_decisions` 반환
- `actor_context(...)` (:276) — `memory.snapshot()`을 LLM 컨텍스트에 넣음

여기에 자기 벽 지도를 추가하는 것이 배선 지점이다. `Memory.receive`(:52)의 원칙 "Peer assertions never overwrite directly measured object facts"를 벽에도 그대로 적용해야 한다.

## 4. 위협 목록과 처리

| # | 위협 | 처리 | 상태 |
|---|---|---|---|
| **T0** | **높이 가정이 인식을 구속한다** | **높이 prior 제거 → 하단 접촉만으로 검출, 높이는 산출** | 미구현 |
| T1 | beam 검정 띠가 벽 후보로 들어감 | beam 색 마스크 → `self_top` 배선 | 미구현 |
| T2 | 지도가 없으면 PF가 동작 불가 | ego frame fusion 없음 → **PF 경로 제거** | 미구현 |
| T3 | 팔 카메라 기하 — 팔 움직이는 동안 무효 (쌍의 70%) | 자세 + 정착 시간 조건 | 미구현 |
| T4 | 전프라이트 비관측 — 3면 중 1면만 보임 | 시선 회전 정책 | 미구현, 범위 미정 |
| T5 | FOV 좁음 (세로 42.19°, 가로 54.64°; 처음 적은 126°는 틀렸다, 실험 README §2.1) — 먼 벽 불가시 | 맵 규모와 함께 재검토 | 미구현 |
| T6 | 위치 모름 → 목표 도달 불가 | 최종 실행 조건으로 분리 | 미구현 |
| T7 | 채널 용량 4조건 동일, 정형이 더 좁음 | 정형 스키마에 벽 선분 필드 | 미구현 |
| T8 | 적재 시점 불일치 — 벽 지도 시각 ≠ 화물 시각 | 관측 시각 stamp 필수 | 설계에 포함 |

## 5. 파이프라인

### 단계 A — 운반물 가림 게이트 (선행 필수)

`carried_mask_top`을 beam 색으로 교체하고 `self_top`으로 전달.

- beam: yellow-green + 검정 띠 (§3.2 코드)
- cyan 상자 경로 유지 (빈손 조건)
- 자기 명령의 load 상태로 분기
- **동일 입력 동일 출력** 유지 (`opencv_wall_observation.observations`은 sha256 고정됨 — `zone_pair_highpose_opencv_exact.py:33`)

`self_top`이 살아나면 `self_margin_px`가 beam 아래 row를 전부 배제한다. 이게 실제 얼마나 막는지는 미측정이다.

### 단계 B — 높이가 아니라 "바닥 접촉"으로 검출

**여기가 설계의 핵심.** 높이를 예측하지 않는다. 이미 알고 있는 것만 쓴다.

바닥-벽 접점(bottom edge)은 카메라 기하만으로 row → 바닥 거리 변환이 된다. `ColumnModel.t_of_row`(:282) → `range_bearing`(:288). **높이 값이 필요 없다.**

인식 단서(모두 높이 무관):

| 단서 | 근거 | 구현 |
|---|---|---|
| **바닥 접촉** | 하단이 floor ray 위. 상자는 안 닿음 | row → t 변환 |
| **하단 계단** | 경계에 실제 휘도·색조 jump. 셰이딩 gradient 아님 | `edge_step` 재사용 (`opencv_wall_observation.py:19`) |
| **연속성** | 벽은 여러 컬럼에 걸친 면. 기둥은 좁고, 상자는 유한 덩어리 | 컬럼 간 연결 |
| **면의 균일도** | 벽면은 위쪽으로 균일. 상자는 윗면·옆면 색이 다름 | band std + 상단 색 |
| **가림** | 벽은 뒤를 계속 가림 | 이미지 위쪽으로 band가 계속됨 |

**높이는 산출값이 된다.** 상단 row가 보이는 컬럼에서 h를 역산해 기록하고, 안 보이는 컬럼은 `h: null`. 높이가 다른 기둥은 h가 벽과 다르다 → 이름 없이도 구별되고, 비교에도 쓸 수 있다.

비교 대상(높이가 0.40 m여야 함):
- 현재: `vt = cm.rows(t, wall_height_m)`로 상단 예측 → 비율 `vb - vt >= 4px`로 수용. **높이가 틀리면 수용 판정이 틀어진다.**
- 바뀜: 하단 row + 계단 + 연속성으로 수용. 높이는 기록만.

이렇게 하면 벽이 0.40 m가 아니어도, 0.10 m여도, 1 m여도 같은 필터가 작동한다.

출력: `[(t_a, θ_a, t_b, θ_b, h_or_null, contrast, n_columns)]`

### 단계 C — 자기 지도 누적 (ego frame)

pose·융합·루프 클로저 없음. 관측 시각의 상대 좌표를 그대로 적는다.

```python
{'t_sim': 12.3, 'seg': [(2.1, 0.21, 2.4, -0.14, 0.40), ...],
 'posture': 'high', 'load': True, 'view_index': 4812}
```

중복 제거하지 않는다. 반복 관측은 정보다("오른쪽 벽을 3번 봤다").

드리프트가 없다: coord는 그 관측 순간 자기 기준. 시간 지난 만큼 옛 관측이 부정확해진다는 것은 **LLM이 알아야 할 사실**이므로 `t_sim`을 버리지 않는다.

### 단계 D — 메모리 주입

`Memory.observe()`가 받는 observation dict에 `self_walls` 추가 → `snapshot()`이 싣는다.

```
self_walls: 3 segments | t=12.3 2.1m @ 12° → 2.4m @ -8° h=0.40
           | t=14.8 1.2m @ 88° h=0.40
```

기존 `observations` / `peer_reports`와 나란히. `peer_reports`의 벽 주장은 `self_walls`를 덮어쓰지 않는다(§3.5 원칙).

## 6. 첫 마일스톤 — 물리 실행 0회

기존 v98 / v92 기록 프레임에 1·2단계만 붙여 오프라인 재현.

| 측정 | 정의 |
|---|---|
| 선분 검출률 | 프레임당 검출 선분 수 |
| 벽 일치율 | 정답 벽 위에 놓인 선분 비율 — **정답은 채점에만. 입력·게이트·판정 로직에 절대 넣지 않는다** |
| beam 오검출률 | 단계 A 전/후 비교 |
| **높이 불변 검증** | **같은 코드·같은 임계를 0.40 m 환경과 다른 높이로 바꿔 돌려 검출률이 유지되는지** |
| 기둥 오검출률 | 높이가 다른 기둥이 벽으로 잡히는 비율 |
| 자세 조건 | 팔 움직이는 쌍에서 검출률 (§4 T3) |

**높이 불변 검증이 통과 조건의 일부다.** 이것이 깨지면 "인식"이 아니라 "0.40 m 필터"인 것이다.

## 7. 환경 벽 높이 규칙 — 별건

`sim/zone_arena.py:188-190`이 `walls_v3` = 0.40 m를 유도한다.
> wrist camera sees over a wall into another room (only through doors and corridors) and no raised arm or held box shows above one.

```
max(kinematic_max_camera_z 0.321 + 0.05, robot_top_max_z 0.367 + 0.03) = 0.397 → 0.40
```

이건 **환경 규칙**이지 카메라 보정이나 detector 파라미터가 아니다. 단계 B에서 높이 가정을 없애므로 이 값은 인식 로직을 더는 구속하지 않는다. 그래서:

- **인식 설계는 이 값과 무관하다.** 0.40 m 유지 여부는 무관하게 진행한다.
- 바꾸기로 하면 함께 갱신할 것: `sim/zone_arena.py:188-200`, `docs/research_todo.md:12`, `static_map.wall_profile`, 관련 테스트
- 낮추면 두 가지가 깨진다: 벽 너머가 보임(지도 없는 조건 무의미화), 든 박스가 벽 위로 보임(운반물이 뒤 벽 가림). 규칙을 바꾸려면 대안 유도 기준을 세워야 한다 — 이건 별도 결정

## 8. 하지 않는 것

- 위치 추정 (ego frame이므로 pose 없음)
- 루프 클로저 (지도 없는 상황이라 개념이 없음)
- 벽 semantic 분류 (벽/문/기둥 이름 붙이기) — **기하만 저장.** 높이는 기록하되 이름은 붙이지 않는다
- 학습형 분할 (`learned_segmentation: False` 유지, 현행 관측 경로와 일치)
- ORB-SLAM3 / pyslam — `experiments/2026-10-03-vo-feasibility/README.md` §4가 의존성 부재와 특징점 부족으로 기각했다

## 9. 참고

- 통신 연구 설계 `docs/coela_communication_study.md`
- 역할·관측 계약 `docs/warehouse_research_contract.md`
- 위치 추정 경계 #216, VO 가능성 #366
- 측정 탐사 `experiments/2026-10-03-vo-feasibility/README.md` (camera-only VO 불가, 추측항법이 모든 자료에서 우위)
- 실행 버전 관리 `docs/execution_versioning.md`