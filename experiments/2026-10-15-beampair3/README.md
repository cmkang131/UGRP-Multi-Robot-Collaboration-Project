# beampair3 — numpy 원장 직렬화 정지 수정

PR #522, `claude/beam-pair-teacher`, beampair2와 합산하지 않는 새 후보.

[수정 전 분포](baseline-rejections.json): 이전 40회 중 시작18, 정상성공14,
HOST_ERROR1, 동일 결함 감독중단3, 미제출22. peer_goal/r2 원장74건은
다른 모집단이고 직렬화 실패1건과 합산하지 않는다. 빈 사유를 성공으로 간주하지 않는다.

원본 stack은 고정 의존성 runner의 `diagnostic-snapshot.json` write에서 numpy bool을
거부하고 예외 처리 `result.json`도 같은 값으로 실패했다. 공통 strict NumPy encoder로
bool/int/float/ndarray를 JSON 수치/배열로 변환한다. 공통 atomic write, pinned runner의
JSON·JSONL, adapter 결과·명령 원장에 적용하며 pinned 소스는 수정하지 않는다.
NaN/Inf·지원되지 않는 객체는 계속 거부한다. 모듈 바인딩은 예외에도 복원한다.
실행 전 모든 기록 경로에 중첩 NumPy 값을 쓰는 비물리 단위시험을 포함한다.

[원본 영상 직접 검토](original-visual-review.json): 실패8318611 0–19초(전체39·끝101프레임),
성공8318604 0–48.6초(전체99·끝101프레임), 각 개요+r1+r2.
MP4 3배속·각8MB 이하, GCP에서 생성 후 Mac 지정 playback 폴더에 회수했다.
원래 자기 JPEG는1Hz라 원본10Hz 평가 qpos를 렌더링하고 camera-runtime 보정을 복원했다.
위치 차이0, 물리·교사 재실행/보간 없음. 평가용 개요는 제어기에 연결하지 않는다.
실패의 배정은r1=blue/r2=teal로 다르고 자기 관측 band도 배정색이다.
근접은 사실이나19초에 정지하여 단순 통과의 완결은 아직 확인하지 않았다.

[짧은 탐색](probe-plan.json): 8318611·8318604 먼저, 성공8318600/01/02/03,
기존 고정 장면을 유지하고 r1 교란12/5/1/3/8/10틱을 분산한다. 최대3라운드,
첫 seed 성공 뒤 나머지5, 호스트 합계40 이하. 학습카메라off, held 숨김on,
weld off. 계산량 예산 search24_checks_v1/search25_checks_v1를 계속 켜고
60 SIM초 상한·기존 판정 상수를 변경하지 않는다. 새 수용 상수는 없다.
6/6이면8318611·8318604를 앞에 둔 별도40회 대기열만 준비한다.

R1은 첫 sentinel의 교란 길이가 원본12와 다른1틱인 계획 오류로 감독 중단했다.
원본을 보존하고 R2에서는8318611=12,8318604=5틱을 원 관문 그대로 둔다.
이 중단을 교사 물리 실패나 R2 성공률에 합산하지 않는다.

## R2에서 드러난 양보 정지와 최종 R3 후보

소스9f6caa6a: 첫8318611은 직렬화 정상, cap_end1, 미시작5.
[관문표](r2-rejection-table.json)에서 peer_goal/r1 95건.
[기존 오류 전380명령·qpos 차이0](prefix-comparison.json).
[0–59.9초 전체121·끝101 프레임 직접검토](r2-visual-review.json):
r1은 청록 옆을 지나 파랑 끝에 READY, r2는 양보 뒤 거의 정지했다. 같은 끝 배정이 아니다.
[명령만 재구성한 수치와 원인](r2-yield-analysis.json): 남은 거리와 발행 pulse가
함께 비례 축소돼 기존 도착식이 계속 false이고 양보는 기존 진행 감시를 우회했다.
기본off `peer_rendezvous_v2`는 기존1 SIM초 예측/경로갱신 범위가 끝나면
양보 계획을 폐기하고 새 경로를 계산한다. 도착·성공 선언이 아니며 새 거리허용치가 없다.
v1 재생 행동은 보존한다. R3가 세 번째이자 마지막 탐색이다.

## 최종 R3: 6/6, 새 관문 큐만 준비

실행 소스 **`e645b34beb4fa693ab4ddedfe77045ae26b46388`**, 고정 의존성
`26f84d0f0ada1c33473c83cca2d3415ce51bd247`, gcp1/n4-highcpu-64.
[전체 요약](summary.json), [원본 재집계](r3-summary.json),
[후보·프레임·이벤트 순차 관문표](r3-rejection-table.json), [런타임](r3-runtime.json).

|관문|누적 통과/시작|거부|
|---|---:|---:|
|시작·both_align·both_ready·both_pick|각6/6|각0|
|양측 명령 완료|6/6|0|
|전체 빔 3 SIM초 유지|6/6|0|
|입력 적합|6/6|0|

8318611=48.0,8318604=48.6,8318600=31.2,8318601=30.1,
8318602=34.5,8318603=34.1 SIM초. cap_end/HOST_ERROR/누락 거부 원장0.
`invisible_measurements=0`, `held_world_reads=0`, held 차단94/92/102/106/106/90틱.
r1 교란12/5/1/3/8/10틱은 모두 완수했고 r2는1/8/0/10/5/0틱이었다.
두0은 교란이 시작되지 않은 경우로 전 길이 검증에 넣지 않는다.
wall/SIM 중앙1.941, 첫 두 시드 직렬 뒤 나머지4동시(6자리 예약).
16동시 성능은 미검증이며 R1·R2·beampair2와 합산하지 않는다.
8318604는 과거 성공의974명령과 불일치0이다.
로컬 비물리24개 통과 뒤 고정 SHA를 push하고 실행했다.

[성공 영상 직접 검토](r3-visual-review.json): 0–48초 전체2Hz97프레임,
마지막10초10Hz101프레임. r2가 양보 만료 뒤 다시 청록으로 접근하고
r1은 파랑을 맡아 양측 파지·들기를 완료했다. 평가 qpos 위치 차이0.
원본 실패 1개·R2 cap_end 1개·과거 성공 1개·새 성공 1개를 검토했다.
모든 영상은 개요+r1+r2 3배속·파일당8MB 미만이고 지정 Mac playback 폴더에 있다.
ffprobe만 사용했고 Mac 화면 앱을 열지 않았다. 새 성공 원본은 episode 상위에
독립 milestone 메타데이터를 추가했으며 원래 raw/adapter manifest는 보존했다.

[새40회 큐](gate40-queue.json): 전체 source SHA·절대 rejection_table·해시,
8318611·8318604 먼저, 최대16, 학습카메라off·held 숨김on·weld off.
운영 사본: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-beampair3-e645b34b.json`.
`ready=false`, `approved=false`, `submitted=false`, `gate_measured_N=0`.
조정자가 clean pin·계획16동시 첫30 속도/원본·예산/디스크·VM 상한을 확인한 뒤 활성화한다.
VM 실제 상한은24시간으로 관측됐고 다른 작업 때문에 바꾸지 않았다. 본 명령은8시간 제한이다.

[세 라운드 원본 해시](all-manifests.json)와 [정리 확인](r3-lifecycle.json):
전체 SHA256SUMS 검증, 본 작업 worker0·lease/예약 해제.
VM 정지는 다른 작업 lease로 거부되어 RUNNING을 유지했다(강제 정지 없음).
원본은 GCP 영속 디스크에 보존하며 별도 ARM 백업은 없다.
정식40회·학습 데이터·ACT 학생·운반/놓기·실물은 미검증이다.
