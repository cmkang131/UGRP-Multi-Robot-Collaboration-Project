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

## 참고 자료

- [OpenSSH `ssh -R`](https://man.openbsd.org/ssh): 원격 루프백 바인딩과 암호화 전달. `ExitOnForwardFailure=yes`, agent forwarding off, 유한 세션, 종료 후 자기 tunnel만 정리한다.
- [RoCo (2023)](https://arxiv.org/abs/2307.04738): 언어 협의와 하위 실행을 분리하는 구조 참고. 논문 성능 재현 아님.
- [Hi Robot (2025)](https://arxiv.org/abs/2502.19417): 상위 의미 판단과 하위 운동 실행 분리 참고. 기존 S3 제어기를 유지한다.

2026-10-10 원문 초록/공식 매뉴얼 확인. 기존 completion의 upstream finish_reason 미검증 한계는 유지하며 proxy stop+valid JSON만 admission한다.
