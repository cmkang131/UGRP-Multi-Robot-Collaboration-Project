# warp9 — gcp4 단독 계측·세 번째 처리량 중단 (NOT_READY)

warp7/PR #550(`claude/warp5`) 후속이다. 사용자 "모두 MJWarp로 바꿔서 하게"의 전체 위치 추정·운반·LLM E2E 이관은 **미완료**다. 같은 처리량 결함이 R1/R2/R3에 남아 사용자 중단 규칙을 적용했다. 새 관문·모델 호출을 제출하지 않았다.

## 조사와 단독 계측

[공식 문서·공개 코드와 보존 원문](references.md)을 먼저 읽었다. GPU 물리는 gcp4(`ugrp-sim-d-1016` / `ugrp-act-l4-gcp4`, g2-standard-8·L4), CPU 분석은 gcp2다. gcp3의 자기 대기 PID13017만 정리했고 warp8 임대는 불변이다([증거](resume2/gcp3-wait-cleanup.json)). gcp2 L4는 사용하지 않았다.

[1·4·16·64 분리 표](resume2/final-v2/timing-table.md), [전체 비용 순위/해시](resume2/final-v2/scaling.json). R1 source `4476e810cad7160d586cd30a4188b9150fe3bea8`, 같은 초기 장면 하나를 명시적으로 복제한 0.3 SIM초 진단이다. 독립 임무 성공 시행이 아니다. setup/JIT 제외, 계측용 event·추가 동기화가 있는 수치이며 각 열은 중복되어 더할 수 없다.

|N|상태|물리 GPU event 초|렌더 GPU event 초|렌더 CPU 초|제어/명령 Python 초|D2H blocking 초 / GB|
|---:|---|---:|---:|---:|---:|---:|
|1|완료|6.1665|0.0655|0.3807|0.5622|0.1529 / 0.4847|
|4|완료|7.3272|0.1327|1.4722|0.9240|0.4935 / 1.9475|
|16|완료|10.8574|0.4183|6.7481|2.5776|3.3784 / 7.9317|
|64|HOST_ERROR|미측정|미측정|미측정|미측정|미측정|

N64는 PID25704가 호스트 OOM으로 SIGKILL됐다(anon RSS31,523,792 KiB ≈30.06 GiB). finalizer/summary가 실행되지 않았으므로 완료 시각·0초로 채우지 않는다. [커널 근거와 사유](resume2/n64-failure-evidence.json). 별도 shared gcp2 warp7 R3의 0.4 SIM초/145.099 wall초, command+physics97.792초·render+평가복사35.126초와 합산하거나 직접 가속 배율로 해석하지 않는다.

## 가장 큰 구간의 후보와 결과

R2/R3 source `3da542d67465fc9a1275c3c1a27dc404d7dae3d6`. [세 라운드 전체 수치](resume2/final-v2/variants.json), [상태 비교](resume2/final-v2/state-comparison.json), [사유·관문 funnel](resume2/final-v2/rejection-table.json).

|라운드|N16 고정 0.3 SIM초 wall초|물리 GPU event 초|해석|
|---|---:|---:|---|
|R1 기존16틱 graph×25|24.986|10.857|분리 계측|
|R2 공식 EventTracer 추가|26.098|11.211|세부 계측, 성능 후보 아님|
|R3 전용 NoSlip 버퍼+400틱 graph×1|29.099|11.928|개선 없음·미채택|

R2 마지막 graph 조각16틱에서 `/step`0.148061초 중 `noslip`0.125856초(약85%)였다. **마지막 조각**의 event 구간이며 400틱 전체의 커널 busy 합계로 확대하지 않는다. [원본 세부 trace](resume2/final-v2/physics-event-trace.json).

기본 off `warp9_full_period_graph_v1`은 동일한400틱을 한 graph로 capture한다. `warp9_noslip_scratch_v1`은 pinned NoSlip 함수의 L/Y/A 할당3개만 전용 버퍼 조회로 바꾸고 원래 커널·인수·산술 순서를 보존한다. 임시 버퍼7,144,448 bytes, source/AST 해시를 원본 summary에 남겼다. 상수는 원래 period/dt/shape에서 계산하며 새 수용 오차를 넣지 않았다.

실제 기록에서 dt·NoSlip10·solver·iterations·ls_iterations·float32 numerics는 같고 초기 qpos/epoch 원장과 최종 issued ctrl도 같다. 최종 qpos/qvel/qacc_warmstart는 비트 동일하지 않다. qpos 최대 차5.6608e-4는 혼합 좌표 단위이며 위치 오차 m로 해석하지 않는다. 기준 배치의 동일 초기 복제 사이에도 차이가 있어 버퍼/graph 효과와 GPU 비결정성을 분리하지 못했다. 속도 개선도 없어 후보를 채택하지 않는다. 두 토글 모두 기본 off다.

## 검증 범위·운영

- 완료한 고정 작업5개(N1/N4/N16/R2 N16/R3 N16)와 N64 HOST_ERROR1개를 모두 기록했다. raw world 결과의 `HOST_ERROR`/빈 error는 profile 종료 후 `lane.close()`의 GeneratorExit 기록이며 그대로 보존하고, 분석 사유는 `fixed_work_profile_end`로 별도 명시했다. 임무 유효 분모는0이다.
- 첫30 SIM초·운반 진입·place·완주·held 구간 감사·LLM E2E는 미실행이다. `cap_end=0`, 모델 호출0. 초기 감사의0을 운반/held 감사 통과로 확대하지 않는다. CoreWeave fp4 등록 오류의 오프라인 수정은 보존했으나 Mac 중계·실제 E2E 연결은 미검증이다.
- **n4 CPU 제어+L4 물리 소유자 분리는 미구현**이다. 원본을 n4에서 분석한 것을 제어 분리로 보고하지 않는다. N64 메모리 경로도 해결되지 않았다. 세 번째 처리량 중단 뒤 새 실행을 내지 않았다.
- 변경 관련 비물리 **20 passed**, diff 검사 통과. 전체 CI·병합·학생 임무 성공을 주장하지 않는다([검증](resume2/validation.json)).
- gcp4 완료 원본1,067파일 SHA 불일치0. 원본은 gcp4 영속디스크, 분석 사본은 gcp2에 보존했다. Mac 회수는 요약·작은 검토 영상·프레임 띠뿐이다. [회수·검토](resume2/playback-review.json), [원본 검사·임대 해제](resume2/gcp4-lifecycle-before-stop.json).
- gcp4 자기 임대/프로세스·GPU PID0, 다른 임대0을 확인한 뒤 VM **TERMINATED** 확인([최종 상태](resume2/gcp4-final-state.json)). 실행 상한을 넣지 않았고 유휴20분·budget-stop은 유지했다. gcp2는 자기 분석 임대만 제거하고 VM 정지 시도0이다. Mac 물리/렌더/GUI·VM 키/에이전트 자격 증명 복사0이다.

재현 명령과 원본 경로는 각 queue/dispatch와 [최종 summary](resume2/final-v2/summary.json), [분석 스크립트](analyze_resume2.py)에 있다. 재개 시에도 다른 호스트 결과를 합산하지 않는다.

## 1회차 진행 기록

- 공식 MJWarp/Warp/Playground 구현을 조사하고 원문·SHA를 보존했다.
- 기본 off `warp9_profile_v1`에 physics CUDA event, host submit/wait, Python command/controller, render·D2H·평가 export 계측을 넣었다. 실운전 속도는 무계측으로 따로 확인한다.
- 설치된 `get_data_into`가 세계별로 전체 배열을 반복 readback하는 경로와 카메라별 동기화/매번 할당을 확인했다. **정적 병목 후보이며 비중은 아직 미측정**이다.
- frozen E2E source27436b8의 CoreWeave `REGISTERED_RATE_POLICY_REQUIRED`를 실제 원문 fixture로 재현했다. `warp9_coreweave_rate_v1`은 정확한 CoreWeave fp4 선택을 등록하고 기존 재시도 한도를 유지한다. 지출 예약에 CoreWeave 가격을 적용한다. 실제 Mac 중계/LLM E2E 연결은 남아 있다.
- gcp3는 warp8 임대와 GPU PID5614가 있어 계측 미제출. gcp2 L4는 사용하지 않았다. gcp2 원본은 삭제/변경하지 않았다. 모델 감시 경보0.

검증: 관련 비물리 **39 passed**, `git diff --check` 통과. 실행 소스 `16a946ff342e957d65cace56055b8067d9bb4296`를 PR #550에 push했고, gcp3 shared bare를 참조한 clean detached clone을 만들었다. 유한 계측 대기 실행기는 `/home/ugrp/ugrp-sim/runs/warp9/profile-r1/status.json`에 상태를 남긴다. 대기 중 GPU context·임대를 만들지 않으며, 모든 기존 임대와 GPU PID가 사라진 뒤에만 자기 임대를 획득하고 4크기×0.3 SIM초를 계측한다. 최적화나 임무 관문은 자동 제출하지 않는다.

gcp3 Compute Engine scheduling 조회에서 `maxRunDuration`·`terminationTime`가 없는 것을 확인했다. 8h 상한을 다시 넣지 않았고 VM lifecycle 변경0이다. 대기 실행기는 고정 SIM 작업만 수행하며, 유휴20분·budget-stop을 변경하지 않는다.

첫30 실행기는 기존 평균 기록을 문서 기준 중앙값으로 바꾸고 >6.0에서 중단하도록 수정했다(`41481b5a9`). 이는 비물리 회귀 검증만 완료됐고, 실제 첫30 SIM초는 아직 없다. 분석기는 완료 표지 뒤 profile 원본이 없으면 오류로 남긴다. CI 목록에 새 비물리 검사4개가 포함된다.
