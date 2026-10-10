# egomap65 — 공통 heading 진동, 고정 24조건 DEV

2026-10-10 사용자 지시. 검출기·지도·운동모델·경로·B/귀환 판정은 egomap64 동결. 새 seed/prepare0, 같은 egomap63 자기 B 체크포인트63001–63006. GT는 결과 채점/원인 분해에만, 제어 입력0. PR405 DRAFT, 물리/재생은 oracle-x86만, Mac은 코드·시험·저장 JSON 산술/전달만.

## 실행 전 조사·협업

- PR416 `origin/codex/s3-no-prior-smoke` **ad844d13**, s3fix16 `experiments/2026-10-10-s3-alignment-ownership/README.md` 확인. 원인은 fine adapter의100ms→60ms 덮어쓰기와 heading 재대체; `coarse_axis_ownership`은 그 **근거리 RGB 정렬** 경로에 한정된다. 자기 지도 Host는 .10s 합법 펄스를 직접 발행하므로 같은 덮어쓰기 경로가 없다.
- PR422 **256a1b0c**의 `zone_solo_cyan_path_heading.py:48–119` 비교: 추가 `position_tolerance_m=.03`은 자기 지도 호출과 수치 동일, 나머지 변경은 S2 물체정렬 전용. 현재 공유 select_waypoint/합법 profile 선택을 재사용하고 다른 모듈 전체 병합으로 동결 조건을 바꾸지 않는다.
- [PR416 공유](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/416#issuecomment-6097396799), [PR422 공유](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/422#issuecomment-6097397009). 공통 drive selector를 복제하지 않고 인스턴스별 입력 필터/히스테리시스만 추가한다.

### 참고 자료와 적용 경계

1. [Nav2 Jazzy rotation shim 원본](https://api.nav2.org/nav2-jazzy/html/nav2__rotation__shim__controller_8cpp_source.html), 소스55–57 및 `in_rotation_ ? angular_disengage_threshold_ : angular_dist_threshold_`: 진입/이탈 히스테리시스. Apache-2.0; C++ 복사 없이 같은 상태 규칙을 Python adapter로. [공식 설명](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/controller_plugins/configuring_rotation_shim_controller/).
2. S3 `zone_s3_settled_servo.py`(ad844d13)의 Selector45–57: 데드밴드 안에서 latch,1.5× 밖에서 해제; SettleGate106–120: `max(.50,profile.times[-1])` 뒤 새 frame. 이 두 작은 상태 규칙은 출처를 붙여 독립 공통 helper로 추출/재사용한다. S3 전체 모듈은 endpoint imports가 있어 가져오지 않는다. 임의의 짧은 미보정 펄스 생성0. S3와 공통 공유 가능하도록 PR에 알림.
3. 목표 방위 저역통과는 표준1차 지연 `alpha=dt/(tau+dt)`, 원형 차이 `wrap(raw-filtered)`를 사용. tau=.50s는 위 기존 settle 시간과 같게 고정한 공학적 선택이며 논문의 최적값이라고 주장하지 않는다. 바닥/경로점을 바꾸지 않고 공유 selector에 줄 목표 방위만 평활화(거리 유지). 각도 ±π 불연속 방지. 필터/히스테리시스/정착은 각 bool 토글, 이번 on은 셋 모두 on.

## 원인 진단 — egomap64 저장 JSON, 제어 재생0

연속 .2초 Host 회전→다음 결정만 분석. 오차 변화 = 목표 방위 변화 − 명령 예측 yaw − yaw innovation(추정 yaw 변화−명령 yaw). 가장 큰 절댓값 성분으로 분류한 **산술 진단**이며 인과 개입 결과 아님. 긴 간격/복구 회전은 제외하므로 기존전체 반전1271/1111와 분모가 다르다.

|조건|연속 회전 피드백|반전|목표 방위 우세|yaw innovation 우세|예측 회전 우세|펄스만으로 반대 데드밴드 초과|
|---|---:|---:|---:|---:|---:|---:|
|baseline|7958|783|702|10|71|0|
|a500|7153|636|554|26|56|0|

1419반전 중1256(88.5%)은 목표 방위 변화 우세. 기존3.5cm carrot 선택은 그대로 둔다. 예측 최소회전 약.10354/.10358rad > 한쪽허용.06이나 전체폭.12보다 작다. 따라서 최소펄스만으로 반대 회전문턱을 넘는 설명은0; yaw innovation은 명령모델 오차와 PF보정 모두 포함하므로 전부 PF jitter라고 단정하지 않는다. 실행별 목표/추정/GT yaw 변화·waypoint 변위 분포/예시는 `results/diagnosis.json`.

## 사전등록 — 결과 보기 전 고정

- 행렬: 6seed×baseline100/a500×기존heading/off·`heading_stability=filtered_hysteresis_v1` = **24회**. [전체 이름·명령·체크포인트 SHA](batch-plan.json). 63004 상자→자기관측B 전환은 egomap64와 동일, 나머지5개 B상태 보존. 접근최대270SIM초, 자기B 선언시 다음프레임 귀환, 미선언270초에도 귀환으로 전환, 귀환270초. 도착/거짓선언/≤.20m 귀환은 기존 판정 불변. 강제loss0.
- on의 회전 **제어** 이탈 .06rad(기존), 재진입 .09rad(S3 1.5×), 목표방위tau .50s, 정착최소 .50s+새 RGB. **성공 판정 문턱은 변경하지 않음**. 계획기/경로/검출/모션/RBPF/graph동결. off는 설치 identity, 기존원본 함수/상태/출력 bytes 동일 시험.
- 코드·변경시험·commit/push 후 ≤8SIMs smoke1회(경로오류시 수정 후1회만 재확인). 준비가 끝나면24개 전부 한 묶음으로 고정 제출, 최대10동시, RAM6GiB 미만이면 대기. 중간 raw 보고 설정/목록 변경0.
- 실행기 wall alarm: egomap64 동일호스트12건의 최대 wall/SIM **7.0114851602**, `ceil(540×7.0114851602×2 + 300)` = **7873wall초/회**. 두 조건 공통, SIM예산/성공문턱 아님. 결과 이후 늘리거나 재실행하지 않는다. admission디스크<2GiB/HOST/벽실패도24분모에 남김. 예상전체2–3시간(실측전 추정), raw약12–16GiB. Mac잔여약4GiB로 이번 raw RGB는 서버원본 보존하고 로그/결과/해시만 로컬회수; 미회수RGB를 로컬백업이라 보고하지 않음.
- 최종 모든24건 terminal 뒤 공동채점: 각조건 n/6 B·귀환·접촉·거짓선언, >3σ프레임n/N/종료n/6, 종료오차, 회전/전진/hold명령 비율·반전·B최근접거리. HOST/차단/미측정분리. 반복seed DEV이며 독립확증 아님. 새 gate/후속 선택실행 없음, 결과 그대로 보고.

## 구현·물리 입장 전 검증

- `harness/path_heading_stability.py`: S3 SettleGate와 latch 규칙을 공통 어댑터로 추출. 원형 저역통과 후 기존 `own_map_heading.command → select_waypoint → select`를 인스턴스 전용 binding으로 호출한다. profile/예측/충돌 검사·dev_light는 기존 Host가 그대로 소유한다. off는 설치 자체 identity; 도착 권한을 latch가 부여하지 않는다.
- `scripts/run_own_route_heading_stability.py`: 기존 egomap64 runner의 체크포인트복원 직후만 on설치. 기존1257모듈 및 기존실행기 바이트는 변경0; 새 어댑터에서 wall alarm만7873초로 바인딩하고 번들에 근거를 남긴다. 스모크8SIM은 같은 공식413wall초.24명령/10슬롯/6GiB입장/전체terminal후채점 고정.
- 변경 관련3파일 **28시험 통과(1.70s)**: off 원본 명령/로그 bytes, 경계 히스테리시스, ±π 필터, 새관측/정착, 실제 Host 공유펄스계약, 실제 runner wrapper 설치·alarm,24조건과 원본옵션 보존. Mac 물리/재생0. 실행 직전 origin 재확인: S3 ad844d13 그대로, 공유 selector 새변경 없음.

### 추가 분해(저장 JSON만, 물리 설정 변경0)

목표방위 항을 다시 고정 이전 waypoint에 대한 자기 XY 이동 효과와 waypoint 갱신 효과로 나눴다. 각 단계에서 동일한 atan2/wrap 대수차를 사용한다.

|seed|조건|반전시 목표방위 변화 중앙(°)|yaw innovation 중앙(°)|추정−GT yaw변화 중앙(°)|carrot거리 중앙(m)|
|---|---|---:|---:|---:|---:|
|63001|a|34.93|3.24|3.20|0.075|
|63001|baseline|71.94|0.89|0.81|0.074|
|63002|a|27.81|2.45|2.40|0.071|
|63002|baseline|26.90|0.92|0.91|0.076|
|63003|a|26.77|1.03|1.02|0.078|
|63003|baseline|27.29|2.10|2.16|0.077|
|63004|a|27.77|3.18|3.33|0.079|
|63004|baseline|35.77|1.36|1.25|0.077|
|63005|a|56.40|2.51|2.64|0.077|
|63005|baseline|37.49|1.94|1.90|0.076|
|63006|a|29.29|3.01|3.13|0.081|
|63006|baseline|27.91|2.42|2.37|0.076|

baseline 목표방위 우세 반전 내부: waypoint 갱신 우세 350, 자기 XY 이동 우세 352.

a 목표방위 우세 반전 내부: waypoint 갱신 우세 224, 자기 XY 이동 우세 330.

## 인프라 입력 소실·복구 등록(본 정책 결과 개봉 전)

13:2x UTC, 입장 시24개 SHA검증을 통과했던 서버 `egomap63-batch` 입력 경로가 사라져 대기5개가 `FileNotFoundError`/`HOST_ERROR_NO_RESULT`로 물리 시작 전 종료됐다. 같은 시각 여유 공간 약10→23GiB 증가를 관측했으나 **제거 주체/원인은 미확인**이다. 이 작업의 삭제/다른 작업 종료0. 이미 진행 중인 물리19개는 그대로 두고, 원래 실패5개 로그도 보존한다.

- 영향: **63005/a/on 및63006/baseline/off,on·a/off,on**. result/own-controller 파일이 생성되지 않아 물리0임을 별도 admission으로 검사한다.
- 로컬 보존 원본에서 prepare63005(40MiB)·63006(32MiB)를 `rsync --ignore-existing`로 원래 서버 경로에 복구했다. 두 체크포인트의 원래 SHA 및 각각29개 파일/스트림 prefix SHA 일치. 새로운 prepare·튜닝·GT 입력0. [공유 알림](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/416#issuecomment-6097908619).
- 최초 묶음 전체 terminal 뒤, **미시작5슬롯만 한 묶음**으로 `egomap65-input-recovery`에 재제출한다. 물리 child는 원래 **4f759965ca00d4ae29ec9419083a8dca62cfb736** checkout/venv/CLI 인자/seed/옵션/7873wall상한 그대로, 출력 경로만 새 폴더. 새 orchestrator SHA와 child SHA를 구분한다. 추가 smoke0. 유효 물리 재시험0, 계획된 물리총수24 그대로.
- `scripts/retry_own_route_heading_inputs.py`는 정확히 위5개·기존FileNotFoundError·물리0·복구파일존재·기존전체종료를 요구한다. 메모리6GiB 대기,동시5≤10. 이 복구도 실패하면 추가 재시도하지 않는다. 결과는 등록조건24와 제출시도29(최초HOST5 포함)를 모두 보고하고 실패행을 대체/삭제하지 않는다. 정책 성능을 보고 재실행 대상을 고른 것이 아니다.

- 복구/전달 변경 관련3파일23시험 통과(1.35s): 정확한5개 미시작 조건만 허용, 진행·유효물리 대체거부, 4그룹 각각6분모, 서버/로컬hash 검사. 복구 child의 절대출력 경로를 새폴더로 고정했다. 원래checkpoint가 요구한 source import 파일 누락0도 확인. 물리 설정 변경0.

- 사후 인프라 확인: 서버 `runs/SUPERVISOR-NOTES.txt`의 **2026-10-10T13:11:43Z** 기록은 `egomap63-batch`·`egomap64-batch`를 Mac rsync-c 동일성 확인 후 중복본 정리했다고 명시한다. 따라서 미확인이던 경로 소실 원인은 보존 정리와 실행 입력 의존성의 충돌로 확인됐다. Mac 원본은 온전하고, 이 작업의 삭제는0이다. 이후 archive 명령으로 옮겨진 eg63/64 smoke도 자기 결과 로컬본을 보존한다. 진행 중 참조 입력은 완료 run이어도 보존해야 한다.
