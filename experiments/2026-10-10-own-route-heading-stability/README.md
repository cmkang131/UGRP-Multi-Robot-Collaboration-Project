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

## 최종 결과 — 24조건/29제출, 설정 변경0

사전등록 e9fa9c54 → 물리 **4f759965ca00d4ae29ec9419083a8dca62cfb736**, 복구 orchestration **cc41acfd**. 같은6개 체크포인트의 반복 DEV 비교이며 독립확증 아님. 최초24제출 중19물리+5입력소실HOST, 동일입력 복구5제출을 합쳐 **계획24/물리24/제출29**. 최종 물리19정상기록·벽접촉실패5, 물리미시작HOST5/29를 별도 보존한다. 차단·호스트중단·wall알람0, 제외/재튜닝0. 스모크8SIM 1회는 본24분모 밖이다.

|입자 / heading|B|귀환≤.20m|벽 접촉 실행|거짓 선언|>3σ 프레임|종료>3σ|종료오차 중앙/최대(m)|
|---|---:|---:|---:|---:|---:|---:|---:|
|100 / off|2/6|0/6|1/6|0/6|9353/13611 (68.7%)|5/6|0.505/1.661|
|100 / on|0/6|0/6|0/6|0/6|8204/16206 (50.6%)|5/6|0.529/0.755|
|500 / off|2/6|0/6|2/6|0/6|6469/12661 (51.1%)|3/6|0.296/0.865|
|500 / on|0/6|0/6|2/6|0/6|3190/14144 (22.6%)|2/6|0.332/0.577|

로봇 접촉은 전조건0/6. 벽 접촉은 실행당 첫 접촉에서 물리 종료하여 위의 실행 수와 사건 수가 같다. 실제 B를 지나갔어도 자기 도착 선언이 없으면 성공으로 바꾸지 않는다.

|입자 / heading|회전/전진/hold 명령(%)|hold제외 회전(%)|반전/회전명령|전진 없는 반전|
|---|---:|---:|---:|---:|
|100 / off|60.0/28.7/11.3|67.6|1271/8163 (15.57%)|792|
|100 / on|20.5/12.2/67.3|62.7|515/3325 (15.49%)|252|
|500 / off|59.2/31.4/9.5|65.4|1119/7490 (14.94%)|652|
|500 / on|20.3/12.3/67.4|62.2|512/2865 (17.87%)|263|

**미채택.** 전체 회전 약60→20% 감소의 상당 부분은 정착 대기 때문이다. on hold 중 `heading_stability_settle`은100입자10022/10900(91.9%),500입자8483/9539(88.9%). 회전명령당 반전은15.57→15.49%,14.94→17.87%여서 진동 해결 근거가 없다. 전진은3904→1981,3970→1740회로 줄고 B도착2/6→0/6; 과신율 감소만으로 위치추정/임무 개선을 주장하지 않는다. 작은 carrot에서의 목표방위 변화는 여전히 남는다. 세 토글을 함께 켠 비교라 각 기법의 인과효과는 분리하지 못했다. 기본off 유지, 결과 후 문턱/시간/설정 수정·추가물리0. 다음 판단은 정착 대기로 생긴 이동 손실과 목표방위 갱신을 분리하는 별도 사전등록이 필요하다.

### 개별 실행(접근270+귀환270 동결)

|seed|입자|heading|B/귀환|벽|종료오차(m)/σ|B최근접 경계거리(m)|접근/귀환 SIM초|회전 반전|종료|
|---|---:|---|---|---:|---:|---:|---:|---:|---|
|63001|100|off|0/0|0|1.661/18.05|1.660|270.0/270.0|287|RECORDED|
|63001|100|on|0/0|0|0.327/3.29|1.839|270.0/270.0|96|RECORDED|
|63001|500|off|0/0|0|0.287/4.01|1.649|270.0/270.0|233|RECORDED|
|63001|500|on|0/0|0|0.116/1.54|0.474|270.0/270.0|88|RECORDED|
|63002|100|off|0/0|1|0.412/3.84|0.000|270.0/17.0|141|PHYSICAL_FAILURE|
|63002|100|on|0/0|0|0.427/13.37|0.211|270.0/270.0|87|RECORDED|
|63002|500|off|0/0|1|0.279/1.31|1.456|270.0/17.2|174|PHYSICAL_FAILURE|
|63002|500|on|0/0|0|0.208/1.54|1.181|270.0/270.0|91|RECORDED|
|63003|100|off|1/0|0|0.820/10.75|0.000|170.0/270.0|201|RECORDED|
|63003|100|on|0/0|0|0.149/1.80|0.312|270.0/270.0|93|RECORDED|
|63003|500|off|1/0|1|0.567/1.84|0.000|120.2/120.6|127|PHYSICAL_FAILURE|
|63003|500|on|0/0|0|0.462/1.27|0.500|270.0/270.0|88|RECORDED|
|63004|100|off|0/0|0|0.598/7.01|2.355|270.0/270.0|229|RECORDED|
|63004|100|on|0/0|0|0.631/12.94|2.356|270.0/270.0|75|RECORDED|
|63004|500|off|0/0|0|0.865/7.85|2.356|270.0/270.0|209|RECORDED|
|63004|500|on|0/0|1|0.577/4.25|2.356|270.0/109.4|95|PHYSICAL_FAILURE|
|63005|100|off|0/0|0|0.267/3.75|0.066|270.0/270.0|240|RECORDED|
|63005|100|on|0/0|0|0.755/6.37|2.198|270.0/270.0|60|RECORDED|
|63005|500|off|0/0|0|0.113/1.60|0.930|270.0/270.0|222|RECORDED|
|63005|500|on|0/0|1|0.455/3.65|2.197|270.0/18.2|49|PHYSICAL_FAILURE|
|63006|100|off|1/0|0|0.205/2.97|0.000|104.0/270.0|173|RECORDED|
|63006|100|on|0/0|0|0.701/7.96|0.308|270.0/270.0|104|RECORDED|
|63006|500|off|1/0|0|0.305/3.98|0.000|113.0/270.0|154|RECORDED|
|63006|500|on|0/0|0|0.204/2.91|0.228|270.0/270.0|101|RECORDED|

63004의자기관측B 지정(기존prepare상자목표→B)은 egomap64와 동일. egomap64 a500의 HOST알람2건에서 미측정이던 귀환 잔여 구간이 이번 off에서는 끝까지 기록되어 과신6436/12514→6469/12661, 반전1111→1119가 됐다. 조건 개선으로 해석하지 않는다. baseline은egomap64수치동일. 이번 wall/SIM **2.587–7.791**, 최대wall **4207.217초**, 등록상한7873초보다 작음; wall알람0/24. 조기 벽 실패의짧은시간을속도향상으로해석하지않음.

### 원본·바이트 동일성·전달

- raw: `/Users/changmin/projects/ugrp/outputs/oracle-runs/egomap65-{batch,input-recovery,smoke}`. 실행중Mac여유가45GiB로확인되어 부분회수계획을 전체보존으로 확대; RGB/지도포함 **57,588파일/11,845,055,253bytes** 서버SHA와 로컬SHA 모두일치, 누락0. 서버원본도유지. 전송·저장만했고Mac물리/제어재생0.
- off의 egomap64 대비 첫60초 **12조건×300=3600/3600행 bytes동일**. 기존1257제어모듈 동결검사+설치off identity시험 유지. [전체결과](results/comparison-v2.json), [원인분해](results/diagnosis.json), [hold/시간집계](results/hold-audit.json).
- 변경3시험파일 **25시험 통과(1.84s)**. CI완료대기0. 본 물리는code4f/복구drivercc41로종료; 뒤의전달코드수정은물리동작을변경하지않음.
- TensorBoard `1010-egomap65-v2` 24조건/600scalar, `1010-egomap65-infra-v2` 5입력실패/20scalar. EventAccumulator/HParams29건과원본수치모두대조통과. 최초스냅샷은보존: 전체회수였는데부분회수라는scope문구가남아 v2에서그문구만정정했고, **성능수치모두동일**. 원본comparison.json도덮어쓰지않음. [검증기록](results/delivery-verification.json).


- [TensorBoard 저장 링크](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2FB_arrived%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Freturned%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fover_3sigma_rate%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fturn_fraction%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fturn_moving_fraction%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fturn_sign_reversals%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fsamples%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fwall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%5D&smoothing=0&runFilter=%5E1010-egomap65-v2%2F#timeseries): native backend가공유logdir와24조건/B·귀환태그를실제로로드한것확인. 입력실패5개는별도infra snapshot. 공유뷰설정에는자기key만추가,10핀·HParams5열목록저장. 기존viewerPID52016이없어자기세션으로시작했으나첫세션SIGTERM종료,두번째`tensorboard-egomap65-view`에서backend확인. 다른프로세스종료0. Chrome연결이재설정되고사용자조작알림이떠 **시각표시·HParams열재적용은미완료**; 다른프로필을사용하지않았고재시도반복0. 새영상요청/생성0.
