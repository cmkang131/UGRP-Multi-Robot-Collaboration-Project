# release23 — 시간·여유 결함 수정 후보 (2026-10-15)

기준 `508fa59a` (release21 실행 `46afd8b0`) 위의 **새 교사 버전**이다.
release21 A39/40·B39/40, rel22rec 44/50을 승계·합산하지 않는다.
조사 원문은 기본 checkout의 `outputs/e2e18-admin/research/release.md`이며
방법 1–3순위를 그대로 적용한다. 전역 정답은 아래 오프라인 잔차/평가만 읽는다.
들기 확인 묶음, 4cm 수용 문턱, 18° absolute yaw cap, 180 SIM초 cap,
weld OFF, 카메라/FOV, 학생 입력을 보존한다. 학습 카메라 기록은 OFF다.

## 먼저 산출한 원본 분포

`release23-baseline-rejections.json`이 수정 전 거부표/funnel이며 재현 명령과
원본 해시 목록의 원격 위치를 포함한다. gcp1에서 `analyze_release23_baseline.py`로
release21 80회와 rel22rec 88639를 읽었다. 이 81회는 독립 코호트가 아니다.
실패 종료는 cap_end2(같은110622의 A/B), motion_cap1(88639)이고,
FOV 막힘4 이벤트는 회복된 사건이다. 따라서 가장 큰 미해결 종료 원인인
시간·회차 경로부터 고친다. rel22rec 학생 원장은 scalar report를 보존하지 않아
그 실행의 관측 잔차를 채워 넣지 않았다.

- 같은 회차 localized 보고194쌍/388끝. `S(theta)=W-.60*mean(abs(cos(theta_i)))`.
  공통 보정 뒤 평가 전용 실제 end-center 여유와의 절대 잔차 최대
  **0.04704375885875689m**를 고정 `error_bound`로 쓴다.
  p95 .02680649, p99 .03584853m. 상관 표본의 경험적 최댓값이며 확률 보장이 아니다.
- 보정 영역 안의 표본194/194, bound를 뺀 lower 판정의 오수용0건.
  이것은 저장 관측 판정이며 새 궤적 성공이 아니다.
- 완료 회차115개의 higher p95 **48.29999999885786 SIM초**.
  .30m 후보의 추가 .10/.129 이동분을 더해 **49.07519379730747초**.
  마지막 완료 판정 이후 tail 최댓값 **6.699999999843726초**를 함께 남긴다.

## 독립 기본 OFF 토글

| 인자 | ON 값 | 근거·동작 |
|---|---|---|
| `margin_common_mode` | `margin_common_mode_v1` | 같은 observation_epoch의 두 scalar 여유만 투영. clip[-.10,0]은 사용자 후보. 합 잔차 허용 .15m은 감사 .072+3*.027≈.153 후보. 양의/범위밖 잔차는 재관측. `min(corrected-error_bound)>=.04`를 `inside_margins_v1`에도 동일 적용. 최소 필요 이동 구간에서0에 가장 가까운 이동 선택. |
| `release_leg_budget` | `release_leg_budget_v1` | .20→.30m, 5→3회. 감사110/110포화·최대시작거리.797m 근거. 남은 SIM 시간이 회차p95+tail보다 짧으면 재파지 전 cap_end. 발행 전체 translation sweep을 실행 직전 검사. |
| `lateral_rate_cal` | `lateral_rate_cal_v1` | 감사 .08*1.515=.1212와 별도 pair .123에 맞춘 .122m/s. axial .129, yaw_cal1.05 보존. lateral 계획·teacher belief·issued pose·localizer 전파가 동일 effective profile 사용. |
| `release_yaw_budget` | `release_yaw_budget_v1` | 다음 펄스가18° cap을 넘으면 lateral-only 개선 후보를 map/FOV/잔여예산으로 검사. 없으면 기존.3초 안정창에 해당하는 fresh RGB3장을 얻고 정확한 사유로 중단. cap 초기화·완료 문턱 완화 없음. `settle_pulse.proportional_pulse` 재사용. |
| `release_plan_budget` | `compute_budget_v1` | 기존 global matcher와 정렬은 유한 검사/SIM deadline이며 wall deadline 없음. 새 sweep은 로봇별2형상×(정적장애물수+경계)의 계산 예산을 계수·감사. 대안 수도 유한. 새 후보에서 ON. |

추가 수용 상수를 발명하지 않았다. sweep은 기존 .18m 로봇 envelope,
max(.02,2σ) halo, 고정 .60×.04m 빔 치수와 각자 RGB map pose/명령 FK를 쓴다.
translation 전체의 convex hull과 모든 정적 keepout/경계를 SAT 검사한다.
회전은 별도 기존 축 회전 검사 경로이며 translation으로 근사하지 않는다.
제어 모듈은 simulator/held-world/측정 관절/접촉을 읽지 않는다.
거부 원장에는 범주·물체 이름·최소 틈과 단위를 기록하며, 과거 이벤트가
수치 틈을 보존하지 않은 경우 null과 unknown 사유를 남긴다.

## 검증과 실행 예산

비물리 회귀171개 통과, release23 시험16개 통과(중복14개는171개에 포함).
release21 고정 함수와 OFF의 명령·trace·결과 비교, 비대칭 반례
실제[-.01,.81]/관측[-.02,.68], 잘못된 epoch/치수/잔차, 새 lateral 역계획과
전파 일치, 경로 중간의 얇은 벽, yaw88639 저장 특징·명령을 시험했다.
Mac에서는 물리·모델 호출을 하지 않는다.

`release23-dev6-plan.json`: 원본 장면110622 A/B, 88639 A/B, 성공110618 A/B.
첫 제출은110622 A,88639 B다. 동일 입력·동일 후보로 최대3라운드,
소유동시≤6·gcp1전체≤40, 회당96MiB/총576MiB, 학습RGB OFF.
실행 전 source를 커밋하고 매 라운드 rejection_table 파일을 먼저 만든다.
토글별 효과는 독립 OFF/ON 저장 관측 비교와 구분하며 묶음 DEV의 성공을
개별 토글의 인과 효과로 주장하지 않는다.

6/6 및 두 실패 seed의 A/B 해결·원본/입력감사/프레임 검토를 확인한 경우에만
새 A40/B40 대기열을 만든다.110622,88639 우선, 나머지 동일39개 기존장면
중 마지막을88639로 대체한 총40 unique scene이다. A/B는 별도 n/40,
동시16·전체≤40, full source SHA·실재 rejection_table 경로·해시를 담는다.
대기열은 검토용으로 비활성화하며 관문 실행/학습/기록 승격과 구분한다.
