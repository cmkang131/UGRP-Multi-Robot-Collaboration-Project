# 기준 B 회전 후보 추가 — 훈련 적합, 검증 전

기존 B에는 회전(yaw) 후보가 없어서 회전 판정이 계속 null이다. 2026-10-03 코디네이터의
위임 결정에 따라 **훈련 자료만으로 새 r5 회전 후보를 만들었다.** B의 문구·문턱,
r4 파일과 전진·측면 값, 기존 검증기 바이트는 보존했다. 원래 B/r4의 회전 null은 바뀌지 않는다.

**v91 held-out 원자료는 이 작업에서 열람·해시·계산하지 않았다.**
아래 두 파일은 코디네이터가 채점 전 공개 고정(pre-scoring commitment)에 사용할 대상이다.
v91은 이미 수집됐으므로 이번 공개를 수집 전 등록이라고 표현하지 않는다.

| 고정 파일 | SHA-256 |
|---|---|
| [회전 부록](consumer_criterion_B_rotation.json) | `6129f144c840510535de053ffcce325ef934e8192c6adf777b2df8d976f5da08` |
| [r5 yaw 후보](calibration_candidate_r5_yaw.json) | `978727fcacc5e368efe2a0fdf6d9d8dc3756573c41e896e06ba11d78cf86fb97` |

두 값은 [SHA256SUMS](SHA256SUMS)에도 기록했다. 후보는 **CANDIDATE_UNVALIDATED**다.
세 축의 `axis_validation`과 활성 `params.motion`은 null이며, 학생 제어기에 적용하지 않는다.

## 사용한 자료

- v89: r4의 `input_manifest_r4.json`에 있는 네 파일을 실제 해시와 대조했다.
  turn 명령이 0개라 회전 적합에 들어간 창도 0개다. 전진·측면은 다시 적합하지 않았다.
- v88: `/Users/changmin/projects/ugrp/outputs/final-pair-v88-cal-747d2b9f-20261001/calibration-unloaded`
  중 `zone_wide_two_doors_final_v3`의 r1 무하중 자료만 썼다. 수집 소스는
  `747d2b9f1eb43e21804ccef58fff4db241d1a844`다. 상대 SIM 시각 242–326초에
  ±0.01/±0.02/±0.03 계단(step) 6개와 각 정지 구간(coast), ±0.02 의사난수 이진 명령(PRBS)
  31칩 및 마지막 정지 구간이 있다. 양수 turn 760 tick, 음수 750 tick이다.
- 수집 완료 기록, 지도·하중·소스, 일정과 발행 명령, lease, 0.05초 pose 시계·순번·회전행렬을
  확인했다. 읽은 원자료는 계산 뒤에도 같은 해시인지 확인했다. 총 9개 고유 입력 파일의
  경로·크기·SHA-256은 [입력 명세](input_manifest_r5_yaw.json)와 부록에 있다.
- pose·명령의 시간 키는 `t`다. 실제 frame의 시간 키는 `sim_time`이다(#358).
  이번 yaw 적합은 pose·명령만 필요하므로 frame·이미지·카메라 라벨을 읽지 않는다.

## 적합 방법과 결과

평균은 r4와 같은 부호 공통 이득(gain), 주행 시간상수(run tau), 정지 시간상수(stop tau)의
3개 값이다. 0.05초 끝 속도 오일러 적분(end-velocity Euler)을 사용했다.
모든 계단·PRBS·정지 구간에서 0.2/0.5/1/2/3/3.2초 창을 만들고 구동 성분의 끝점 오차를
동일 가중 최소제곱으로 맞췄다. 범위·초깃값·최적화 종료 조건은 r4와 같다.
속도는 기록 처음에 0이고 발행 명령으로만 누적한다. 측정 속도나 접촉을 예측 입력으로 쓰지 않는다.

| 회전 값 | 결과 |
|---|---:|
| gain | 1.0725221565695355 |
| 주행 tau (s) | 0.16770868665607128 |
| 정지 tau (s) | 0.03736721159765567 |
| 최저 훈련 2σ 포함률 | 95.0106157113% (895/942) |

최적화는 수렴했고 자코비안 계수(rank)는 3, 범위 경계에 닿은 값은 없다.
식별 조건이 부족하거나 최적화·rank·경계 검사에 실패하면 적합기는 후보를 null로 남긴다.

잡음은 기존 `sigma_velocity = noise_rel*abs(v_next) + noise_abs`다.
회전 프로필의 `[forward,left,yaw]` 값은 다음과 같다.

- 상대 잡음: `[0.3176, 0.4438, 0.1116]` — M1 하한과 같다.
- 절대 잡음: `[0.01538, 0.00504, 0.015461140772925479]` (m/s, m/s, rad/s).
  회전 성분만 M1의 0.01406에서 늘었다. 확대 전 최소해는 0.015461140771925478이고
  수치 여유 1e-12를 더했다. **r4 전진·측면의 기존 잡음 벡터는 그대로다.**

B의 사전식 최소화(lexicographic minimisation) 순서는 상대 잡음 세 값 → 절대 yaw →
절대 forward → 절대 left다. 회전 중에는 전진·측면 평균이 0이어도 잡음 좌표계가 회전한다.
따라서 각 창의 위치 분산은 `Vx=C*abs_x²+S*abs_y²`, `Vy=S*abs_x²+C*abs_y²`로 계산한다.
C/S는 각 tick **이전** heading의 cos²/sin²에 dt²를 곱한 합이다. forward를 최소화할 때는
뒤 순서인 left가 커질 수 있음을 반영한다. r4의 병진 전용 최소화 함수를 회전에 그대로 쓰지 않았다.
마지막에는 기존 검증기의 전체 공분산 계산으로 모든 그룹·성분의 95% 포함률을 다시 확인했다.

| 예측 시간 (s) | 계단 창 수 | 계단 yaw 2σ 포함률 | PRBS 창 수 | PRBS yaw 2σ 포함률 |
|---:|---:|---:|---:|---:|
| 0.2 | 1302 | 100% | 357 | 100% |
| 0.5 | 1266 | 100% | 351 | 100% |
| 1.0 | 1206 | 100% | 341 | 100% |
| 2.0 | 1086 | 100% | 321 | 100% |
| 3.0 | 966 | 100% | 301 | 100% |
| 3.2 | 942 | 95.0106% | 297 | 100% |

전진·측면 오차 성분의 포함률은 모든 그룹에서 100%다. 제한 그룹은 계단 3.2초의 yaw이며
`p95(abs(error)/sigma)=1.9999999996663158`이다. 전체 수치, 1σ 포함률과 NEES는
[훈련 보고서](training_report_r5_yaw.json)에 있다. 겹치는 창의 포함률은 독립 표본의 보증이 아니며,
이 결과는 held-out 검증·입자 필터(PF) 사후분포·실제 임무 성공을 뜻하지 않는다.

## 후속 검증 범위

held-out은 `zone-final-pair-v91`, 소스 `04043e274af7351f3d35cb6be77d948cac1b8c6a`의
corridor와 door-geometry **두 지도 무하중 자료**다. B와 같은 시간·성분·창·판정 규칙을 쓴다.
모든 지도·사례·계단/PRBS·시간·성분에서 정규화 절대오차 p95 ≤ 2와 2σ 포함률 ≥ 90%를
모두 요구한다. 빠진 축은 null, 하나라도 검증 실패면 전체 false다. 검증 자료로 재적합하지 않는다.

[후속 연결 설계](SCORING_HOOK.md)에 공개 해시 확인, r5 읽기, 기존 수치 함수 재사용,
원래 B/r4 결과와 부록 결과의 분리를 적었다. **#356 병합 뒤 별도 PR에서 구현한다.**
현재 #356 브랜치·로더·제어기는 수정하지 않았고 실제 v91 채점도 수행하지 않았다.

## 검증과 재현

적합 소스를 먼저 `0ca27b1e`에 커밋한 뒤 실행했다. Python 3.13.5, NumPy 2.4.4,
SciPy 1.17.1이며 새 환경이나 패키지는 설치하지 않았다. 합성 자료에서 실제 소비자 메서드의
yaw 파라미터 복원, r4 목적함수 동등성, 공분산 검산, 최소 잡음을 낮추면 포함률이 깨지는 반례,
회전 좌표 결합, 식별 실패/null, 허용 경로 밖 접근 차단과 기존 값 보존을 검사했다.

```text
새 회전 합성 검사: 18 passed in 1.30s
관련 회귀 검사: 141 passed in 4.32s
```

[로그](related-tests.txt)·[JUnit](related-tests.xml)과 [36개 기존 파일 보존 확인](preservation.json)을
남겼다. `.github/workflows`, 실행 번들·워크플로 번호를 바꾸지 않았다.
물리·렌더·모델 호출은 모두 0회다. raw는 로컬 보존이며 원격 백업으로 표현하지 않는다.

```sh
python3 -m scripts.fit_consumer_criterion_b_rotation \
  --output /Users/changmin/projects/ugrp/outputs/critb-rotation-NEW
python3 -m pytest -q tests/test_consumer_criterion_b_rotation.py \
  tests/test_consumer_criterion_b.py tests/test_unloaded_consumer.py \
  tests/test_unloaded_hammerstein.py tests/test_review_346.py
```

적합 CLI에는 임의 raw 인자가 없다. 지정된 두 훈련 경로만 허용하며, v91 경로나
훈련 자료의 심볼릭 링크를 허용하지 않는다. 새 출력 폴더를 사용하고 기존 산출물을 덮어쓰지 않는다.

TensorBoard 새 snapshot `1003-r5-yaw-training`의 **12 runs·132 scalars·HParams 12개**를
다시 읽고 기존 서버의 실제 값과 대조했다. r4 훈련 기준선과 함께 보는
[대시보드](http://127.0.0.1:6006/?runFilter=%5E%281003-r5-yaw-training%7C1001-v89-consumer-r4-final%29%2F&smoothing=0#timeseries)와
[고정 카드·열·검증 기록](tensorboard_record.json)을 남겼다. 신규 영상은 없다.
서버 공용 logdir는 HTTP로 확인했으며 서버·프로세스는 변경하지 않았다.
Chrome 연결은 브라우저 표면이 없고 `cgWindowNotFound`로 실패했다. 따라서 고정 카드와
HParams 열의 **화면 확인은 미완료**다. PID/명령 조회도 sandbox가 거부했다.

남은 일은 독립 검토·PR CI, 코디네이터의 두 해시 공개, #356 병합 뒤 연결 구현,
그 후 별도로 승인된 v91 채점이다.

## 참고 자료

- Thrun, Burgard, Fox (2005), *Probabilistic Robotics*, ch. 4–5 —
  [저자 자료](https://robots.stanford.edu/probabilistic-robotics/).
  r4와 같은 확률 운동·과정 잡음의 배경이다. 이 실험의 수치 문턱과 적분·적합법은 프로젝트 B에 고정돼 있다.
- [r4 방법과 기존 B](../2026-10-01-final-env-v87-calibration-fit/README.md),
  [고정 B JSON](../2026-10-01-final-env-v87-calibration-fit/consumer_criterion_B.json)
- [#356 v91 검증기](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/356),
  [#358 실제 프레임 시계](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/358)
- [회전 적합기](../../scripts/fit_consumer_criterion_b_rotation.py),
  [합성 검사](../../tests/test_consumer_criterion_b_rotation.py)
