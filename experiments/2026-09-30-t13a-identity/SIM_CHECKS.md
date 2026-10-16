# T13a 조정자 인계 — 정상 1 + 모호한 실패 1, 총 1,800 SIM초 cap

**아직 실행하지 않은 최소 진단 제안.** 구현 PR의 fake 통과와 물리 준비/물리 성공을 구분한다.
이 sandbox에서는 World/Scene/렌더/시뮬레이션/비전 모델/LLM을 실행하지 않는다.

## 실행 전 차단 조건

1. P01/P02/P03/P05/P07의 실제 병합 SHA와 독립 검토 범위를 다시 확인한다. 최종 MasterPi v3,
   walls_v3(0.40 m), 표식 0, 원래 카메라 배치/FOV, weld OFF, cargo_noslip_v1를 고정한다.
   임의 v2 provider/운동 보정을 v3에 승계하지 않는다. 기존 정식 s1–s6는 바이트 그대로 둔다.
2. 이 후보는 아직 specific item과 RGB를 연결할 인식 단서가 없다. 먼저 저장된 자기 RGB에서
   공개 specific 요청을 정답 없이 구분 가능한지 확인한다. 단서가 없으면 정상 셀도
   `UNSUPPORTED_SPECIFIC_GROUNDING / 미실행`이다. 이름/색/초기 slot/장면 item lookup으로
   통과시키지 않는다. 새 관측 정보 설계·자료 수집 비용은 **미산정**이며 이 cap에 포함하지 않는다.
3. 인식 단서를 확정한 새 후보에서 target-aware 하위 backend를 연결하고 fake 회귀/검토한다.
   `submit_target/refresh_target/cancel_target`이 frame별 지정 detection만 사용하는지 검사한다.
   현재 기존 `ZoneOwnExecutor`는 이 API를 구현하지 않는다. 이 인계 문서만으로 runnable이
   되지 않으며 존재하지 않는 CLI 옵션/실행 bundle을 제시하지 않는다.
4. 확정된 코드/입력/인식기/카메라·모델/지도·보정/센서/자기 기억/명령 궤적/관측 주기를 커밋하고
   공통 bundle·표준 `sim_cli` workflow를 새로 고정한다. 실행 중 소스는 불변이다. 조건에 따른
   제어 override는 없다. role assignment hash와 controller/config hash는 **별도 필드**다.
   no_comm/peer_ko/leader_ko/structured의 차이는 통신 허용 범위뿐이다. 아래 두 셀은 4조건
   효과 코호트가 아니며, 한 조건에서 검사했다고 나머지 조건의 물리 성공으로 복제하지 않는다.
5. 자기 worktree와 관리 session에서 실행한다. `agent_lock.py acquire`로 공용 잠금 획득,
   10 GiB 여유·부하·PID/소유 확인, primary `outputs/t13a-identity-<후보>-<새 run>/`를 사용한다.
   사용한 raw 경로/실패 결과는 재사용·덮어쓰기하지 않는다. 다른 작업은 중지하지 않는다.

## 고정할 셀과 판정

| 셀 | 사전 고정 입력/동작 | 관측/평가 기준 | cap |
|---|---|---|---:|
| I1 정상 재탐색 | 별도 dev fixture. 공개 `order-identity`와 `cyan_1`을 다른 ID로 유지. cyan 특정 물체를 관측→접근→자기 관측으로 놓쳤다고 판단→재탐색→다시 잡기→A 방출. 가시 이동 경로/가림 길이/인식 단서·고정 action을 실행 전 저장 | 이름 기반 동일성은 금지. 저장 own RGB/track 연속성 또는 별도 검토한 시각적 재식별 근거가 있어야 한다. 미파지와 경로 실패도 기록. 하위 완료·자기 claim·eval의 정확한 개체 도착을 각각 대조 | staging/reset 포함 900 SIM초 |
| I2 동일 색 교환/가림 실패 | I1과 동일 코드·공통 구성의 별도 dev fixture에 같은 색 물체 2개. 공개 주문은 `cyan_1` 하나. 평가 전용 setup에서 대상 교환/가림을 미리 정하고 actor에 사건 시각·GT 매핑을 주지 않는다. actor는 동일 고정 action으로 계속 관측 | 구분 불가능하면 unknown→재탐색→실패, 잘못된 대상 배송 후 성공 claim 0. local token을 바꿔 같은 물체를 두 번 세지 않음. cancel 뒤 원래 job 명령 잔류 0. 실제 미파지/오인식/가림 성립 여부는 eval_only에서 확인 | staging/reset 포함 900 SIM초 |

I1은 시각적 식별 설계와 fixture가 고정되기 전에는 실행 명령을 만들 수 없다. 미정인 배치나
식별 단서를 조정자가 실행 직전 GT를 보고 골라 정상 셀을 통과시키지 않는다. I2의 교환/가림은
dev 진단으로 명시하며 정식 s5의 이동30초/낙하62.5초를 바꾸지 않는다. 정식 s5는 cyan1개지만
이동 후 추적 연속성은 여전히 필요하다. 원본 사건4분기/복구는 별도 T13b 범위다.

## 셀마다 남길 증거와 종료

- 두 셀 모두 900초 cap 도달, API unsupported, unknown 만료, 미파지/오배송/오인식, host 오류를
  원래 할당 분모에 남긴다. ENOSPC는 HOST_ERROR. cap을 늘려 통과시키거나 실패 파일을 덮지 않는다.
- SIM초에는 초기화/staging/팔 전이/관측/재탐색/주행/대기/방출을 전부 포함한다. 각 구간 및 합계,
  발행 명령 수, 관측 수/주기, 모델 호출0 여부, 중단 이유를 기록한다. cap은 wall 시간 예측이 아니다.
- actor/action→order_id/requested_item_id→job_id→local token→frame hash/detection→자기 open→
  claim의 근거→**별도 eval_only** 실제 item_id/목적지/비파지·정지·접촉 판정을 연결한다.
  peer 실제 배송만 달라진 동안 자기 입력/명령/claim은 관측 전 같아야 한다. eval 결과를
  controller 성공 통보, 재탐색 종료 또는 item lookup으로 되돌려 보내지 않는다.
- 보고 분모: 할당2, 실행/미실행, cap 실패/미도달, 실제 교환·가림 효과 성립, 오인식/미파지,
  물리 정확배송, 자기 올바른 완료, 거짓 identity, 거짓 완료를 각각 남긴다. 두 셀에서 거짓 주장
  0을 관측해도 일반적인 오류율 0 또는 4조건 효과/확증이라고 해석하지 않는다.
- 원본 own RGB·모델 요청 텍스트(있다면)·자기 명령/상태·하위 job·원장·평가·환경/입력/모델
  manifest와 전체 SHA-256을 primary outputs에 보존한다. 실패 원본도 새 run에 연결한다.
- 실제 결과를 받으면 `docs/tensorboard.md`대로 native TensorBoard 새 snapshot, 원본 source/hash
  중복 검사, event readback, 새 영상 등록, source 값과 표시 값·pin/HParams를 검증한다.
  dashboard URL과 미회수/미변환/미표시 항목을 결과 기록에 남긴다. 그때까지 실험/TensorBoard
  완료는 아니다. 자기 session/자식만 정리하고 잠금을 반환한다.
