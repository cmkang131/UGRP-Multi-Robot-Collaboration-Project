# warp9 — 조사·계측 준비, 단독 GPU 대기

사용자 "모두 MJWarp로 바꿔서 하게"에 따라 warp7/PR #550(`claude/warp5`)을 이어 간다. 현재 **NOT_READY**. 위치 추정·운반·place·완주·실제 LLM E2E 완료를 주장하지 않는다.

[참고 자료](references.md), [warp7 R3 원본 대기열](warp7-r3-queue.json). R3는 shared gcp2 L4, command+physics97.792s / render+평가복사35.126s, 0.4 SIM초/loop145.099s였다. 순수 물리·렌더 수치로 재해석하지 않는다.

## 진행

- 공식 MJWarp/Warp/Playground 구현을 조사하고 원문·SHA를 보존했다.
- 기본 off `warp9_profile_v1`에 physics CUDA event, host submit/wait, Python command/controller, render·D2H·평가 export 계측을 넣었다. 실운전 속도는 무계측으로 따로 확인한다.
- 설치된 `get_data_into`가 세계별로 전체 배열을 반복 readback하는 경로와 카메라별 동기화/매번 할당을 확인했다. **정적 병목 후보이며 비중은 아직 미측정**이다.
- frozen E2E source27436b8의 CoreWeave `REGISTERED_RATE_POLICY_REQUIRED`를 실제 원문 fixture로 재현했다. `warp9_coreweave_rate_v1`은 정확한 CoreWeave fp4 선택을 등록하고 기존 재시도 한도를 유지한다. 지출 예약에 CoreWeave 가격을 적용한다. 실제 Mac 중계/LLM E2E 연결은 남아 있다.
- gcp3는 warp8 임대와 GPU PID5614가 있어 계측 미제출. gcp2 L4는 사용하지 않았다. gcp2 원본은 삭제/변경하지 않았다. 모델 감시 경보0.

검증: 관련 비물리 **37 passed**, `git diff --check` 통과. 실행 소스 `16a946ff342e957d65cace56055b8067d9bb4296`를 PR #550에 push했고, gcp3 shared bare를 참조한 clean detached clone을 만들었다. 유한 계측 대기 실행기는 `/home/ugrp/ugrp-sim/runs/warp9/profile-r1/status.json`에 상태를 남긴다. 대기 중 GPU context·임대를 만들지 않으며, 모든 기존 임대와 GPU PID가 사라진 뒤에만 자기 임대를 획득하고 4크기×0.3 SIM초를 계측한다. 최적화나 임무 관문은 자동 제출하지 않는다.

gcp3 Compute Engine scheduling 조회에서 `maxRunDuration`·`terminationTime`가 없는 것을 확인했다. 8h 상한을 다시 넣지 않았고 VM lifecycle 변경0이다. 대기 실행기는 고정 SIM 작업만 수행하며, 유휴20분·budget-stop을 변경하지 않는다.

## 남은 관문

1. warp8 임대 해제 후 gcp3 단독 1·4·16·64세계 분리 계측과 거부/비용 표.
2. 가장 큰 원인 수정, n4 제어/L4 물리 분리와 무계측 속도 확인. NoSlip·dt·solver 유지.
3. N16 첫30 SIM초·운반·place·완주, 실패/성공 재생·관문 funnel·입력 감사.
4. CoreWeave fp4 Mac 중계·ACT 연결·LLM 첫30 점검. 같은 결함3라운드 중단.

원본은 GCP에 보존하고 Mac에는 요약·몽타주·실패 프레임만 회수한다. 유휴20분·budget-stop을 유지한다. 다른 작업 임대·프로세스·VM을 정지하지 않는다.
