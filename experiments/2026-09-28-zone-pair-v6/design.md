# v6 구현 결정과 검증 경계

다음 문서를 먼저 읽고 기존 RestingBeamTrack / PairSweepGuard / PairGraspRelook / STATUS를 확장했다.
설계의 좌표계 분리·loaded 제한을 새로운 성공 근거로 바꾸지 않는다.

- `/private/tmp/claude-501/-Users-changmin-projects-ugrp/ecd247bf-a1a7-45d6-9190-dad34be56468/scratchpad/codex-dev13-14-design.md`
- 같은 경로의 `codex-dev11-12-diag.md`
- `/Users/changmin/projects/ugrp-wt/codex-pair-parity/experiments/2026-09-27-zone-pair-parity/beam_frame_design.md`
- 같은 경로의 `loaded_stage_design.md`

## 상대 보고

`harness/zone_pair_relative.py`는 자기 RGB + 자기 발행 PWM + 고정 600×40×32 mm 형상만 읽는다.
빔 바디 색은 silhouette 후보를 분리하는 데 사용하고, 검은 band나 표식 ID/개수/좌표는 읽지 않는다.
양끝 경계와 catalogue 길이/폭, 여러 paired-edge strip의 일치로 새 resting anchor를 만든다.
전체 빔이 보이지 않거나 단안 평면·끝 구분이 모호하면 metric 상태를 0으로 채우지 않는다.

보고에는 frame/SHA/capture/segment/PWM, 상대 grip·yaw, 관측 가능한 축, sigma와 별도 bias bound,
endpoint 가설, resting/attached/unknown 사유, anchor 시각을 기록한다. 양끝이 같은 거리라 구분할 수
없으면 거부한다. 이름 붙은 물리적 end_neg/end_pos의 표면 ID는 관측할 수 없고 nearest_end를
자기 역할의 대칭 끝에 연결한다. 이 대칭 가정 밖 물체는 지원하지 않는다.

`RestingBeamTrack`의 command/time uncertainty 전파를 재사용한다. END_CLIPPED/BAND_CLIPPED는
기존 anchor에 들어맞는 visible patch라는 약한 제약만 주며 anchor age·sigma를 줄이지 않는다.
중복 JPEG는 새 측정이 아니고, camera/base 명령 이후의 이전 영상은 재사용하지 않는다.
prediction bound를 벗어난 빔 이동/association은 anchor를 폐기한다. bound 안의 이동은 남는
불확실도이며 검출 완료로 주장하지 않는다. 들린 빔에는 ground-plane metric fit을 적용하지 않는다.

`a+b`의 align residual은 기존 12 mm/8 mm/.035 rad와 2회 fresh streak를 상대 보고에 적용한다.
close 준비의 5 cm/3°는 상대 보고의 uncertainty+bias에 적용하고 전역 안전을 별도로 AND한다.
새 유효 absolute fix를 파지의 필수 신호로 요구하지 않는다. 이는 정책 변경이며 기존 gate와
안전 동등성을 입증한 것은 아니다. post-close/loaded receipt와 이동 gate는 보존했다.

## 전역 안전

`zone_pair_global.py`는 지도 PF 위치와 마지막 informative absolute fix에서 별도 command reachability
영역을 유지한다. 상대 보고를 인자로 받는 것은 stationary beam 형상을 world 벽에 대조할 때뿐이다.
상대 관측으로 global sigma나 fix age를 변경하는 API가 없다. command의 실제 이동을 확정하지 않고
gain bound·stop lag·경과시간·PF 평균 이동과 anchor의 차이를 영역에 포함한다.
PF 전체 가설의 반경도 반영해 평균만으로 여러 mode를 숨기지 않는다. 새 compact fix가 옛 reachable
영역 밖으로 뛰면 새 anchor로 받아들이지 않는다. 새 posterior 재획득의 독립 검증이 필요하다.

차체·팔·전체 정지/부착 빔은 기존 sphere/sweep geometry를 사용한다. 35 mm 기본 여유를 유지하고
오차가 커질수록 여유가 감소한다. .15 m/.20 rad 지원영역 밖은 sigma를 잘라 통과시키지 않고 거부한다.
통계 k=2는 검증된 95% coverage라는 의미가 아니다. entry fix가 없거나 30초를 넘으면 unknown이다.
아직 안전하지만 남은 여유가 40 mm 미만이거나 envelope sigma가 .10 m/.15 rad에 이르면 align에서
예방 relook을 요청한다. 이미 안전영역을 벗어나면 동작을 허용하지 않는다. 시선 후보의 충돌 여유도
원시 PF sigma 대신 같은 전역 envelope로 검사한다. 이 scheduling reserve 역시 개발 가설이다.
이 보수적 영역으로 인해 현재 낮은 팔 모델 편향이나 loaded 단계에서 수행 가능성이 작을 수 있다.

## 복구와 관측 품질

`owncam_recovery_v6.py`는 opt-in PF 확장이다. routine look는 같은 localizer 객체·입자·가중치·fix
시각을 보존한다. lost(미초기화/범위초과/정지 뒤 연속 잔차 불일치)에서만 최대 2회 요청,
요청당 최대 3개 frame의 20% 다중 yaw/관측 proposal을 허용한다. 전 posterior를 지우지 않는다.
초기 관측에 의한 bootstrap은 시작에만 별도다. 정지 gate·원시 명령 시각 계약을 보존한다.

검출 파싱 수용 `accepted`와 위치정보 획득 `informative`는 다르다. robust outlier floor, inlier 비율,
posterior support, 기하 curvature, 팔 settle 조건을 진단한다. invalid majority/포화 frame은 기존
posterior를 수축하거나 absolute fix 시각을 갱신하지 않는다. 실제 품질/정확도 calibration은 남는다.
dev13의 모든 feature -8.995732 및 dev14 3개 중 2개 floor를 자기 JPEG에서 재현한다.
설계 근거의 dev14 82.47 cm 오차와 1.896 cm sigma는 사후 진단 설명이며 제어 fixture에 GT를 넣지 않았다.

`expected_observability`는 PF 여러 가설에서 정적 벽/모서리 투영의 기하 구분력을 계산한다.
시선 이동 비용과 안전 여유로 점수를 낮춘다. marker ID/개수 조건이 없으며 점수 자체는 fix가 아니다.
occlusion/외관 변화와 calibrated information gain은 미검증이다. markerless fake provider는 같은 계약으로
검사하지만 실제 vision worker를 호출하지 않는다.

막힌 pan은 `PairExecution.arm_step`에서 큐 전체를 폐기하고 발행된 PWM으로 되돌린 뒤 재계획한다.
차단 방향은 해당 sweep에서 제외한다. 복귀 view가 막히면 align로 허위 복귀하지 않고 실패한다.
gate dwell만 남았으면 새 pan 없이 기다린다. 기존 8회/회당 8초/누적 40초와 원래 align deadline을
보존하고 pregrasp recovery에도 적용한다. fresh READY/같은 GO/상대 abort 큐 정리, 잡힌 뒤 일방 pan
금지, weld OFF, 카메라/FOV/외관/정상 물리, GT·접촉·관절측정·peer pose 금지 경계는 유지한다.

## 검증 해석

저장 checkpoint의 상대 보고 및 전역 safety unknown, production relook 상태 전이를 재생한다.
첫 새로운 action/view/receipt 이후는 unknown으로 고정한다. 과거 전체 영상은 새 controller의 완주
근거가 아니다. dev05–14 각 2 endpoint와 M2 49회/98 trace는 서로 다른 source의 진단 자료다.
별도 pytest는 포화·과신, blocked-pan cancel, dwell, 중복/명령후 영상, partial/moved/loaded,
markerless fake provider, dual close READY/GO/abort, 원시 시간 및 source boundary를 검사한다.
실행 로그와 남은 실패는 validation.json/테스트 로그에 적는다.
