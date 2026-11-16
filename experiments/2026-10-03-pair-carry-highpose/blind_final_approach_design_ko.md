# v98 닫기 직전 "보고 나서 움직이기" 설계 (blind final approach)

- 대상: PR #363, 후보 번들 `zone-final-pair-highpose-v98`, 기준 SHA `3358372e`
- 상태: 설계 초안(작성 당시). 기록된 프레임으로 오프라인 재생만 했다. 폐루프(물리) 실행은 하지 않았다.
- 6절 열린 결정은 조정자가 2026-10-04에 정했다. 적용 내용과 폐루프 결과는 [README](README.md)의 "보지 않는 마지막 접근" 절에 있다(호버 확인은 연속 2프레임, CI 목록 추가 등).
- 변경 범위: v98 전용 파일과 새 모듈만 바꿨다. 공용 동결 파일(`zone_pair_grasp.py`, `zone_final_pair_guards.py`, `zone_pair_beam_track.py`, `zone_pair_vision.py` 등)은 그대로다.

## 1. 문제

- `raise_high_align` 단계 검사(3358372e)에서 r1이 54.1 SIM초에 닫기를 거부당했다. 순서는 `BEAM_UNCERTAIN` → `PREGRASP_NOT_READY`였다.
- 바닥 잡기 자세(서보 1269/2052/2494/1500)에서는 자기 손목 카메라에 빔이 한 픽셀도 보이지 않는다. 그래서 닫기 전 빔 추정(`beam_track.estimate`)이 `None`을 낸다.
- 이것은 카메라 기하의 사실이다. 카메라 위치·시야(FOV)는 바꾸지 않는다(AGENTS.md).
- 사용자 생각: "짐을 들면 안 보일 테니까, 짐을 들기 전에 미리 확인하는 과정이 있겠지." 이 설계는 그 생각을 그대로 따른다. 빔이 아직 보일 때 확인하고, 그다음은 확인한 값과 자기 명령 기록으로 움직인다.

## 2. 기록 데이터 측정 (오프라인, 물리 실행 없음)

원본은 `/Users/changmin/projects/ugrp/outputs/v98-dev-probe-raise_high_align-3358372e/before_door`(r1)이다. 재생 스크립트는 `blind_final_approach_replay/`의 `measure_last_visible.py`, `replay_track.py`, `lateral_mid.py`에 있다.

| 시점(SIM초) | 자세(서보 3/4/5) | 공구 높이 | 빔 색 픽셀 | 측정된 카메라 모델 | 제어기 쪽 결과 |
|---|---|---|---|---|---|
| 51.8 | 둘러보기 자세 508/2432/1320 | 148 mm | 약 4만 | 있음 | 서 있는 위치 추정(standoff) 성공. 잡는 점 x 0.2046 m, std 15 mm / 1° |
| 52.85–52.95 | 호버(hover) 807/1897/2187 | 95 mm | 약 10.8만 (투영 2.7만 점) | 있음 | 기존 추적 검사 통과. 띠 지지율(support) 1.0, 단면 38.5 mm, 띠 가로 중심이 고정 잡기 선에서 0.06 mm |
| 53.0–53.75 | 내려가는 중간 자세 | 85→29 mm | 6.7만–13.7만 | 없음 | 투영 불가(측정되지 않은 자세) |
| 53.8–54.1 | 잡기 자세 1269/2052/2494 | 24 mm | 0 | 있음 | 추정 `None` → 거부 |

- **마지막으로 보이는 자세는 두 가지로 적는다.**
  - 픽셀 기준: 53.75초, 서보 1254/2076/2455(내려가기 5단계와 6단계 사이), 공구 높이 약 29 mm.
  - 보정된 카메라 기준: 호버(공구 높이 95 mm). 이 자세는 이미 `required_camera_poses()['unloaded']`에 있어 새 보정이 필요 없다.
- **설계는 호버에서 확인한다.** 중간 자세들은 카메라 모델이 측정되지 않아 투영할 수 없기 때문이다.
- **남은 접근 거리 (자기 명령 기준):** 호버에서 잡기 자세까지 고정 경로 7단계 × 0.12초이고, 그 뒤 0.3초를 안정화한다.
  - 공구는 수직으로 71.1 mm 내려간다. 수평 변화는 0.02 mm다.
  - 차체 이동은 0이다(명령은 `hold`뿐).
  - 기록에서는 호버 확인 프레임(52.9초)부터 닫기 준비 판단(54.1초)까지 1.2초 걸렸다.
- **안정성:** 서 있는 위치 추정은 51.55–51.85초 동안 x가 0.2046 m로 같았다. 호버 프레임 3장의 지지율은 1.0, 단면은 38.4–38.5 mm, 가로 중심은 −0.12 mm로 서로 같았다.
- **정확도 (오프라인 평가 전용, 정답 사용, 제어에 들어가지 않음):** 51.8초에 정답 잡는 점은 로봇 기준 x 0.2044 m, y 0.0 m였다. 제어기 추정과의 차이는 0.2 mm다. 고정 잡기 목표(0.2032 m)와는 1.2 mm 차이로, 정렬 허용치 3 mm 안이다.
- **한계:**
  - 표본은 r1 한 번뿐이다. r2는 정렬 재관찰 중이라 닫기까지 가지 못했다. 기하와 보정이 같으니 같아야 하지만 측정하지는 않았다.
  - 기록의 호버 프레임은 호버 명령이 끝난 직후 0–0.1초 안에 찍혔다. `frames.jsonl`에는 실제 관절값이 아니라 발행한 PWM이 들어 있다. 새 설계는 호버 뒤에 0.3초 안정화를 넣으므로 실제 확인 프레임은 더 늦다.

## 3. 선행 방법 조사 요약

자세한 출처는 맨 아래 참고 자료에 있다.

- **보고 나서 움직이기 (look-then-move).** 목표를 한 번 추정하고 개루프(open-loop)로 움직이는 것은 고전 분류에 들어 있다(Hutchinson·Hager·Corke 1996). 정지한 물체라면 정상적인 방법이다. Kragic·Christensen 2002 조사에도 "시각 정렬 뒤 몇 cm 수직으로 내려가 잡기" 사례가 있다.
- **최근 학습 기반 손목 카메라 잡기도 마지막 구간은 보지 않는다.**
  - GG-CNN(Morrison 외 2018): 깊이가 150 mm보다 가까우면 목표 갱신을 멈춘다. 그때까지의 평균 목표로 약 70 mm를 개루프로 내려간다. 우리 71 mm와 거의 같다.
  - Viereck 외 2017: 14 cm 안에서는 정해진 동작으로 닫는다.
  - DGBench 2022: 마지막 단계를 개루프로 처리하는 것이 일반적이라고 정리한다.
- **이동 조작(mobile manipulation)에서도 같다.** HomeRobot·OK-Robot·Stretch는 한 번 관찰한 뒤 고정 경유점으로 접근한다. 다만 상당수는 잡은 뒤 확인이 없다. OK-Robot은 이것을 한계로 적었다.
- **경계(guard).** 보지 않는 구간은 "허용 범위 안에서만 움직이기(guarded move, Will·Grossman 1975)"로 막는다. 예: GG-CNN의 높이 바닥 값과 힘 한계, Spot의 "목표가 영상 가장자리에 있으면 계획하지 않음".
- **빈 곳:** 조사한 자료 가운데 보지 않는 구간에 시간 상한이나 중단 코드를 정한 것은 없었다. 아래의 시간·거리 상한과 중단 코드는 우리 설계다. 근거는 경계 이동(guarded move)과, 기존 닫기 대기 시간을 물려받은 값이다.

## 4. 설계

### 4.1 호버 확인 (빔이 보이는 마지막 보정 자세)

- 열린 상태로 내려가기를 호버에서 멈춘다. 호버까지 1.0초, 기본 정착 0.1초, 추가 안정화 `HOVER_SETTLE_S` 0.3초다. 0.3초는 마지막 내려가기 뒤 안정화와 같은 규칙이다.
- 호버에서 **바뀌지 않은 닫기 전 검사(`CommandGuard.preclose_check`)를 그대로 돌린다.**
  - 자기 위치 보고의 신선도와 std, 게이트를 본다.
  - v98 프레임 문턱과 같은 카메라 명령인지를 본다.
  - 시각 빔 추적 추정(띠 지지율 95 % 이상, 카탈로그 단면)과 정지 빔 벽 간격도 본다.
- 여기에 하나를 더 본다. 호버 영상에서 빔 띠의 가로 중심이 고정 잡기 선(y = 0, x = 0.2032 m)에서 `HOVER_LATERAL_TOL_M` 안에 있어야 한다. 이 값은 정렬 허용치 3 mm와 같다. 측정값은 0.06 mm다.
- 이 검사가 확인하는 것과 확인하지 않는 것:
  - 호버 검사는 "빔이 서 있는 위치 가설이 가리키는 곳에 여전히 있고, 카탈로그 단면을 가졌으며, 가로로 고정 잡기 선 위에 있다"를 확인한다.
  - 세로(앞뒤, x) 위치는 호버에서 관측되지 않는다. 띠가 잘리기 때문이다(`BAND_CLIPPED`).
  - x는 서 있는 위치 추정과 정렬 단계(연속 2프레임)에서 오고, 그 뒤 차체 이동은 0이다. 그러니 호버 검사를 "정렬 확인"이라고 부르지 않는다.
- 실패하면 새 자기 프레임으로 최대 `HOVER_CONFIRM_MAX_S` 1.0초 동안 다시 시도한다. 그래도 안 되면 중단한다. 확인 없이는 절대 내려가지 않는다.

### 4.2 보지 않고 내려가 닫기

- 확인이 되면 추적기에 "보지 않는 구간(blind window)"을 연다.
- 그다음 고정 경로(7단계, 각 0.12초, 마지막 0.3초 안정화)를 큐에 넣는다. 닫기 준비와 닫기 동시 시작 장벽(barrier)은 그대로다.
- 잡기 자세에서 시각 패치가 없으면, 추적기는 서 있는 위치 가설을 자기 명령으로 전파한 값을 돌려준다. 단, 아래 조건을 **모두** 만족할 때만이다.
  1. 이 구간(segment)에서 호버 확인이 있었다.
  2. 확인 뒤 발행한 모든 명령이 고정 경로의 테두리 안에 있었다.
     - 차체 이동 명령(속도가 0이 아닌 `mecanum`/`drive`)이 없었다.
     - 팬(pan)이 바뀌지 않았다.
     - 서보 3/4/5 펄스가 호버~잡기 경로의 최소·최대 ± 2 안에 있었다.
     - 집게가 다시 열리지 않았다(닫기 PWM 단계는 허용).
     - 모르는 명령 종류가 없었다.
  3. 지금 자세가 고정 잡기 자세(서보 3/4/5/6)다.
  4. 확인 프레임에서 `BLIND_MAX_S` 안이다.
  5. 내려간 거리가 `BLIND_MAX_DROP_M` 0.075 m 이하이고 수평 변화가 `BLIND_MAX_XY_M` 0.002 m 이하다.
  6. 추적 가설 자체가 동결 한계 안에 있다(기준 영상 나이 30초 이하, std 50 mm / 3° 이하).
- 이 전파 값으로 **바뀌지 않은** 정지 빔 벽 간격 검사가 돈다. 닫기 PWM 단계마다 도는 기존 검사(`PREGRASP_BEAM_UNSAFE`)도 그대로다.

### 4.3 상한 값

새로 조정한 값은 없다. 모두 고정 자세 또는 물려받은 시간에서 나온다.

| 값 | 크기 | 근거 |
|---|---|---|
| `BLIND_MAX_S` | 22.14초 | 고정 내려가기 0.84 + 안정화 0.3 + 기존 닫기 대기 `CLOSE_WAIT_S` 20 + 닫기 PWM 0.5 + 격자 여유 0.5. 부모 코드도 잡기 자세에서 이 시간만큼 기다렸다. |
| 기준 영상 나이 | 30초 | 동결 `MAX_AGE_S` (서 있는 위치 추정 기준) |
| 수직 이동 | 71.1 mm (상한 75 mm) | 고정 자세의 순기구학 |
| 수평 이동 | 0.02 mm (상한 2 mm) | 고정 자세의 순기구학 |
| 차체 이동 | 0 | 이동 명령이 하나라도 있으면 구간을 닫는다 |
| 호버 가로 허용 | 3 mm | 정렬 단계 허용치와 같다 |

### 4.4 중단 코드

- 호버:
  - `PREGRASP_HOVER_UNCONFIRMED`: 기존 닫기 전 검사 실패
  - `PREGRASP_HOVER_LATERAL_SHIFT`: 띠가 잡기 선에서 3 mm 넘게 벗어남
  - `PREGRASP_HOVER_NOT_VISUAL`: 확인 프레임이 이번 시각 추정 프레임이 아님
  - `PREGRASP_HOVER_POSE_NOT_COMMANDED`: 호버 자세나 열린 집게가 아님
- 잡기 자세(`_wait_close`):
  - `PREGRASP_BLIND_NOT_CONFIRMED`
  - `PREGRASP_BLIND_BASE_MOVED`
  - `PREGRASP_BLIND_PAN_MOVED`
  - `PREGRASP_BLIND_ARM_OFF_PATH`
  - `PREGRASP_BLIND_GRIPPER_REOPENED`
  - `PREGRASP_BLIND_UNKNOWN_COMMAND`
  - `PREGRASP_BLIND_SEGMENT_CHANGED`
  - `PREGRASP_BLIND_WINDOW_EXPIRED`
  - `PREGRASP_BLIND_DISTANCE_EXCEEDED`
  - `PREGRASP_BLIND_TRACK_UNCERTAIN`
- 다른 항목이 실패하면 예전처럼 `PREGRASP_NOT_READY`다. 닫기 PWM 중 실패는 기존 `PREGRASP_BEAM_UNSAFE`다.

### 4.5 기록되는 것

- 호버 검사마다 `blind_hover_check`를 남긴다: 통과 여부, 코드, 프레임 id와 sha256, 위치 검사 항목, 구간 기록. 구간 기록에는 확인 시각·프레임, 내려간 거리, 가로 중심, 확인 때 빔 가설, 구간이 닫힌 이유와 그 명령이 들어 있다. 동결 검사의 조용한 거부도 이것으로 진단할 수 있다.
- 호버와 잡기 자세의 `preclose_beam_guard`는 기존대로 남는다. `beam`에는 `evidence`(`visual` 또는 `blind_after_hover_confirmation`), `blind_s`, 확인 프레임, 내려간 거리, 가로 중심이 추가된다.
- 그 밖의 기록:
  - `blind_descent_queued`: 경로 큐 시각
  - `blind_final_approach_refused`: 코드와 구간 기록
- 번들 `timing.blind_final_approach`, `Runtime.record()['blind_final_approach']`, 등록 파일 `blind_final_approach.profile`(`zone_pair_blind_final_approach_v98`)에 상한과 입력 범위를 고정한다. 새 모듈은 소스 폐포(source closure)로 번들 해시에 들어간다.

### 4.6 입력 경계와 남는 위험

- 입력:
  - 쓰는 것: 호버의 자기 RGB, 측정된 호버 카메라 모델, 자기 발행 명령.
  - 쓰지 않는 것: 정답 좌표, 접촉·성공 신호, 공용 top 카메라.
- 남는 위험:
  - 보지 않는 구간에 짝 로봇이 빔을 건드려도 닫기 전에는 알 수 없다. 부모 코드는 닫기 PWM마다 시각 검사를 다시 했지만, 이 자세에서는 원래 볼 수 없었다.
  - 잡은 뒤의 확인(자기 집게로 놓침 감지 + 짝에게 알림)은 이번 범위가 아니다. 계속 기록만 한다(registry `grip_monitor`, 사용자 10/3 결정).
- 조사 결과와 같은 구조다. 마지막 구간은 개루프로 가고, 실패는 잡은 뒤 확인에서 잡는다.

## 5. 시험

- 새 파일 `tests/test_highpose_blind_close.py`: 20개 시험.
  - 기록 프레임 3장(서 있는 위치·호버·잡기, 38 KB)과 그 사이 발행 명령 213줄, 측정 카메라 모델 3개를 담은 fixture `tests/fixtures/highpose_blind_close`를 쓴다. 정답은 들어 있지 않다.
  - 확인 내용:
    - 확인이 없으면 3358372e와 같은 거부(`BLIND_NOT_CONFIRMED`)가 난다.
    - 확인하면 잡기 자세에서 전파 가설을 쓴다.
    - 닫기 PWM 단계에서는 구간이 유지된다.
    - 차체 이동·팬·경로 밖 서보·모르는 명령에서는 구간이 닫힌다.
    - 시간·구간·자세 한계가 지켜진다.
    - 호버의 가로 이동, 자세, 프레임 불일치는 거부된다.
    - 컨트롤러가 호버에서 멈추고, 확인 뒤에만 경로를 큐에 넣고, 실패하면 막힌다.
    - `_wait_close`가 중단 코드를 정확히 이름 붙인다.
    - MRO 위치가 맞고 동결 문턱을 참조하지 않는다.
    - 등록·번들 기록이 맞다.
- `tests/test_zone_final_pair_highpose.py`가 v96 등록 파일과 v98 등록 파일의 차이 키 목록을 고정하고 있어서, 그 목록에 새 키 `blind_final_approach`를 더했다(v98 전용 시험 파일).
- 관련 기존 v98 시험도 함께 돌렸다. 결과는 144개 중 143개 통과였고, 실패 1개는 위 키 목록이었다. 목록을 고친 뒤 그 파일과 새 시험을 다시 돌려 39개가 모두 통과했다.

## 6. 열린 결정

1. **번들 ID.**
   - v98은 `DRAFT_UNSEALED`이고 SHA로 구분한 DEV 기록이 있다.
   - 이 변경은 제어기 동작을 바꾼다. 그래서 v98 안에서 SHA로만 구분할지, 새 ID를 쓸지 정해야 한다.
   - v99는 #371이 쓰고 있으므로 새 ID라면 그다음 번호다.
2. **보지 않는 구간의 길이.**
   - 지금은 물려받은 22.14초다.
   - 대안은 짧은 상한(예: 3초)이다. 넘으면 호버로 다시 올라가 재확인하고 다시 내려가며, 횟수에 상한을 둔다. 짝 로봇이 늦을 때 빔이 밀릴 위험을 줄이지만 코드가 늘어난다.
3. **호버 확인 프레임 수.** GG-CNN은 3샘플을 평균한 뒤 목표를 고정한다. 지금 설계는 한 프레임으로 통과한다. 정렬 단계처럼 연속 2프레임을 요구할지 정해야 한다.
4. **중간 자세(내려가기 5단계, 공구 약 34 mm)의 카메라 보정.** 보정하면 확인을 더 가까이서 할 수 있지만 별도 보정 작업이다.
5. **시간 하한 표.** `zone_pair_highpose_timing._grasp_s`는 호버 정지(+0.3초와 검사 틱)를 넣지 않았다. 여전히 유효한 하한이지만 약 0.4초 작다. 300초 상한에는 영향이 없다.
6. **CI 목록.** `scripts/run_ci_tests.py`는 공용 파일이라 새 시험을 넣지 않았다. #363 작성자가 v98 시험 목록에 추가할지 정해야 한다.
7. **호버 가로 검사(`HOVER_LATERAL_TOL_M`)를 바로 적용할지.**
   - 이 검사는 기존 검사를 옮긴 것이 아니라 새로 더한 것이다.
   - 측정값은 0.06 mm로 허용치 3 mm보다 훨씬 작다. 다만 표본이 하나다.
   - 바로 적용할지, 처음에는 기록만 할지 정해야 한다.
8. **모르는 명령 종류의 처리.** `BLIND_UNKNOWN_COMMAND`는 hold·drive·mecanum·look·arm이 아닌 명령이 오면 일부러 구간을 닫는다(fail-closed). 기록된 구간에는 이 다섯 종류만 있었다.
9. **새 실패 이름의 분류.** `PREGRASP_BLIND_*`, `PREGRASP_HOVER_*`는 새 실패 이름이다. 평가 스크립트의 분류표에 넣어야 한다.
10. **폐루프 확인.** `raise_high_align` 재실행(r1, r2 모두)으로 확인한다. 물리 잠금과 부하 기록 규칙을 따른다.

## 참고 자료

"확인"은 해당 절이나 코드를 직접 읽었다는 뜻이다. "미확인"은 초록이나 2차 언급만 봤다는 뜻이다.

- Hutchinson, Hager, Corke (1996). A tutorial on visual servo control. IEEE T-RA 12(5). https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/HutHagCor96.pdf. 확인(스캔 PDF를 OCR로 읽음).
  - 보고 나서 움직이기와 끝점 개루프·폐루프를 구분한다. 특징이 사라질 때 관측기로 예측하는 방법도 다룬다.
- Chaumette, Hutchinson (2006/2007). Visual servo control Part I/II. IEEE RAM. https://faculty.cc.gatech.edu/~seth/ResPages/pdfs/ChaHut06.pdf, ChaHut07.pdf. 확인.
  - 시야 유지 기법(특징 선택, 전환, 경로 계획)을 다룬다. 접촉 직전 개루프 전환은 다루지 않는다.
- Kragic, Christensen (2002). Survey on visual servoing for manipulation. KTH/CVAP 기술 보고서. web.archive 사본. 확인.
  - 개루프 범주를 둔다. "정렬 뒤 수직으로 몇 cm 내려가 잡기" 사례가 있다.
- 미확인(초록만 읽음):
  - Mezouar, Chaumette (2002). IEEE T-RA. https://inria.hal.science/inria-00352101
  - Garcia-Aracil 외 (2005). IEEE T-RO 21(6). https://inria.hal.science/hal-04654343
  - Cherubini, Chaumette (2013). IJRR. https://inria.hal.science/hal-00750623
- Folio, Cadenat (2008). A sensor-based controller able to treat total image loss. IROS. HAL hal-00603686(web.archive). 확인.
  - 영상이 완전히 사라져도 마지막 측정과 자기 속도 명령으로 특징을 예측한다.
- Morrison, Corke, Leitner (2018). Closing the loop for robotic grasping (GG-CNN). RSS. arXiv 1804.05172. 확인. IJRR 2020판은 미확인.
  - 코드는 https://github.com/dougsm/ggcnn_kinova_grasping `scripts/kinova_closed_loop_grasp.py`다.
  - 깊이 150 mm보다 가까우면 목표를 고정하고 약 70 mm를 개루프로 간다.
  - 높이·도달·힘 조건에서 멈춘다.
- Haviland, Dayoub, Corke (2020). Control of the final-phase of closed-loop visual grasping using IBVS. arXiv 2001.05650. 확인.
- Viereck, ten Pas, Saenko, Platt (2017). Learning a visuomotor controller … simulated depth images. CoRL. arXiv 1706.04652. 확인.
  - 14 cm 안에서는 정해진 동작으로 닫는다.
- Levine, Pastor, Krizhevsky, Ibarz, Quillen (2016/2018). Learning hand-eye coordination for robotic grasping. IJRR. arXiv 1603.02199. 확인.
  - 어깨 너머 카메라를 쓴다. 집게가 없는 사전 영상을 함께 쓴다.
- Kalashnikov 외 (2018). QT-Opt. CoRL. arXiv 1806.10293. 확인.
  - 어깨 너머 카메라를 쓴다. 들어 올린 뒤 떨어뜨려 영상을 비교해 성공을 판정한다.
- Burgess-Limerick, Lehnert, Leitner, Corke (2022). DGBench. arXiv 2204.13879. 확인.
  - 마지막 단계를 개루프로 처리하는 것이 일반적이라고 정리한다.
- Burgess-Limerick 외 (2023). An architecture for reactive mobile manipulation on-the-move. ICRA. arXiv 2212.06991. 확인.
- hello-robot/stretch_ros. `stretch_demos/nodes/grasp_object`, `stretch_funmap/.../manipulation_planning.py`. https://github.com/hello-robot/stretch_ros. 확인(코드).
  - 한 번 관찰한 뒤 고정 접근을 한다. 잡기 확인이 없다(반례로 인용).
- hello-robot/stretch_visual_servoing. `visual_servoing_demo.py`. https://github.com/hello-robot/stretch_visual_servoing. 확인(코드).
- HomeRobot / OVMM. arXiv 2306.11565, https://github.com/facebookresearch/home-robot. 확인.
- OK-Robot (2024). arXiv 2401.12202. 확인.
  - 개루프 경유점으로 접근한다. 오류 감지와 재시도가 없다는 점을 한계로 적었다.
- Boston Dynamics Spot SDK. `protos/bosdyn/api/manipulation_api.proto`, `robot_state.proto`. https://github.com/boston-dynamics/spot-sdk. 확인(proto 주석). 내부 제어기는 공개되지 않았다.
- Will, Grossman (1975). An experimental system for computer controlled mechanical assembly. IEEE Trans. Computers C-24(9). https://www.cs.jhu.edu/~rht/Miscellaneous%20Materials/IBM%20Mechanical%20Assembler.pdf. 확인.
  - 경계 이동(guarded move)을 다룬다.
- 조사 전문(영문, 출처별 수치 포함): [blind_final_approach_survey.md](blind_final_approach_survey.md)
