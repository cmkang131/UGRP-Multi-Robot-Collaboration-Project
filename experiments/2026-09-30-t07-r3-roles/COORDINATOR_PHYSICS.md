# T07 물리 인계 — 미실행, 12셀/10,800 SIM초 제안 상한

이 문서는 최소 진단 제안이다. 정상·실패 어느 셀도 아직 실행하지 않았다.
고정 r1/r2의 과거 성공은 다른 배정의 성공 근거로 사용하지 않는다.

## 실행 전 관문

1. T07과 P01 #305/P02 #307/P03 #312/P05 #308/P07 #311의 실제 merge SHA와
   검증 범위를 다시 기록한다. 각 PR이 아직 열려 있으면 null로 둔다. 합성 후보의
   controller 독립 검토와 기존 작은 사례 인수를 같은 고정 SHA에서 진행한다.
   이 sandbox에서는 렌더/물리 금지라 인수 실행을 시도하지 못했다.
2. 최종 MasterPi 3D 모델 v3 + walls_v3 + 표식 0 + weld OFF +
   cargo_noslip_v1. P01/P03의 v3 camera/model/provider/calibration 지원을 먼저
   닫는다. 기존 v2 보정을 v3로 이름만 바꾸거나 guard를 제거하지 않는다.
3. 하나의 새 dev 배치를 먼저 고정한다. T07 자체는 기존 M2 동서 빔 envelope를
   사용한다: 공개 coarse sheet `[1.0, 0.0, 0.0]`, 원본 setup 제안
   `[1.0, 0.05, 0.0]`, long_beam 1개, 목적지 B. 최종 지도에서 유효한지 정적
   검사를 먼저 통과해야 한다. 남북 원본 s3 빔 접근은 T08a/b의 별도 관문이다.
4. 동일 seed·3대 spawn assignment·짐 배치·지도/모델/보정·controller/config/
   sensor/memory 버전·상태 enum을 12셀에서 고정한다. 실제 reset spawn pose와
   robot ID 연결은 setup/eval 파일에 남긴다. 역할 교환을 쉽게 하려고 robot을
   정류장으로 옮기거나 camera/FOV를 바꾸지 않는다. 남는 로봇은 동일한 사전
   고정 hold 요청을 수행한다. 동료 private 상태에 따라 host가 양보시키지 않는다.
5. 실행 소스와 입력/설정을 커밋하고 source closure·role assignment·bundle
   해시를 별도로 고정한다. 새 bundle/workflow ID는 열린 PR 전체 최댓값을
   확인한 뒤 조정자가 예약한다. 기존 v81/v83 등의 성공·승인을 승계하지 않는다.
   `sim_cli` 관리 경로의 새 합성 설정에 고수준 role 요청을 연결한다. 기존
   prereg에는 이 옵션이 없으므로 이 문서만으로 실행 가능한 CLI라고 하지 않는다.
6. 공용 `agent_lock.py status/acquire`와 `disk_report.py`로 소유권·10 GiB 여유를
   확인하고 `ugrp_session.py run <고유이름> -- <등록 실행 명령>`을 사용한다.
   이 cap에는 외부 모델 호출이 없다. 고정 공개 고수준 요청을 각 actor가
   독립 제출한다. LLM 코호트는 별도 비용 승인·원장·상한 후에만 수행한다.

## 정확한 셀과 종료

공통 조건은 먼저 고정한 **no_comm + 기존 pair enum 채널**이다. 아래 12셀은
4조건 효과 비교가 아니다. 네 조건 확대는 동일 설정의 별도 코호트로 등록한다.

| 배정 ID | end_neg | end_pos | 정상 셀 | 실패 셀 | 각 셀 cap |
|---|---|---|---|---|---:|
| r12 | r1 | r2 | r12-normal | r12-endpos-fault | 900 |
| r21 | r2 | r1 | r21-normal | r21-endpos-fault | 900 |
| r13 | r1 | r3 | r13-normal | r13-endpos-fault | 900 |
| r31 | r3 | r1 | r31-normal | r31-endpos-fault | 900 |
| r23 | r2 | r3 | r23-normal | r23-endpos-fault | 900 |
| r32 | r3 | r2 | r32-normal | r32-endpos-fault | 900 |

실패 셀은 사전 고정한 end_pos actor의 첫 close 발행부터 jaw-open fault를
유지한다. 기존 `JawOverridePort`처럼 evaluator/실험자 출력 경로에서만
주입하고 controller는 자기 발행 명령과 자기 RGB만 받는다. 발행 close가
없는 경우 fault 미도달로 남긴다. 결과를 보고 반대 역할로 바꾸지 않는다.
이 6개 실패는 양 역할 전체의 실패 커버리지가 아니며 end_neg 실패는 별도다.

- SIM 시계는 reset 이후 staging·팔 전이·대기·관측·실패 종료를 모두 포함한다.
  900초 도달은 실패/미도달이다. 한 후보의 전체 상한은 **12×900=10,800초**다.
- 정상은 실제 spawn→접근→양끝 정렬→동시 파지/들기→문 통과→B 운반→방출을
  연속 확인한다. stage probe/teacher 재초기화는 그 셀의 정상 성공이 아니다.
  evaluator의 전체 물체 footprint·바닥·정지·비파지 settle 기준을 충족해야 한다.
  `PAIR_SEQUENCE_DONE`/own job done만으로 성공 처리하지 않는다.
- 실패는 own RGB 실패 또는 enum abort/heartbeat timeout 뒤 두 참여자의 hold,
  arm/base 예약 취소, 과거 task의 후속 명령 0개를 검사한다. fault 적용시각,
  own 관측시각, 최초 local failure/abort 송신, 상대 수신/정지, 마지막 명령시각을
  각각 기록한다. 제3 로봇 포트에 pair의 arm/base 명령이 한 개라도 나오면 실패다.
- 같은 구성에서 정상 성공과 실패 안전이 모두 확인된 배정만 그 **배정/배치**의
  지원으로 적는다. 접근 실패·비대칭 카메라 품질·fault 미도달은 다른 셀 성공으로
  덮지 않는다. 정식 s3의 r3 12–52초 hold 효과·재배정은 T12에서 따로 검증한다.

## 원본·분모·TensorBoard

각 셀은 primary `/Users/changmin/projects/ugrp/outputs/t07-r3-roles/<새-cohort>/<cell>/`
새 경로에 저장한다. 존재하면 실행을 거부한다. 재시도는 새 run ID이며 실패 원본을
덮지 않는다. source/config/input/role/controller 해시, 실효 모델·provider·환경,
정확한 spawn, 원본 자기 RGB/명령/enum/고수준 요청·ack·job ID, eval-only 자료,
staging 포함 SIM초, 명령/관측 수, 실패 이유와 fault 적용/미도달을 보존한다.

총 배정 12개, 정상 6개, 실패 6개 분모를 먼저 보고한다. 완료/거절/미도달/
HOST_ERROR를 모두 남긴다. ENOSPC는 HOST_ERROR다. 성공률은 정상 성공/6과
실패 안전/6을 분리하고 배정별 1/1 또는 0/1도 표시한다. cohort 중 미완료는
완료 수에 넣지 않는다. 비용은 실제 모델 0회인지 원장/명령과 대조한다.

완료 결과와 실패 모두 `docs/tensorboard.md`에 따라 새 snapshot에 추가한다.
기존 manifest의 경로·해시로 중복 변환을 피하고 원본을 보존한다. primary
`outputs/tensorboard` viewer 소유권·PID·logdir, 새 영상 등록, 실제 데이터
readback, `outputs/tensorboard-view.json`의 pinned success/runtime/command/
model-call/response-time와 HParams 컬럼을 확인한다. 기준 배정을 함께 보여 주고
대시보드 링크·표시 확인 범위·미완료 변환을 결과 보고에 적는다.
