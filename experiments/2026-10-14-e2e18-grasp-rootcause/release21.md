# release21 — FOV 최소 펄스 거부 뒤 유한 대안 (2026-10-15)

기본 off `release21_v1`(API/CLI `release21`/`--release21`)은 release20 정착 위에만 켠다.
A=release18+release20+release21, B=동일+release19 완료 look 대기 재사용이다.
최종 판정과 직접 실행 결과는 아래에 추가한다. 이전 release20 결과와 합산하지 않는다.

## 원인과 입력 경계

release20 실행 SHA `e897b0c2c96ad99cb0a3f5eb3cc255d2686bba09`의 seed110618 A,
r1 첫 정렬 world_t31.4에서 끝 띠 bbox `[205,65,409,309]`, 안쪽 FOV 여유1px였다.
rho=.02740395는 기존 허용.025 및 .6δ=.01981682를 넘어 최소 펄스가 필요했다.
그 펄스의 명령 적분은 `[forward=0,left=.0016,yaw=-.021]`이고 FOV를 넘는다는 이유로
`release20.py → release17.py`가 대안 없이 `fov_no_safe_translation`으로 끝났다.
저장 자기 RGB 특징·발행 PWM만 fixture로 분리했다. 전체 정답은 fixture/복구 판단에 넣지 않았다.

운영자의 18:04–18:06 기록에서 정지 전 완료 성공 A14/14·B13/13 이후 결함이 발견되어
같은 코드의 A/B가 정지됐다. 이 숫자는 관문 통과나 최종 전체 성공률이 아니다.
원본: `gcp1:/home/ugrp/ugrp-sim/runs/r20ag-18-e897b0c2/raw`.
운영 기록: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/ops-log.md:1834,1878`,
정지 기록: 같은 디렉터리 `stop-release20-e897b0c2-20261015.json`.

## 동작

양자화 후 FOV 거부 및 상속된 후보 없음 두 경로에서 순서대로 다음 대안을 시도한다.
각 대안은 정렬 인스턴스 전체에서 최대2회이며 성공 영상·모드 전환으로 횟수를 초기화하지 않는다.

1. 몸 정지, 열린 hover에서 팬6/손목 틸트3을 최대120 PWM(10.8°) 바꾸어 띠의 안쪽 여유를 늘린다.
   자기 RGB 꼭짓점·고정 K·발행 PWM의 nominal FK/기존 .032m 평면으로 후보를 예측한다.
   .8초 대기 후 **새 자기 RGB**로 원래 거부된 펄스를 다시 검사하고 안전할 때만 발행한다.
   같은 카메라 자세에서 이동 뒤 새 RGB로 기존 yaw 부호 검사를 먼저 한다.
   이후 원래 hover를 복원한다. 두 .8초 대기는 스케줄 예정 시각이 아니라
   새 발행 PWM 이력의 실제 나이를 요구한다(이력 없으면 일치 명령 확인 뒤부터 잰다). 카메라 이동 중 정착/집기를 허용하지 않는다.
2. 짧은 후진 한 펄스(명령 모형 약12.9mm)를 기존 FOV·지도·누적 이동 상한 안에서 발행하고 다시 본다.
3. 원래 거부된 방향의 반대 최소 펄스 중 띠의 안쪽 여유가 늘고 기존 안전 검사를 통과하는 것만 발행한다.
   다시 새 RGB로 기존 양자화 정착을 시작한다. 대안이 소진되면 원래 실패 인계로 끝난다.

복구 뒤 정착 이력을 초기화한다. 원래 hover·새 영상 .3초 안정·16초 정렬 상한·180초 에피소드 상한,
자기 RGB 지도 clearance·10cm/18° 누적 이동 상한을 유지한다. 시간 상한을 연장하거나 안전 거부를 우회하지 않는다.
`sim/settle_pulse.py`의 δ/.6δ/실제 명령 뒤 연속3회 반전 수용은 변경하지 않았다.
상속 `release20.LineAlign`에는 기존 반환값과 동일한 기본 hook만 추가했다.
토글 off에서는 release20 경로·원장/명령을 유지한다. 별도 `review_top=off`로 평가용 top 촬영도 막는다.

## 다른 종료 경로 조사

관련 release14–20와 regrasp recovery를 범위 검색했다(저장소/원격 브랜치 전체 검색 없음).

| 위치 | 경로 | 처리와 근거 |
|---|---|---|
| release20.LineAlign.choose_step | quantized pulse FOV 거부 | 110618 A 원본1건 재현; release21 대안 연결 |
| release17.line_step:150 | 안전한 연속/8방향 펄스 후보 없음 | 같은 `fov_blocked` 결과를 release21 대안에 연결 |
| release15.line_step:195 / tick:251 | 이전 프로필의 동일 거부 | release21 미선택 경로; 이전 프로필 결과를 변경하지 않음 |
| release17.tick | shaft 미관측1초, 회복 무진전2회, 모드 무진전3초 | 별도 결함 수치 미확인; 안전 거부 유지 |
| release17.tick | 16초 timeout,10cm/18° cap, map clearance, yaw sign mismatch, PWM 변경 | 복구 예산/입력 무결성 상한으로 유지; 완화 근거 없음 |
| release14 / release_regrasp_recovery | 방향 탐색/정렬/카메라 모델/지도/상한 실패 | legacy 별도 경로; 이번 최소 펄스 FOV 결함 근거로 확대 수정하지 않음 |

후속 직접 원본에서 경로별 발생 수를 다시 센다. 이전 관문의 강제 정지/미완료를 성공으로 세지 않는다.

## 직접 GCP 계획과 보존

`release21-dev6-plan.json`: 110618 A/B,110613 A,74976 B,78526 B,110600 A.
기존 관문/진단 에피소드 입력을 복사했고 batch만 구분했다. 각180 SIM초,동시 최대6,최대3라운드.
실행 전 코드 커밋, **push 전 run-first**, 각 라운드 같은6회, 라운드 간 합산 금지.
자기 RGB만 기록,학습RGB off,모델 호출0,정답/held/input 감사0/0 유지.
gcp1 공용 admission.lock 아래 실제 Python 실행·다중 워커 예약·임대를 합쳐≤40 및 자체≤6을 확인한다.
프로젝트 `ugrp-act-train-1014`,기존 `ugrp-sim-gcp1/n4-highcpu-64`만 쓴다.
8h STOP·20분 유휴·budget-stop 유지. budget-stop 발동 시 제출/재시작하지 않는다.
첫30 SIM초 원장/자기 RGB 및 분포를 확인한다. 실패는 처음/중간/끝 최소6시각×r1/r2를 직접 본다.
알려진 제어 결함 확인 즉시 같은 결함의 자기 진행 실행을 SIGINT하고 원본을 보존한다.
원본은 GCP 영속 디스크,Mac은 텍스트/요약/해시/선별 프레임만 이 worktree의 `outputs/release21/`로 회수한다.
예산96MiB×6×최대3=1728MiB 원격,로컬 선별 회수≤96MiB 목표. 요약/원장/해시 영구 보존,
DEV 미디어는 PR 열린 동안 보존. 전체 raw/별도 백업은 회수하지 않는다.

관문 큐는 기존110600–110639 바이트/해시를 유지해 A40/B40을 처음부터 측정하도록 준비한다.
선행 진단110618 A/B→110613 A를 분리한다. 자체 확인이 전부 성공이어야 `PREPARED_NOT_APPROVED`,
그 외 `BLOCKED`. 승인/준비/제출/실행 플래그는 전부false다.

## 참고 자료 — 열람 범위와 구현 구분

Chaumette & Hutchinson, [Visual Servo Control Part I: Basic Approaches](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf),
IEEE Robotics & Automation Magazine 13(4),82–90,2006,DOI10.1109/MRA.2006.250573.
pp82–83의 영상 특징/interaction matrix 구성과 p87의 PBVS에서 특징이 FOV를 떠날 수 있다는 설명,
pp88–89의 국소 수렴/극소점 논의를 2026-10-15 원문으로 확인했다.
이는 영상 오차 감소만으로 가시성이 보장되지 않는다는 배경이다. 이 문헌이 여기의
팬/틸트→후진→반대 펄스 순서,2회,.8초,.6δ 또는 수렴/물리 성공을 보증한다고 주장하지 않는다.
해당 수치와 임시 카메라 복원은 이번 구현의 유한 복구 설계이며 직접 GCP 검증 대상이다.

## 비물리 검증

관련 시험 `test_release21/test_settle_pulse/test_release17/test_release18/test_release19`: **82 PASS,23.44초**.
Mac 물리/렌더 없이 실제 저장 특징의 거부 재현,재중심/복원 스케줄,대안 순서/각2회 상한,
지도/이동 상한 거부,새 RGB 필요,release20 off의 명령/teacher 원장·판정 동등성,top0을 확인했다.
원본 fixture의 result/양쪽 teacher 압축 및 복원 SHA-256을 기존 manifest와 모두 대조했다.
첫 실행의 pytest 임시 경로 부모 누락 및 동등성 테스트의 Git/top wrapper 스텁 충돌은 테스트 설정에서 수정했고,
최종 전체 관련82개를 단일 pytest로 다시 통과했다. 새 물리 성공을 뜻하지 않는다.

## 다른 종료 경로의 숫자 근거

`release21-prior-path-audit.json`은 지정 release20 운영 보고에 있는 회수 가능 원본27개를
각 result/양쪽 teacher의 압축/복원 manifest로 검증했다. 그 범위의 정렬73개에서
`fov_blocked`/`release17_fov_no_safe_translation`은 **1건(110618 A)**이고 다른 정렬 실패0건이었다.
27개는 성공20·비성공/중단7이며 운영자의 정지 직전 성공 스냅샷 A14/B13의 전체 회수 집합이 아니다.
이 숫자를 과거 관문 최종 성적이나 release21 성공률로 합산하지 않는다.
최초 release20 실패의 자기 RGB6시각×r1/r2=12장도 직접 확인했고 서로 다른 색 끝을 유지했다.

## 1라운드 b75b130f — 코드 감사로 은퇴

자연 완료3/6(110618 A/B,110600 A 모두 성공),감사 후 직접 정지3/6(110613,74976,78526),
HOST_ERROR0. 종료 코드130·SUPERVISOR_STOP·원본을 보존하고 **1라운드 결과는 합산하지 않는다**.
110618 A에서 원래 world_t31.4 FOV 거부가 재현됐고 재중심1회/보정1펄스 뒤84.5 SIM초에 성공했다.
재중심 새 자기 RGB bbox는 `[162,96,363,383]`,안쪽 여유32px였다.
그러나 직접 보정 펄스의 yaw sign check는 해당 펄스 직후가 아니라 뒤의 정렬 펄스에서 수행됐다.
코드 감사로 이를 확인한 즉시 같은 소스의 진행3개를 SIGINT했다(서로 다른 PID를 직접 대조).
`outputs/release21/stop-release21-round1-*.json`과 원격 실행별 SUPERVISOR_STOP.json에 기록했다.

2라운드 수정은 보정 뒤 카메라를 유지하고 새 RGB로 원래 yaw sign 기준을 적용한 뒤 복원한다.
반대 yaw도 같은 pending 검사를 준비한다. 부호 반전/관측 없음이면 기존 거부로 끝나며 정착할 수 없다.
카메라 대기는 자기 발행 명령 이력 나이≥.8초를 요구한다. 스케줄 호출 다음 tick에 명령이
발행되는 시간 차이를 대기 완료로 세지 않는다. 정렬16초/에피소드180초 상한은 유지한다.
관련5파일 **83 PASS,25.70초**. 같은 카메라의 정상/반대 yaw 검증과 발행 나이 .7초 거부를 추가했다.

1라운드 원본6개 전부 VM SHA256SUMS/로컬 lite/압축 복원 해시를 검증했고,
각6시각×r1/r2=72장을 직접 봤다. 최대 시각 간격25초 미만이며 서로 다른 끝을 유지했다.
상세6개 성적·pulse/반전·입력0/0/top0/0·원본/선별 영상 해시는 `release21-round1-summary.json`에 있다.
첫30 측정은 training-segments의 prefix 원점을 사용했다(teacher trace는 release부터 시작하므로
첫 행을 전체 원점으로 쓰지 않는다). 중앙 wall/SIM2.5173,관측/명령 기준 기록이며 비용 측정이 아니다.
