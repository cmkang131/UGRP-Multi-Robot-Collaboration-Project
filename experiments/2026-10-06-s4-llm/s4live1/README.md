# s4live1 — 실제 LLM + Oracle x86 단계 배관 확인

2026-10-10 감독 지시. `research_result=false`, 정식 E2E·연구 코호트·실물 검증 아님.
S3 `7a4bda7ac71bc7b59d7d9a9101d9d3c619498df1`을 S4에 병합했다.
새 번들 `zone-s4-live-dev-v157`, workflow `7.51.0` (예약 시 main/열린 PR 최대 v156/7.50.0).

## 고정 범위

- `dev_s1lite`: cyan/P1-1 → A, r3 단독; beam/P2-3 → B, r1/r2 자기 claim까지만. 실제 pair GO/운반을 시작하지 않는다.
- S3 v156 최신 제어/물리·카메라 구성, dev_light, heading on, weld off. r3가 cyan에서 0.24m 떨어진 합성 정렬 입구를 **장면 구성에서만** 설정한다. 시작 주행/전역 탐색 성공이 아니다.
- r3는 자기 RGB로 표적을 얻고 실제 모델 claim 이후만 align/pick/lift를 실행한다. 발행한 HIGH 시퀀스 후 자기 명령 이력에 출발 대기 사건을 남기고 새 LLM continue가 10 SIM초 내 도착해야 carry 명령을 허용한다. 늦거나 이전 창의 응답은 출발 허가가 되지 않는다.
- 네 조건은 동일 seed601·물리·관측·모델·호출/토큰 상한·실행기를 사용한다. 채널만 no_comm / peer_ko / leader_ko / structured. leader는 기존 seed 회전으로 r2. 고정 prompt 과금은 네 조건의 최댓값으로 같다.
- S3 내부 B-only 생성 뒤 r3의 목적지/정적 경로를 공개 주문 A로 바꾸며, 제어 시작 전 완료한다. GT는 setup/eval_only/실제 실패 abort에만 사용한다.
- 모델은 기존 등록 `gemini-3.8-flash` (프록시 유효 매핑 `gemini-3.8-flash-low`), 요청 timeout180초, 최대18 POST/조건, 300,000 토큰/조건, retry0. 모델 응답 원문·이미지 sha256·provider usage·wall latency·실패·명령별 claim/출발 call_id를 저장한다.
- Mac은 물리·렌더0. 모델은 기존 Mac 프록시의 인증을 그대로 사용한다. Mac relay가 매 POST마다 기존 `live_proxy`로 소스해시·PID·listener를 다시 검사하고 SSH 역방향 루프백18391→Mac18392→기존8391로 전달한다. 키/토큰은 읽거나 서버로 전송하지 않는다. 서버 `PairLiveLedger`의 실제 wire, SQLite 선예약/정산, NetworkFence, redirect 거절, 완료·JSON 검증을 유지한다.

## 실행 목록 (결과 열람 전 고정)

필요한 경로 스모크는 `s4live1-smoke-no_comm-s601-v157`, no_comm/seed601/7.5 SIM초 1회다. reset/setup 포함 10 SIM초 미만이다. 실행기 결함이면 같은 제한에서 수정 후 1회만 재확인한다.

그 후 아래 4개를 한 번에 동시 제출한다(작업 몫 상한6, 이번 묶음4). 각90 SIM초, reset/setup 포함120초 미만. 묶음 도중 조건·시드·코드를 바꾸지 않는다.

| 이름 | 조건 | seed | cap SIM초 |
|---|---|---:|---:|
| s4live1-no_comm-s601-v157 | no_comm |601|90|
| s4live1-peer_ko-s601-v157 | peer_ko |601|90|
| s4live1-leader_ko-s601-v157 | leader_ko |601|90|
| s4live1-structured-s601-v157 | structured |601|90|

공통 명령(이름/조건/cap만 위 표대로 치환):

```sh
ORACLE_HOST=oracle-x86 "$S/oracle_run.sh" /Users/changmin/projects/ugrp-wt/s4-llm "$NAME" -- \
  .venv-sim/bin/python -m scripts.sim_cli workflow run zone-s4-live-dev-v157 --record "outputs/$NAME/managed" -- \
  --expected-source-sha "$SHA" --condition "$CONDITION" --cap-s "$CAP" \
  --relay-receipt /home/ubuntu/ugrp-sim/s4live1-relay.json \
  --output "outputs/$NAME/raw" --execute
```

SOURCE_SHA/COMMAND/EXIT, raw 요청·응답·영상·eval_only와 artifact manifest를 회수·해시 검증한다. 묶음 종료 뒤 한 번에 평가한다. 모델→명령 연결·오류/지연 거절·조건 배관 동일성을 판정하며 실제 운반 성공으로 확대하지 않는다. README/TensorBoard/push까지 수행하고 병합은 감독이 맡는다.

## 완료 결과 — 배관 확인, 연구 결과 아님

네 조건 모두 **90 SIM초 / EXIT0 / DEV_STAGE_FINISHED**. 실제 모델의 세 로봇 claim,
r3 새 `continue` 출발 허가, r3 물리 집기·상승·운반 명령 연결을 확인했다.
전체 raw 9시도(완료5 + 호스트 중단4), **28,687개 파일 서버/로컬 SHA256 일치**.
원본은 `/Users/changmin/projects/ugrp/outputs/oracle-runs/s4live1-*`,
서버는 `/home/ubuntu/ugrp-sim/runs/s4live1-*`; Git에는 요약·출처·해시만 보존한다.
[전체 판정](batch-audit.json) · [회수 검증](retrieval-verification.json) · [원장 대조](reconciliation.json).

| 조건 | 실제 모델 호출 | 입력 / 출력 / 보고 총 토큰 | 실행 wall초 | 응답 중앙 / 최대초 | r3 명령 | 접촉 상승 중 XY 이동 m |
|---|---:|---:|---:|---:|---:|---:|
| no_comm | 7 | 40,740 / 573 / 41,313 | 620.13 | 3.95 / 129.58 | 1299 | 1.0044 |
| peer_ko | 7 | 42,651 / 811 / 43,462 | 514.57 | 4.59 / 8.30 | 1278 | 1.0095 |
| leader_ko | 7 | 42,699 / 710 / 43,409 | 525.27 | 5.06 / 13.29 | 1298 | 1.0044 |
| structured | 7 | 43,423 / 873 / 44,589 | 572.46 | 5.23 / 64.49 | 1299 | 1.0044 |

- **결정→명령:** 모든 조건 r3 `call-0003-r3` claim → align/pick/lift, `call-0004-r3` continue → 운반 허가. 출발 창은 no_comm/leader/structured 31.35 SIM초, peer 32.65초에 열렸고 각각 34.55/34.65/34.55/35.85초에 허가됐다. 명령별 실제 응답 call_id·해제 시각 위반0. 출발 허가를 가진 이동 명령은 118/122/118/118개다.
- **물리 범위:** 최대 cyan COM 높이 약0.1603m. 이동은 두 손가락 접촉이 있고 COM>0.06m인 평가 표본의 처음 위치에서 최대 XY 거리다. 배달·정착/실물/E2E 성공이 아니며 `physical_success=null`, `research_result=false`. r1/r2는 claim-only이고 빔 이동/GO는 실행하지 않았다.
- **오류·지연:** API 오류0, 형식 실패0. 네 조건 모두 나중에 온 continue 1건씩은 닫힌 출발 창으로 거절됐고 기존 허가를 바꾸지 않았다. 429·비정상 completion·잘못된 claim·허가 전/만료 응답 거절은 오프라인에서 검증했다. 실제 고장 주입은 하지 않았다.
- **시계 경계:** no_comm 최초 r3 응답은 wall129.58초, structured 재응답은64.49초였다. 기존 scheduler는 토큰 기반 SIM 비용으로 응답을 해제하고 실제 HTTP wall 지연은 별도 기록한다. 10 SIM초 출발 제한은 실시간 wall deadline 검증이 아니다. 이 한 번의 시간 차이를 통신 효율 차이로 해석하지 않는다.
- **조건 배관:** source/scene/map/orders/seed/controller/heading/dev_light/weld/제한의 fingerprint가 네 조건에서 같고 system 고정 과금도952토큰으로 같다. 메시지는 no_comm0, peer3(mesh/free_ko), leader3(star/free_ko, r2 leader), structured2(mesh/schema). inbox와 scheduler 일치, no_comm 전달0·structured 자유문0·leader follower 간 전달0을 확인했다.
- **모델·비용:** 본 묶음28 POST / 보고172,773토큰. 스모크3건17,677토큰, 중단 시도12건73,721토큰도 보존했다(합43건264,171토큰). 43건 모두 wire/SQLite/프록시 영수증과 요청·응답·이미지 SHA256 일치. structured 마지막 r2 응답의 보고 총토큰은 입력+출력보다293개 커 원문을 보존하고 원인 미확인으로 표시했다. upstream 시도·과금·finish reason의 독립 확인은 안 됐고 USD는 미상이다.
- **종료·키:** 자기 릴레이/SSH 터널 종료, 서버 S4 프로세스·18391 listener 없음. 키는 읽거나 서버로 전송하지 않았다. 자기 실행 JSON/JSONL/log/command 526개와 relay identity 검사에서 키 패턴0, 점검 환경의 모델 키 변수0. 서버 전체 홈 디렉터리에 대한 전수 보증은 아니다. [종료 검사](server-post-run-audit.json).

### TensorBoard

[저장한 10개 pinned card 보기](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22evaluation%2Freported_success%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fwall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fsim_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_latency_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcarry_plumbing_pass%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fdeparture_accepted%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcontact_lift_xy_m%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Finfrastructure_interruptions%22%7D%5D&smoothing=0&runFilter=%5E%281010-s4live1-%7C1010-s3fix10-oracle%2Fviews__s3fix10-r2-cyan-%29#timeseries) · [대표 r3 입력 영상, 6×](http://127.0.0.1:6007/video/761b70dfde340d1a2c1b).
새 snapshot `1010-s4live1-batch`와 `1010-s4live1-smoke-hoststop`을 공용 logdir에 추가했다.
완료/중단을 구분하며, 중단 시도의 전체 runtime·성공은 미상으로 남겼다.
`evaluation/reported_success`는 S4 결정→운반 명령 연결 게이트다. S3 참고 실행의 물리 단계
게이트와 정의가 다르다. 함께 보이는 S3 cyan은 다른 SHA/설정/호스트/한도의 과거 참고자료로,
통신 비교 baseline이나 이번 묶음 분모가 아니다.
9개 자체 run·114 scalar의 실제 로딩/원본 해시와 영상5개의 HTTP Range206을 확인했다.
HParams 열은 case/policy/seed/source_sha, 조건은 case와 run 이름으로 구별한다.
[이벤트·UI 검증](tensorboard-verification.json) · [저장 RGB 영상 출처](video-provenance.json).

## 호스트 중단과 동일 묶음 재제출

실행 소스는 `6cffbc514200ee2aedda59ad65d75b1f2fe1d844`로 고정했다.
7.5 SIM초 스모크는 EXIT0으로 완료했다. 이후 네 조건 동시 실행 중
2026-10-10 **09:32:44Z 감독 자동 전원 끄기 버그**로 서버가 종료됐다.
감독이 09:39Z에 복구하고, 실행을 인식하지 못한 idle 판정 버그를 고쳤다고 통보했다.
감독이 남긴 EXIT143은 **HOST_INTERRUPTED**, 시뮬레이터 실패가 아니다.

중단된 네 폴더는 서버와 로컬에서 이름 뒤에 `-host-stop-093244Z`를 붙여 보존했다.
6,219개 파일을 모두 회수했고 서버/로컬 전체 SHA256 불일치0이다.
각 3건씩 실제 요청·응답이 durable 원장과 프록시 영수증에 일치한다.
종료 시점의 메모리 내 명령/스케줄러 기록은 완성되지 않았으므로 해당 시도의
운반·결정 연결 판정과 전체 runtime은 미확인으로 남긴다. 비용은 제외하지 않는다.

감독의 재실행 지시에 따라 **같은 네 명령·SHA·seed·cap**을 09:41:37Z에
동시에 재제출했고 네 제출 모두 0으로 승인됐다(실험 완료 EXIT와 별개).
서버 메모리 여유 6 GiB 미만 거부 규칙을 포함한 최신 `oracle_run.sh`를 사용했다.
명령·아카이브·제출 시각은 [host-interruption.json](host-interruption.json)에 있다.
스모크를 다시 실행하지 않았고, 묶음 사이 제어기·설정 변경도 없다.

## 오프라인 검증 범위

관련 3개 파일 46 PASS, Mac 물리/렌더/실제 모델 호출0.
[검증 기록](offline-validation.json). 새 stage 테스트는 CI 목록에도 등록했다.
실제 scheduler→S3 claim 연결, pair claim-only, 네 조건 공통 프롬프트 과금,
허가 전 응답·10 SIM초 이상 지연 응답·중복 출발 응답 거절,
프록시 identity/유효기간 거절을 확인했다. 실제 모델에 고장 응답을 주입한 시험은 아니다.

## 참고 자료

- [OpenSSH `ssh -R`](https://man.openbsd.org/ssh): 원격 루프백 바인딩과 암호화 전달. `ExitOnForwardFailure=yes`, agent forwarding off, 유한 세션, 종료 후 자기 tunnel만 정리한다.
- [RoCo (2023)](https://arxiv.org/abs/2307.04738): 언어 협의와 하위 실행을 분리하는 구조 참고. 논문 성능 재현 아님.
- [Hi Robot (2025)](https://arxiv.org/abs/2502.19417): 상위 의미 판단과 하위 운동 실행 분리 참고. 기존 S3 제어기를 유지한다.

2026-10-10 원문 초록/공식 매뉴얼 확인. 기존 completion의 upstream finish_reason 미검증 한계는 유지하며 proxy stop+valid JSON만 admission한다.

CI: 실행 SHA의 workflow plan fixture 누락은 수정 후 대상1 PASS. 기존 S3 오프라인 테스트2건은 MuJoCo 미설치로 실패해 [S3 PR에 전달](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/416#issuecomment-6096302154)했다. 전체 CI green/병합 완료를 주장하지 않는다.
