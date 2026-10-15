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
| `margin_common_mode` | `margin_common_mode_v1` | 같은 observation_epoch의 두 scalar 여유만 투영. clip[-.10,0]은 사용자 후보. 합 잔차 허용 .15m은 감사 .072+3*.027≈.153 후보. 양의/범위밖 잔차는 재관측. `min(corrected-error_bound)>=.04`를 `inside_margins_v1`에도 동일 적용. 구간 안이면 완료하되, 이동이 필요하면 기존 양끝 균형 목표 유지(아래 DEV2 재생 근거). |
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

## DEV1 중단과 직렬화 수정

소스 `4a1809e2584840499be48e7baff99024c8bd35c1`의 DEV1은 HOST_ERROR3,
동일 결함 감독중단3이다. sweep의 NumPy 좌표에서 나온 `numpy.bool`이
중첩 검사 원장에 남아 최종 JSON 저장이 실패했다. 첫 오류를 읽은 즉시
소유 실행에 SUPERVISOR_STOP과 SIGINT를 보냈으며 이미 종료한 실행은 건드리지 않았다.
최종 result/audit가 저장되지 않았으므로 완료 동작이나 `done` trace를 성공으로 복구하지 않는다.
초기 `running` result는 원본 그대로 보존하며 최종 감사0을 주장하지 않는다.

수정은 sweep의 수치 gap을 Python float로 만들고 따라서 판정도 Python bool이 되게
하는 것뿐이다. 실제 중첩 sweep 원장을 `json.dumps(..., allow_nan=False)`로 검사한다.
시작/끝은 비어 있지만 중간에서 막히는 얇은 벽 시험도 명시했다.
다음 DEV2는 같은6장면·같은 토글·새 source SHA로 처음부터 측정하고 DEV1과 합산하지 않는다.

## DEV2 중단과 경계 이동 목표 복원

DEV2 `f4f2994d39954c61ad8bf1d337c347d2f8f8cafb`:5회 제출·감독중단,
1회 제출 전 취소. DEV1 마지막 자기 scalar 보고를 같은 코드로 gcp1에서
재생한 결과110618은 보정 하한 .0379564m→최소필요 이동 .00204359m를
요구했다. 남은55.50 SIM초보다 회차+tail55.7752초가 커서 거부된다.
이는 최종 저장 실패로 가려진 **제어 재생 반례**이며 물리 성공/실패의 복구 집계가 아니다.
확인 즉시 제출기·소유 실행을 중단했다. 수정 전에 관문표에 반례·사유·최소틈을 추가했다.

보고서의 최소 필요 이동은 선택 적용안이다. 다음 관측의 경계 재보정을
유발하므로 이 추가 변경을 거두고 기존 양끝 균형 이동 목표를 유지한다.
이미 두 하한이4cm 이상이면 같은 목표 영역 판정으로 즉시 완료한다.
문턱·error_bound·여유 상수·회차/시간 한도는 바꾸지 않는다.
마지막 DEV3는 같은6장면·같은 후보이며 이후 추가 탐색은 하지 않는다.

## 최종 DEV3 — NOT_READY, 관문 대기열 없음

실행 SHA **`8d24a525fc3e2d480050dc08788befd8f3d4fde4`**, gcp1,
소유동시6·자기 제출 시 전체 최대22(한도40). 최종 **5/6**, 실패1,
cap_end/HOST_ERROR0. 앞선 두 라운드와 합산하지 않는다.

| seed | A (`release18_v1`) | B (`release19_v1`) |
|---|---|---|
|110622|성공, 총178.0 SIM초|`release_iteration_cap`,168.5 SIM초|
|88639|성공,131.0 SIM초|성공,126.2 SIM초|
|110618|성공,85.5 SIM초|성공,79.2 SIM초|

총 시간에는 마지막 평가 구간이 들어간다. 입력 감사6/6에서
`invisible_measurements=held_world_reads=control_top_camera_reads=0`이고,
검토 top도0이다. 이는 release 판단 구간이며 prefix까지 감사한 결과가 아니다.
최종 목표 영역 수용5건의 평가 라벨은 모두 fit(오수용0/5)이다.
학생 실행·학습 카메라 기록·데이터 수용·학습·실물 검증은 없다.

**남은110622 B:** 양측 반대 색 끝이 유지되는 처음/중간/끝12프레임
(0,32.3,65.3,99.3,132.3,165.3 SIM초)을 직접 봤다. 같은 끝 접근·상호 막힘은
보이지 않았다.120.6초 보고의 축 오차는 r1−5.65°, r2−12.10°인데
평가 전용 실제 빔 축 오차는−6.80°였다. 기존10° 축 관문이 r2 보고에
반응해 `axis_correct`를 선택했고,47.2초짜리 전체 회차를 소모했다.
167.8초에 필요한+.30m 축 이동은 세 회차 상한에 거부됐다.
최종 실제 end-center 최소 여유는 **−.0254536m**, 즉 영역 밖이다.
축 추정의 지도 heading/자기 명령 기억 기여는 아직 분리하지 않았다.
정답으로 제어 판정을 덮거나10°·18°·4cm·3회 한도를 바꾸지 않았다.

전체48/48 정렬은 완료했다. 전체 translation sweep 제약308/308 통과,
자기 RGB 근거2458/2458 원본 해시·JPEG decode 확인, 여섯 회의 양측72프레임을
직접 검토했다. 첫30 SIM초 wall/SIM 중앙2.053(6회,모델 호출0)이다.
새 yaw-budget 대안은 이 DEV3에서 발동0건이므로 물리 효과를 주장하지 않는다.
저장88639 특징·명령 단위 시험과 구분한다.

기본 회귀171개와 최종 release23 시험17개가 통과했다(중복14개).
171개는 개발 중 tree의 비물리 검사이며 고정 SHA의 물리 결과가 아니다.
최종17개가 검사한 관련 파일 바이트는 위 실행 SHA와 같다.
상세 명령·로그 해시는 `release23-validation.json`에 있다.

원본은 gcp1 `runs/r23d3-*-8d24a525`에 보존한다. Mac에는 분석 요약·몽타주,
실패 한 건의 선택12프레임만 회수했다. 원본 manifest6/6을 VM에서 전수 검증했다.
`release23-summary.json`, `release23-rejection_table.json`에 누적 funnel·거부 수·
물체/최소 틈·원본 경로·실행 가능한 재현 명령을 남겼다.
FOV 거부2건은 저장 자기 RGB/발행 명령의 명목 평면 투영으로 각각−1.312px,
−.703px를 재계산했으며 둘 다 회복된 사건이다. 물리 실패1건과 합산하지 않는다.
큰 전체 분석 JSON은 해시가 연결된 zstd 파일로 보존한다.

최종 저장 관측194개 비교에서 margin-only는 선택을 바꾸지 않았고,
leg-only는 축 이동110개의 크기를 바꿨다. 큰 경험적 error_bound가 공통 보정의
낙관적 수용을 상쇄한다. 이 오프라인 비교를 새 궤적 성공으로 해석하지 않는다.

**6/6 및 두 실패 seed 해결 조건 미달**이므로40회 관문 대기열을 생성하지 않았다.
3라운드 예산을 마쳤고, 추가 실행·예비 채우기·기존 성공률 승계·자동 승격은 없다.
소유 실행/예약/임대는 모두 정리했고 최종 소유 활성0을 확인했다.
다른 작업의 실행과 VM은 유지한다.
