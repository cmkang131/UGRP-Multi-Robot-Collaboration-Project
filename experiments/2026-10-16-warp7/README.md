# warp7 — NOT_READY / 세 번째 처리량 라운드 중단

`claude/warp5`, [Draft PR #550](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/550). 사용자 2026-10-16: **"모두 MJWarp로 바꿔서 하게"**. 자기 지도·운반·LLM E2E도 대상이다. CPU 색 결과 동일성은 관문에서 폐기했다. MJWarp 색 평가와 N16 초기 진행은 실행했지만 운반·place·완주·LLM E2E는 미완료다. 처리량 증상이 R1e/R2/R3 세 실행에서 반복돼 추가 물리/LLM 제출을 중단했다. R2에는 별도의 TOP 캐시 오류도 있었다.

## MJWarp 자체 RGB 측정

gcp2 L4, 고정 v5 장면, 자기 RGB640×480/PIL82·기존 광학계,88자세다. 평가용 visible geom 라벨은 채점에만 쓴다. 검출기/제어/LLM 입력에 전달하지 않는다. 원본2,912파일 SHA를 CPU에서 전부 확인했다. 같은88장으로 보정·평가한 DEV fit이며 독립 holdout 결과가 아니다.

|검출기|보정 전 accepted 정답/전체|현재 accepted 정답/전체|현재 오검출|가시 면적 기준 전체 검출|
|---|---:|---:|---:|---:|
|상자|52/52|52/52|0|52/82|
|B 바닥 기억|0/45|4/4|0|4/10|
|운반 목적지|4/82|4/4|0|가시지만 거부38건|

상자 누락30건은 **모두 색·윤곽 후보 뒤 바닥 cuboid 투영에서 거부**됐다. HSV를 더 넓히지 않았다. 전체 검출 recall63.4%는 계속 남긴다. B 정면 등록 자세는4/4다. 나머지 B 누락6건과 목적지 크기·바닥 투영 거부는 별도 문제다. 이전 CPU 운반의 목적지 획득0/1253이 해결됐다고 주장하지 않는다.

기본 off `UGRP_WARP7_PERCEPTION=rendered_hsv_v1`은 [보정표](paint-calibration.json)의 paint p01/p99 HSV를 바깥 정수 bin으로 반올림해 **후보 영역 중앙 HSV**를 판정한다. 연결 영역 경계를 보존한다. 기존 하단35% crop이 B 양성 자세의 라벨/HSV/유효 바닥 ray23,905px를 모두 버렸으므로 이 토글에서만 제거했다. ray·거리·최소 면적·support·목적지600px/1.2m·place 관문은 그대로다. 새 기하 허용 오차는 없다.

[최신 측정](colour/r5-summary.json), [백분위](colour/hsv-distribution.json), [첫 분포](colour/r1-summary.json). R3/R4 scorer의 `admitted=false`는 색과3D 투영을 합쳐100% 검출을 요구하던 임시 값이다. 최신 scorer는 이를 색 판정에서 제거하고 **정적 DEV 운반 진단만** 허용한다. 전체 시각/위치 추정/ACT/임무 qualification은 false다. 기존 N16은 처음부터 명시적 DEV였으며 과거 대기열/결과를 소급 변경하지 않았다.

## 관문과 모든 제출

[전체 관문표](final-record/rejection-table.json), [모든 오류·원본/모델 배열 해시](final-record/attempts.json), [집계](final-record/summary.json). R1–R1c는 baseline11 + progress5였고 setup에서 멈췄다. 이후 미등록 정적 선언5개를 제외한 R1d 이후 N16은 **고유6초기 상태 × baseline/progress 두 조건 + 명시적 반복4세계**다.16개 독립 성공 시행으로 세지 않는다. 모든 대기열에 존재하는 절대 `rejection_table`을 연결했다.

|제출|setup|GPU 초기 진행|완료|중단 사유|
|---|---:|---:|---:|---|
|R1|0/16|0|0|floor-map fixture 누락|
|R1b|0/16|0|0|standalone wall helper 누락|
|R1c|2/16|0|0|미등록 시나리오 정적 선언 없음|
|R1d|16/16|0|0|절대 시각 반올림으로 명령 시계 역행|
|R1e|16/16|0.4 SIM초|0|처리량 부족, 감독 중단|
|R2|16/16|0.3 SIM초|0|`cctv_top` 대신 첫 CCTV를 선택한 캐시 오류|
|R3|16/16|0.4 SIM초|0|세 번째 처리량 증상, 감독 중단|

R1d epoch1.3000000000000178→1.3의1.78e-14초 역행이 기존2000PWM/s 누산기 한도를 넘었다. 정수 tick 차이만 반올림하도록 수정했다. 명령 허용 오차는 완화하지 않았다. R2는 검토 카메라를 `cctv_top`으로 명시하고 모든 세계의 캐시 준비를 확인한다. 두 반례의 회귀 검사가 있다.

|실제 rollout 조건|물리 그룹|초기 SIM초|loop wall초|
|---|---:|---:|---:|
|R1e all-awake|6|0.4|290.369|
|R2 native sleep/compact·필요 카메라|6|0.3|177.537|
|R3 위 조건 + native 모델 배열 배치·SAP|2|0.4|145.099|

이는 setup 제외 **부분 진행 시간**이다. 첫30SIM초 wall/SIM 중앙값·비용 우월성 측정이 아니며 공유 부하/구성도 달라 합산하지 않는다. R3 그룹 누적 `command_and_physics`97.792초, `render_and_evaluator_export`35.126초(초기 렌더 포함)다. 순수 GPU 물리·명령 CPU 계산·공유 부하 분리 계측은 남아 있다.

R3 GPU source: `5974a181a2cec9731339a6ce3aadc0464b8dddcf`. 공유 backend/core 원문을 바꾸지 않고 native 초기화 AST 두 분기만 바꿔 기존 exact `combine_models`를 호출했다. 지원 `*` 배열만 세계별로 배치하고 비지원 배열/스칼라는 정확히 같아야 한다. `dof_length`는 기존 pinned world-index sleep adapter로 읽는다. 렌더러가 native 배열에서 읽는 투명층 반경 등도 그룹 키에 포함한다. source/AST/배열 SHA와 실제2그룹 증거는 전체 기록에 있다. actor10Hz·review2Hz, 같은 GPU 상태의 full/demand actor RGB 일치를 초기·첫 자기 명령 변화에서 확인했다. 명령 변화는 이동 성공이 아니다.

|임무 관문|유효 분모|결과|
|---|---:|---|
|들기 → 운반 진입|0|start/fold에서 중단|
|reloc21 반복 제거 수정 물리 검증|0|미검증|
|출발 enclosure·목적지 색 획득|0|새 운반 분포 없음|
|place / 완주|0|미측정,0/16 실패로 계산하지 않음|
|운반 xy/yaw p95·입력 감사|0|미측정|
|cap_end|0|HOST_ERROR/감독 중단과 분리|
|LLM 첫30 SIM초|0|미실행·모델 호출0|

초기 start/fold 감사의 `invisible_measurements=0`, `held_world_reads=0`은 운반/held 구간의 감사 통과가 아니다.7제출 원본1,528파일 SHA 불일치0이며 모든 HOST_ERROR를 포함한다.

## 인계·남은 문제

[이전 거부 분포](prior-rejection-table.json)는 CPU 코호트로 분리했다. seed93266 progress의 최대 범주는 `start_enclosure_overlap` / `wall_divider_1` /1765건 / 최소 틈−0.031820265m다. 다음은 issued-motion enclosure98건/−0.034708619m다. seed93315는170.4SIM초 이후 목적지 색0/1253이었다. 이 수치로 허용 폭을 넓히지 않았다. progress/complete 기본 off, 반복 제거 수정 진단만 별도 조건으로 유지했다. 새 운반까지 도달하지 못했으므로 해결됐다고 하지 않는다.

다음은 처리량 분리 계측과 scalar 제어의 n4 이전이다. 현재 제어는 L4의8 CPU, 사후 분석만 n4여서 **n4 CPU 제어 + L4 물리 소유자 분리도 미완료**다. 세 번째 중단 뒤 새 N16을 제출하지 않았다. 이후 같은 호스트에서 enclosure 분포 → 반복 제거 → 목적지 → place/완주·p95·감사를 순서대로 잰다.

PR #553 CoreWeave fp4 설정/중계/감시를 가져왔다. 마지막 watch 경보0, Mac에서 OpenRouter 양수 잔액 확인(정확한 잔액은 ignored 로컬 기록만). 가격 경보가 이번 차단 사유는 아니다. [legacy planner preflight](e2e-preflight.json)는 CoreWeave bounded-rate 등록에서 `REGISTERED_RATE_POLICY_REQUIRED`를 재현했다. 실제 relay/3로봇 E2E factory·ACT 근거리 연결·sub-tick 철회·종료 세계 격리도 미검증이다. 호출0이며 형식·응답 시간·429·캐시·이미지·호출 수·토큰/SIM초는 첫30 원본이 없어 null이다. 손코딩 근거리 파지로 대체하지 않았다.

## 재생·운영·재현

gcp2 ffmpeg으로 R1e/R3 world000의 overview+r1+r2+r3를4배속으로 만들고 ffprobe로 확인했다.3,832/3,842bytes로8MiB 이하이며2Hz overview는 각1시각뿐이다. 직접 읽은10Hz r1 strip은 R1e1.3–1.6SIM초/R3 1.7–2.0SIM초, 각4장이다. 바닥·보라 벽 경계가 거의 같은 방향으로 유지됐다. sparse overview보다 큰 화면 변화가 없는 이 짧은 구간만 추가 확인했으며, 운반·반복 진동·실패 직전10초 원인을 주장할 길이가 아니다. 성공 실행이 없어 성공1개 비교도 미충족이다. [직접 검토 기록](playback-review.json). Mac에는 요약/strip/작은 영상만 회수했다.

물리: GCP `ugrp-sim-b-1014` / `ugrp-act-l4-gcp2` / g2-standard-8·L4 / MuJoCo-MJWarp3.16·Warp1.15, shared-load. 분석: `ugrp-sim-gcp2` n4-highcpu-64. gcp3 warp6 exclusive 임대는 사용하지 않았다.8h Compute Engine deferredStop(`system@google.com`, 예산 함수 아님)을 확인하고 같은8h/STOP 설정으로 재가동했으며 타 임대를 보존했다. 첫 프로젝트는 건드리지 않았다. 원본은 두 gcp2 영속디스크, source는 shared bare reference clone에 보존한다. Mac 물리/렌더/GUI·Drive·VM 키/자격 증명 복사0이다.

[L4 종료 확인](host-lifecycle-l4.json)·[CPU 종료 확인](host-lifecycle-cpu.json): 자기 프로세스0·자기 임대 제거, 타 작업 임대/프로세스 보존, VM 정지 시도0. 기존 idle/budget/상한 장치를 변경하지 않았다.

재집계는 gcp2 CPU에서 `python collect_results.py --root /home/ugrp/ugrp-sim/runs/warp7 --output <새 절대 경로>`다. 원본 대기열/dispatch에 개별 재현 명령이 있다. 관련 비물리 검사·회수·정리는 [검증 기록](validation.json)을 따른다. 전체 CI/병합·학생 임무 성공을 주장하지 않는다.

방법 근거: [OpenCV HSV inRange](https://docs.opencv.org/4.13.0/da/d97/tutorial_threshold_inRange.html), [MJWarp 배치/sleep/성능](https://mujoco.readthedocs.io/en/latest/mjwarp/index.html), [segmentation object ID/type](https://mujoco.readthedocs.io/en/latest/_modules/mujoco_warp/_src/render_util.html). pinned API·백분위·원본 반례를 함께 기록했다.
