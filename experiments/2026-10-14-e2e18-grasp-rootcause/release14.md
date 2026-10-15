# release14 — 선 특징 폐루프·후진 전 지도 여유·끝 띠 증거·기록 입력 경계

기준 `97942a8285b498a2e7896dc8dccc88e067b77cc7`, 측정 기록 `024d1ca4`.
`release13.md` 전체와 `outputs/e2e18-admin/gt-leak-audits/gt-leak-audit-97942a82.md`를 먼저 읽었다.
이 worktree의 `claude/grasp-act-probes`에서만 수정했다. PR #491의 head는 별도 브랜치다.
새 선택은 **`--release-profile release14_line_v1`**, 기본 `off`다. 기존 옵션 기본값·구형 제어 경로는 유지한다.
[진단 계획](release14-diagnostic-plan.json), [요약·해시](release14-summary.json),
[전체 저장 입력 재생](release14-replay.json.zst), [새 seed 검색 범위](release14-seed-audit.json).

## 변경과 표준 방법 적용

1. `sim/release14.py`의 선 IBVS: 기존의 양쪽 경계가 보이는 행 중심을 선으로 적합한 뒤
   정규화 영상의 `(rho, theta)`로 변환한다. 위치와 기울기 두 오차를 **함께** 푼다.
   고정 카메라 보정·발행 PWM FK·명목 높이 0.032 m에서 계산한 desired interaction matrix를 쓰며,
   현재 정답 깊이/자세·release13 실제 yaw를 넣지 않는다. 옆 이동 4 mm·yaw 0.025 rad 이하의
   결합 펄스를 내고 0.2초마다 새 자기 RGB를 확인한다. 바퀴별 최소 시간을 따로 올려
   결합 비율을 깨던 방식도 새 프로필에서는 쓰지 않는다.
   이는 알려지지 않은 구동 yaw를 다음 영상 오차로 보정하는 폐루프다. 실제 slip·yaw 결합계수 식별이나
   ViSP 전체 6-DOF 제어기를 이식했다는 뜻은 아니다. 명목 Jacobian·임계값의 실제 수렴은 미검증이다.
2. `slope=None`/잘린 선이면 **옆 이동은 0**, 영상 중심의 방향에 따른 작은 회전으로 방향부터 재관측한다.
   방향 미관측 탐색 누적 12도, 전체 명령 yaw 18도/옆 0.10 m, 16초 시한, 유효 선 무진척 3초의
   제한을 두고 넘으면 실패한다. 정답으로 방향을 채우거나 중심만 보고 집지 않는다.
3. 최초 놓기·열기·팔 올리기 뒤에는 후진 **전에** 제자리 자기 RGB panorama로 지도 위치를 추정한다.
   후진 방향은 rear 후보 0.15/0.10/0.05 m 중 기존 0.18 m 차체 여유와 위치 공분산 여유를
   만족하는 것을 고른다. 불명/벽 접근이면 옆으로 눈먼 우회를 하지 않고 제자리 재관측으로 간다.
   이후 재접근 전·후에 각 로봇의 열린 집게/hover에서 선 방향과 위치를 다시 맞추고 통과해야 닫는다.
   재접근 전체 명령 경로와 정렬 펄스도 정적 지도 여유를 검사한다. 자기 위치는 RGB 추정과 발행 명령만 쓴다.
   상대 바퀴·팔 명령이 바뀌면 정렬을 무효화한다. 재시도도 이 정렬기를 쓴다.
4. `sim/release_regrasp.py`: 새 프로필에서만 황록 몸통 **또는 맡은 끝 색**을 같은 화물의 영상 증거로 쓴다.
   기존 끝 색 장면 `grasp_act_teal_blue_v1`의 HSV(청록 70–90, 파랑 110–130)를 재사용한다.
   반대 끝 색은 인정하지 않는다. 순차 자기 시험 들기·3초 안정화·1초 연속 확인·복귀 유지·새 epoch ACK는 유지한다.
   접촉/정답 높이로 통과시키지 않으며 색 띠가 있다는 사실만으로 통과하지 않는다.

## 정답 누설 감사와 기록 경계

- 신규 프로필은 `commands + command_relative_v1 + hidden_v1 + global_localized_release_v1 +
  setdown_global_v1 + backoff_v3 + native_yaw_v1 + pad_window_v2 + own_rgb_lift_v1 + own_rgb_realign_v1`을
  검사한다. 잘못된 조합은 backend·prefix·출력 생성 전 거부한다.
- **기록 모드 가드:** `--record-training`/Python `record_training=True`를 명시적으로 받고,
  legacy anchor, held visible, truth comparison, 비 RGB placement/legacy lookaround를 거부한다.
  안전 구성도 현재는 **새 프로필 ≥38/40 관문과 학생 writer가 없으므로 명시 거부**한다.
  원래 이 release 러너에는 학생 기록 경로가 없었다. 이번 수정은 위험한 기록 요청의 묵시적 통과를 막는 것이며,
  실제 학습 기록 지원·관문 통과·ACT 데이터 생성 완료가 아니다.
- **선행 집기는 제외를 선택했다.** `observable_v2`와 정답 접촉/높이 유지 판정은 장면 준비용으로 보존한다.
  prefix의 명령/RGB는 학생 스트림으로 쓰지 않는다. `training-segments.json`과 result에
  `prefix.included=false`, 정답 판정 사유, 실제 시작/끝 시각을 명시한다. 현재 release 측정 행에도
  `training_eligible=false`를 붙인다. 평가용 prefix 검토 영상은 보존한다.
- `LookaroundLocalizer.make_plan/visible_fn_for`: static map 지형지물 + `own.x` + 발행 카메라 FK로
  볼 방향을 계산한다. 여기 자체에는 정답 빔 끝/축 입력이 없다. **legacy `--lookaround setdown_lookaround_v1`의
  위험은 호출자가 제공하던 truth+error anchor와 비 RGB observe**였다. 새 프로필/기록 가드는 이 조합을
  거부하고, 명령 원점에서 자기 RGB로 초기화하는 `setdown_global_v1`만 허용한다. 구형 기본값은 비교용으로 유지한다.
- 별도 **`--active-recovery setdown_lookaround_v1`**은 위 lookaround 옵션과 다른 경로다.
  `release_setdown_lookaround.script`는 발행 후진 궤적·`released_band` 명령 FK 기억과 RGB 지도 가설만 읽는다.
  ±90도 몸체 방향/팬 목록은 고정이며 정답 빔 끝/축으로 둘러볼 범위를 맞추지 않는다.
  `setdown_global_v1`의 `observe()`는 즉시 빈 scan을 반환하므로 legacy `pose_of/own_end_world/Eyes.classify`
  경로를 실행하지 않는다. 신규 스케줄러 시험에서 이 세 경로 중 perception 호출을 금지해 통과했다.
- `pose_of`, `look_truth`, `BandVisibility`, 접촉/성공 평가는 별도 평가 출력에 남는다.
  공용 top 영상은 기존 검토용 합성 저장에서만 쓰며 제어·선 특징·파지 증거에는 전달하지 않는다(#366).
  prefix를 포함한 러너 전체를 '정답 없음'이라고 표시하지 않는다.

## 저장 원본 오프라인 재생

`scripts/replay_release14.py`로 두 실행의 result/teacher 원장 **6/6 payload**를 manifest와 대조하고,
실제 사용 JPEG **151/151**을 입력 원장·manifest SHA256과 대조했다. 평가 접촉/높이는 이 스크립트의
제어 함수 인자가 아니다. 비교용 실제 보유 라벨은 release13의 별도 평가 결과다.

| 저장 실행·r1 시도 | 안정화 표본 | 기존→새 영상 판정 | release13 평가와의 관계 |
|---|---:|---|---|
| 74963 / 97942a82, epoch1 시도1 | 21 | no 21→no 21 | 빈 집게 반례 계속 거절 |
| 74976 / c9ba20a6, epoch1 시도1 | 11 | yes 11→yes 11 | 기존 보유 대조 유지 |
| 74976, epoch2 시도1 | 21 | no 21→no 21 | 미파지 계속 거절 |
| 74976, epoch2 시도2 | 21 | no 21→yes 21 | 청록 띠로 인한 미탐 해소 분기 |
| 74976, epoch2 시도3 | 21 | no 21→yes 21 | 청록 띠로 인한 미탐 해소 분기 |

74976 r2 epoch1의 기존 yes 11/11도 유지한다. r1에 한정한 선택된 개발 반례는 보유 3/3·미보유 2/2의
방향이 맞으며, 새로운 정확도/관문 성공률이 아니다. 두 색 띠 재시도의 복귀 유지도 yes지만
후속 새 행동·새 완료 상태를 검증한 것은 아니다.

74963의 43.3–48.5초 정렬 원본 **27/27**은 여전히 양쪽 경계 방향을 복원하지 못한다.
새 분기는 모두 `recover_direction`, 옆 이동 0, 작은 yaw 명령 후보로 바뀐다.
새 실행 전체는 이미 **첫 observe_back 14.9초**에 '후진 전 제자리 RGB 관측'으로 갈라진다.
따라서 43.3초 이후의 원본을 새 제어기의 궤적처럼 연결하지 않는다. 74976도 최초 분기는 14.9초다.
원장에 마지막 종료 틱이 없는 경우(74963 48.5초)는 직전 0.1초 내의 발행 PWM을 사용하고 그 시각을 남겼다.

직접 열람: release13 저장 배열본의 두 실행 각각 8시각×개요/r1/r2 = **48장**,
추가 74976의 82.1/83.5/89.9초 자기 원본 배열 **3장**, 합계 51장.
74963 1.8/10.1/16.1/23.1/29.1/35.1/42.1/48.1초,
74976 1.8/10.1/26.1/41.1/56.1/72.1/88.1/103.1초를 보았다(최대 간격 16초).
두 로봇은 반대 끝에 있고, 후반 청록 띠가 r1 중앙을 차지한다. 새 렌더나 동영상 전체 시청은 하지 않았다.

## 검증·큐·남은 일

관련 시험만 실행: `tests/test_release14.py tests/test_release_regrasp.py tests/test_grasp_act_release_run.py`.
**61 passed in 49.65s**. 로그 `outputs/release14/pytest.log`, 해시는 summary에 있다.
픽셀·선 Jacobian/혼합 펄스 산술·방향 상실 차단·벽 여유·기록 거부·실제 러너의 전후 정렬/ACK 상태 전이를 검증했다.
러너 시험은 시계만 진행하는 fake backend이며 실제 시뮬레이션/렌더가 아니다.
새 결합 보정의 산술 시험도 합성 feature-space 반례이며 물리 증거가 아니다.

새 큐는 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-release-gate-<실행SHA8>.json`에
별도로 만든다. 실행 SHA는 최종 push HEAD로 고정하고, 별도 GCP launcher가 source worktree HEAD를 읽으므로
조정자는 제출 직전에 큐 SHA·HEAD·원격 SHA·plan hash를 대조해야 한다.
재현 **74963·74976(개발 분모 2)** → 검토 → **76000–76006(새 진단 분모 7)** 순서다.
main과 열린 PR 22개 head, 로컬 VM3 큐에서 새 7 seed 사용 흔적 0건이다. 원격 실행 이력은 조정자 점검이 남는다.
`coordinator_approval.approved=false`, 모든 `ready=false`, **관문40 미승인·미등록**이며 자동 승격하지 않는다.
기존 큐는 수정하지 않는다. 실행 예산은 9×96 MiB, 공용 자원·디스크·유휴/상한 장치는 제출 전 점검한다.

Mac 물리·시뮬레이터 렌더·원격 제출·모델 호출 0. 새 물리 효과, 새 7개 시드 결과,
관문40, 학습 RGB writer/기록 인수는 미검증/미완료다. 이전 결과와 합산하지 않는다.

## 참고 자료

- Chaumette & Hutchinson (2006), [Visual Servo Control, Part I: Basic Approaches](https://dl.icdst.org/pdfs/files3/614363efffef5c72b787d9dc35f0cca2.pdf),
  pp.82–84의 특징 오차·interaction matrix·desired matrix 근사와 안정성 한계 부분을 확인했다.
  [저자 설명](https://faculty.cc.gatech.edu/~seth/res.php?u=vs)으로 서지를 대조했다.
  이 방법을 2개 차체 자유도로 제한하고 고정 카메라 FK에서 수치 미분했다. 전역 수렴을 주장하지 않는다.
- Espiau, Chaumette & Rives (1992), [A New Approach to Visual Servoing in Robotics](https://www-sop.inria.fr/members/Patrick.Rives/Publications/ITRA-espiau-chaumette-rives-92.pdf),
  IEEE TRA 8(3):313–326, DOI 10.1109/70.143350. 저자 PDF와 검색 추출의 선 `(rho,theta)` 표현을 확인했다.
  **스캔 PDF 전체·해당 행렬 수식의 직접 판독은 미확인**이다. 아래 공개 구현의 명시 수식을 함께 확인했다.
- ViSP [vpFeatureLine.cpp](https://github.com/lagadic/visp/blob/master/modules/visual_features/src/visual-feature/vpFeatureLine.cpp),
  `interaction`/`error`/`buildFrom`의 두 선 특징과 `x cos(theta)+y sin(theta)=rho`를 확인했다.
  위치·방향을 함께 쓰되, 이번 코드는 현재 target의 3D plane을 요구하지 않는 고정 명목 desired Jacobian으로 제한한다.
- [Visual dead-reckoning for motion control of a Mecanum-wheeled mobile robot](https://www.sciencedirect.com/science/article/pii/S0957415803001156)
  (Mechatronics 14(6), 2004, 623–637): 초록·서론의 x/y/회전 관측 폐루프와 옆 구동 불일치 문제를 확인했다.
  센서는 optical mice이므로 자기 RGB라는 우리 입력과 다르다. 상세 실험/제어 이득 원문은 미확인이다.
- Killpack et al. (2010), [Visual odometry and control for an omnidirectional mobile robot with a downward-facing camera](https://scholarsarchive.byu.edu/facpub/3222/):
  저자 저장소 초록에서 영상 추정 기반 옆 이동·외란 보정 폐루프를 확인했다. 우리 카메라를 아래로 재배치하거나
  해당 성능 수치를 가져오지 않았다. 본문 알고리즘 재현은 하지 않았다.
