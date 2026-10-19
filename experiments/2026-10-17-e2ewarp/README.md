# e2ewarp — MJWarp LLM E2E 통합 후보, NOT_READY

Draft PR [#570](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/570).
**정지 조건인 ‘LLM + 자기 지도 + 처음→끝 실제 운반의 한 실행 성공’은 미달이다.**
새 실행기·Mac 중계·입력 경계·부품 조합 경로를 구현했지만 ACT 학생/지도/내려놓기
부품의 실제 인수는 남아 있다. CPU 실행기는 수정하지 않았다. [설계](design.md),
[전체 시도 요약](summary.json), [부품 대기 설정](components.pending.json).

## 확인한 결과

gcp6, `ugrp-sim-f-1016` / `kcm5781kcm5781@gmail.com`, g2-standard-8 L4.
실제 MJWarp 실행 소스는 **`e0e1244839d993424cd232836c55357e49ac7d51`**,
`e2e-warp-batch-v446` / 기본 off `e2e_warp_batch_v1`이다. 서로 다른 소스/조건/세계 수,
CPU, noslip10 결과를 합산하지 않는다.

| 시도 | 소스 | 세계·조건 | SIM | 실제 모델 호출 | 종료/원인 |
|---|---|---|---:|---:|---|
| R1 | b8270d07b | 1, no_comm | 0 | 0 | HOST_ERROR: backend/core vendor ABI 불일치. 같은 소스 core로 교체 |
| R2 | fb651f59c | 1, no_comm | 22.1 | 0 | 중계 Journal의 64자리 hex 키 계약 오류. 클라이언트9회 모두400, 원본 확인 즉시 감독 중단 |
| R3 | e0e124483 | 2, peer_ko | 30 | 18 | 지정 진단 SIM 예산으로 cap_end. 학생·운반 실행0 |

R2 원본 `result.model_calls=9`는 클라이언트 요청 수였다. 원본은 보존하고
[독립 재계수](r2/review.json)에 상류0을 명시했다. 이후 코드에서 클라이언트 요청과
실제 upstream attempts를 분리했다. R2 traceback의 KeyboardInterrupt는 감독 중단이며
색 검출기 실패로 판정하지 않는다.

R3는 각 세계의 r1/r2/r3가 자기 RGB를 받아 검사할 주문을 골랐다. 실제 요청/응답,
18개 공급자 사용량과 Mac 원장의 call ID·요청 SHA·상류 attempts가 모두 일치했다.
[원본 재계수](r3/review.json), [중계 대조](r3/relay-reconciliation.json),
[runtime manifest](r3/runtime-applied.json), [첫30](r3/first30.json).

| 첫30 지표 | 값 |
|---|---:|
| 정상 응답/실제 모델 호출 | 18/18 |
| 형식 오류 / HTTP·상류429 | 0 / 0·0 |
| 호출당 prompt_tokens 중앙값 | 4,691 |
| prompt / total tokens | 76,816 / 77,084 |
| cached_tokens / 비율 | 34,944 / 45.4905% |
| 토큰 / (SIM초×세계) | 1,284.7333 |
| 토큰 / 묶음 SIM초 | 2,569.4667 |
| 응답 wall 중앙값 | 1.20784초 |
| 공급자 보고 비용 합 | $0.00777272 |
| 자기 JPEG SHA / 캐시 순서 검사 | 18/18 · 18/18 |
| 묶음 wall / SIM | 352.8227 / 30 = 11.76076 |
| wall / (SIM×세계) | **5.88038** |

속도는 기록 전용이다. 초기 구성 포함 총 wall은363.2508초이며 위352.8227초와
구분한다. [backend 시간](r3/backend-timings.json)은 physics256.3400초,
명령 decode/upload52.0449초다. CPU와의 속도 비교·운반 성공 측정은 아니다.
같은 초기 상태/장면/공급자의 CPU 첫30 기준 실행은 없어 토큰 기준선과 직접 비교하지 않았다.
스모크의0/10/20 SIM초 호출 스케줄은 본 임무의 이벤트 기반 호출 비용을 예측하지 않는다.

CoreWeave/fp4·fallback false, 자기 JPEG1장을 전달한 요청의 Mac 수신 SHA를 확인했다.
공급자 usage의 image_tokens는0으로 보고됐다. 전송 증거와 공급자의 실제 시각 활용·과제
정확도 검증을 구분한다. 실제 peer 메시지는0건으로, 네 조건의 채널 격리는 단위 시험
범위이며 실시간 통신 효과를 입증하지 않았다.

## 자기 지도 관문에서 발견한 결함

[funnel](r3/rejection_table.json)은 **1806 자기 RGB → FK1806 → 안정된 벽 관측48 →
키프레임0**이다. 최종 지도가 만들어졌다고 보고하지 않는다. LK measured48도 자기 위치
정확도·정적 지도 정합·운반 성공을 뜻하지 않는다.

[수정 전 거부 분포](r3/frame-rejection-distribution.json)의 큰 항목은 camera qualification
1758/1806이다(bootstrap6, servo 변경90, 기존2.25초 settling1662). 이 상수는 근거 없이
줄이지 않고 owner/native 카메라 자격 인수를 기다린다. 별도로, 허용된 벽 관측48개를
`tick % 10 == 0` 조건이 전부 놓친 통합기 결함을 확인했다. virtual_scan의 hit가 있으면
segment가 하나 이상 생기는 코드와 정상 종료·inserted0을 대조한 판정이다.

후속 **기본 off `--map-keyframe-admission elapsed_sim_v1`**은 owner의 기존
`CSMOptions.keyframe_interval_s=1 SIM초`를 마지막 수용 프레임부터 재는 방식으로
연결한다. 불규칙한 허용 프레임이 정각과 어긋나는 회귀 사례를 단위 시험으로 확인했다.
R3의 old modulo 동작은 off로 보존한다. **수정 뒤 GPU 재실행은 하지 않았다**(3라운드 소진).
새 후보의 지도 관문과 실제 운반은 다시 검증해야 한다.

## 최종 코드와 검증 범위

- 새 `run_e2e_warp.py`, native initializer, own-input runtime/relay와 표준 workflow를 추가했다.
  native `put_model/put_data/step/render`, noslip0이며 legacy plane·C 동등성 shims를 사용하지 않는다.
- 후속 `e2e_warp_mission.py`는 LLM task/집기/운반/놓기 승인 → 지도 코드 → ACT 청크 →
  자기 RGB 확인 → 실제 release 위치 재획득 → 다음 작업을 조합한다. owner가 또 다른
  전체 E2E 제어기를 만들 필요 없이 navigation/release 어댑터 두 개를 연결한다.
  학생 입력은 기존 이미지/명령 이력+이산 토큰이고, GPU actor 로딩은 artifact hash·native
  provenance로 차단한다. 실제 checkpoint 로딩/추론·새 mission 흐름은 물리 미검증이다.
- 최종 Mac 검증은 비물리24 tests pass(통합23 + workflow 계획1), compile/whitespace, vendor334 SHA 일치다.
  source/native smoke는 위 e0e124483에 한정하며 후속 mission 조합/키프레임 후보에
  그 물리 결과를 승계하지 않는다. Mac 물리 step/render0, 추가 GPU 라운드0.
- 후속 **eval-only evaluator** `harness/e2ewarp_evaluator.py`를 추가했다. 제어 종료 뒤
  `evaluation-state.npz`/`eval-geometry.json`만 읽어 `physical-evaluation.json`을 쓰고,
  zone B base·cargo landing·door aperture·same episode·self-map 원장을 판정한다.
  누락/파손/SHA 불일치는 fail-closed HOST_ERROR이며 agent claim은 읽지 않는다. 합성
  fixture 30 tests pass, manifest `ready`+SHA 배선, 기본 smoke/CLI 경로 불변. 실제 장면
  통합·물리 실행은 아직 없다([evaluator.md](evaluator.md)).
- queue와 실제 XML/manifest의 current_stack 점검은 pass이지만
  localization/nearfield/setdown **3개 승인된 smoke 이탈**이 있어 current_compliant=false다.
  [점검 결과](r3/runtime-stack-check.json)의 선언 범위와 실제 관문 증거를 구분한다.

최신 stackaudit `45623168`에는 영어 대화와 `selfmap_map_correction=on`이 추가됐다.
새 조건은 `no_comm/peer_en/leader_en/structured`이고 topology 검증만 기존 계약으로
투영한다. full mission은 mapbuild8의 이동량 예측 → 자기 지도 축적 → 사전 창 안에서
자기 지도·정적 지도와 주변 인식 정합·위치 보정이 준비돼야 한다. ready manifest와
매 관측의 map_correction_active를 검사하고 odometry-only 어댑터는 차단한다.
R3의 원본 `peer_ko`와 지도 보정 off는 그대로 보존하며 **최신 요구에는 미준수**다
([후행 점검](r3/latest-policy-review.json)). 최신 설정 준비는
[선언 검사](latest-policy-admission.json)에서만 통과했고 새 물리 검증은 없다.

이전 CI는 새 workflow의 read-only 계획 예제 누락으로1건 실패했다. 예제를 추가해
해당 검사와 통합 단위 시험을 함께24건 통과했다([CI 기록](ci-review.json)). 최신 CI
결과는 draft PR에서 별도로 확인한다.

## 남은 의존 / ops-alert 상태 (종료 시 확인)

| 부품 | 소유자 | 최신 수신 / 남은 것 |
|---|---|---|
| native ACT 최종 학생 | act16w4, PR539 | owner ops 보고: A/B10000 step·재로딩 완료, VAL8 A0/8·B0/8(정렬 탈락 각8/8), h4 새 학습 시작. 선택/public artifact/독립 성공 인수 미수신 |
| LK/RBPF 실제 운반 판정 | mapbuild8, PR556 | mapbuild6 운반 진입0 / NOT_READY. 02:24 scope-ack, 실제 경로 OFF/ON 판정06:00 KST 예상 |
| 운반 자세 명령 FK | mapbuild8 | 02:24 scope-ack. 보정/FK API 예상04:15 KST. 기존 grip<=1600 거부 유지, 승인된 loaded API 미수신 |
| 자기 RGB→정적 지도 초기/주기 정합 | mapbuild8 | 이동량 사전 창에서 자기 지도·정적 지도 정합 필수. 사전 창 표03:15, API04:15, 실제 경로06:00 KST 예상. spawn/평가 앵커 금지 |
| release_reloc_selfmap_v1 | warp8f, PR557 | warp8e 관측 어댑터 byte vendor. 오프라인14세계 CSM0/28 채택(모호17/관측부족11); mapbuild8 보정 API 뒤 재평가, A40/B40 보류 |
| noslip0 | nsoff PR568 / warpfit2 PR562 | byte vendor/runtime GPU0 확인. nsoff 최신 CI 이슈는 소유자 담당, 원본 변경0 |
| current_stack/checker | stackaudit PR569 | 최신45623168 byte vendor. R3 원본 점검은8fc1b1bc; 최신 기준 재판정 별도 |
| 이 작업 키프레임 수정 | e2ewarp PR570 | 코드·회귀 시험만. 수정 후 실제 지도 삽입/운반 미검증 |

공용 ops-alert에 ownership/latest-ack, 설계 완료, 첫30 점검, 종료를 append했다.
부품이 없는 상태에서 교사/손짠 파지/출발 좌표 정답으로 메우지 않는다. full mission은
`components.pending.json`으로 준비 단계부터 거부된다. 부품 readiness·factory·증거와
ACT inventory가 채워지기 전 제출하지 않는다.

## 원본·영상·호스트 종료

원본은 `gcp6:/home/ugrp/ugrp-sim/runs/e2ewarp-r{1,2,3}`에 남는다.
[원본1456개 재해시](r3/integrity-originals.json) mismatch0,
[대형 JSON7개 무손실 압축](r3/packing.json)·해제 SHA 일치,
[원격 manifest SHA](r3/remote-manifest-hashes.json)를 기록했다. packed 원본은
`zstd -dc <원래경로>.zst`로 복원하며 원래 sha256.json의 바이트 해시와 비교한다.
원격 raw 전체를 Mac/GitHub에 백업했다고 주장하지 않는다.

Mac에는 요약·가벼운 원장·검토 영상/띠만 회수했다.
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/playback/e2ewarp-r2/`, `e2ewarp-r3/`.
R2 0–22 SIM초1Hz와12.1–22.1초10Hz, R3 두 세계0–30초2Hz와20–30초10Hz 띠를
직접 확인했다. R3 r1/r2/r3의0/6/12/18/24/30초도 확인했다. 시간순으로 초기 정면 →
좌/중/우 팬 →10·20초 새 검사 →반복 팬이 보이며, R2는 검사 선택이 실행되지 않아
정면 영상이 유지됐다. 물체 파지·이송·낙하의 영상 증거는 없다. ffmpeg3배속 영상은
ffprobe로만 확인했고 Mac 화면 앱은 열지 않았다.

실행 없는 lease/GPU/Python0을 확인한 뒤 **gcp6 TERMINATED, 2026-10-17 02:05:09 KST**를
live 조회했다([정지](r3/shutdown.json), [정지 전](r3/pre-stop.json)).
idle20/budget-stop 유지, VM wall cap 없음. Mac 중계·자기 SSH tunnel도 종료했다.

초기 source ship의 공용 Git shallow6개는 누락 ancestor32188개를 한 번 보충하고
전체51032개 도달 객체 missing0을 확인한 뒤 원 shallow 파일을 보존하며 해제했다.
[복구 기록](r3/source-repair.json). 공유 object store/기존 ref를 지우거나 gc/prune하지
않았고, 각 source clone은 공용 git-shared.git에 직접 reference한다.

재현/다음 제출은 [reproduce.md](reproduce.md), 부품 ABI는
`harness/e2e_warp_mission.py`의 docstring과 설계서를 따른다.
