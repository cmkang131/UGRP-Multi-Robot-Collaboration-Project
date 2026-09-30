# P02 코디네이터 인계 — 혼합 임무 실제 검증은 미실행

이 문서는 실행 명세이며 결과가 아니다. READINESS S04/S13의 기준 main은
`a8094cc14e098a55483f53a3c49bf6a0b116043d`, P02 작업 시작 main/branch는
`d17ca4345affef8cf027e121cf1f3197b36c23e0`이다.

## 정적 후보와 제한

- 개발 시나리오: `configs/zone_study_integration/mixed_cyan_beam_fixed_r12_r3_dev.json`.
- 준비 명세: `configs/zone_study_integration/mixed_jobs_dev_spec.json`,
  `ugrp.zone_mixed_jobs_dev_spec.v1`, `DRAFT_CONTRACT_ONLY`, source/bundle/실행 ID는 null.
  러너의 prereg 파일이 아니며 실행·등록·봉인 승인이 아니다.
- `from scripts import zone_mixed_study_adapter as runner` 뒤
  `runner.host_spec(scenario, dev_spec['episode'], bundle_for(scenario))`에서
  `mixed_cyan_beam_fixed_r12_r3_v1` opt-in 계약을 만든다. 공개 OrderSheetSource에는
  초기 slot·종류·수량·정적 개체 ID만 남고 setup pose와 bindings는 host/eval 쪽에 둔다.
- `beam-order → beam_dev`: r1/end_neg·r2/end_pos가 각각 자기 API로 claim해야 한다.
  `cyan-order → cyan_dev`: r3의 자기 deliver API만 허용한다. 상대 claim 자동 생성,
  GT 기반 r3 양보, pair 실패에 따른 r3 취소는 없다.
- 계약 테스트의 지도/모델 경로는 기존 `zone_wide_door_geometry_v2`와 기존 M2 문
  경로, `v5h` API seam이다. 이는 최종 MasterPi v3/무표식 제공자나 #292 v6h1
  성능 검증이 아니다. 다른 지도/route/pair policy는 fail-closed다.
- r3 pair, 비cyan 단독, heavy_crate, 수량 확장과 새 경로는 미지원이다.
  정식 s1–s6는 그대로 보존했으며 전체 6시나리오 지원·파트너 자유 선택이 아니다.
- 별도 `MixedGeometryCargoZoneScene` 표준 Scene subclass가 setup의 cyan과 봉을
  함께 유지한다. #249의 기존 geometry Scene 파일은 바꾸지 않았다.

## B1 이후 진입점 (2026-09-30)

독립 검토 B1에 따라 기존 `zone_own_team_host.py`, `zone_study_integration.py`,
`run_zone_study_integration.py`는 v6e 등록 해시의 원본 바이트로 복원했다. 등록 JSON이나
해시 검사 자체는 변경하지 않았다. 기존 integration CLI는 계속 혼합 주문을 거절한다.

새 `scripts.zone_mixed_study_adapter`의 `host_spec`, `placements_match`, `StudyTeamHost`,
`IntegratedTrial`, `HostRobotLink`를 함께 사용하는 명시적 Python 합성 경로다.
`StudyTeamHost`는 기존 provider 수명/시계를 상속하고, `MixedOwnCamTeamHost`에서
정적 inventory를 검사한 뒤 기존 solo 초기화와 order ID 기반 pair 연결을 순서대로 수행한다.
`MixedIntegratedTrial`은 기존 scheduler와 원장 처리를 상속하고 혼합 주문의 계획 거절만
자기 dispatch 메서드에서 적용한다. 공용 모듈의 전역 함수·클래스는 교체하지 않는다.

이 어댑터는 새 standalone CLI나 등록된 runnable이 아니다. 기존 `run_bundle/run_trial`을
그대로 호출하여 혼합 실행으로 인정하면 안 된다. 코디네이터는 새 어댑터, 두 mixed host/
integration 모듈, inventory/helper를 포함하는 의존성 closure와 구성/Scene을 새 workflow에
고정해야 한다. 어댑터 constructor는 World 소유 부분만 fake로 치환하여 검사하며 물리 실행은 없다.
정상 GitHub CI는 허용하며 취소하거나 CI 생략 표시를 사용하지 않는다.

## 선행 조건과 합성 경계

P01의 최종 환경과 P03의 provider/model/calibration, P04의 chain, P05의 다회 대화,
P06의 실패 기록·referee·TensorBoard를 독립 검토한 뒤 합성해야 한다. P02에서 검증한
v2/v5h 제한을 제거해 무조건 수락하지 않는다. 최종 v3 및 새 정책/지도 조합을 쓰려면
그 조합의 M1/M2 이관·새 정적 거절 검사·물리 접근/운반/도착 증거를 먼저 확보하고
새 opt-in profile/명세로 기록한다. 기존 fake 통과를 물리 통과로 승계하지 않는다.

이번 PR은 runnable/workflow 번호를 예약하지 않는다. main+모든 열린 PR에서 중복을
확인한 뒤 코디네이터가 새 source SHA·번들 ID·해시와 표준 sim_cli workflow를 고정한다.
봉인 자료·raw·기존 번들은 덮어쓰지 않는다. Drive 작업은 없다.

## C5a — 초기화부터 두 물건 목적지까지

동일 새 source·seed 700·scene spec/해시·로봇/카메라·provider/보정·명령 주기·접촉
프로필로 `no_comm`, `peer_ko`, `leader_ko`, `structured` 각각 새 host에서 1회 수행한다.
조건마다 **1800 SIM초 cap**, 총 **4회/7200 SIM초 상한**이다. wall 환산은 하지 않는다.
현재 700은 leader r2이며 자유 파트너/leader 균형 코호트가 아니다.

1. 표준 Scene reset에서 시작해 cyan1+long_beam1 및 로봇3대의 초기 충돌/카메라를
   확인한다. 중간 teacher staging·재배치·GT 보정 없이 접근→정렬→grasp/lift→문 통과
   →운반→lower/open→재측위/재파지(필요 단계)→최종 방출을 한 실행에서 이어 간다.
2. r1/r2 pair와 r3 단독은 개별 결정을 통해 시작한다. 한쪽 pair claim 뒤 상대 API 호출이
   없으면 자동 job이 생기면 안 된다. 고정 결정은 로봇 자기 공개 요청과 명령 이력만 읽는다.
3. 목적지 기준은 cyan A·봉 B의 전체 footprint, 바닥·정지·비파지와 referee settle 조건이다.
   API `job_done`/`unconfirmed`는 도착 성공이 아니다. 두 주문의 물리 개체 ID가 manifest와
   일치해야 하며 다른 cyan/봉으로 성공을 대체하지 않는다.
4. 각 호출은 call_id→fake/실제 원장→dispatch actor/order_id→ack job_id→자기 terminal
   event→평가 item_id/destination으로 join한다. fake send 수는 실제 모델 호출 수가 아니다.
   `harness.zone_mixed_jobs.evidence_join`은 별도 offline join 검사를 제공하며 모델 입력,
   제어 보정이나 성공 통보로 쓰지 않는다.
5. no_comm 메시지0, leader follower 간 직접 전송0, structured 자유문0, 모든 조건 동일
   pair enum 채널/입력/물리 설정을 확인한다. 공개 요청 원본·자기 RGB·자기 명령을 보존하고
   GT/TOP/교사 자료는 eval_only로 격리한다. 실제 호출/송신 비용과 fake 원장을 구분한다.
6. pair 실패 중 r3의 자기 job이 유지되는지 확인한다. 전체 host 중단은 실제 안전/인프라/
   episode cap과 분리해서 기록한다. 한 job 완료로 다른 job 완료를 추정하지 않는다.

## 중단·기록·후속 실행

- 1800초 안에 둘 다 도착하지 않으면 그 조건을 실패/미완료로 남긴다. 예산을 몰래 늘리지
  않고 실패·미도달·API 거절·HOST_ERROR를 모두 4회 분모에 포함한다. ENOSPC는 HOST_ERROR다.
- 물리 실행 전 agent_lock/session 소유·10 GiB 여유·raw 저장 절대 경로를 확인한다.
  다른 작업/서버를 종료하지 않는다. raw는 기본 checkout outputs에 남기고 해시·환경·실효
  설정·명령·요청/응답·평가/dispatch/원장의 같은 분모를 experiments 기록으로 연결한다.
- 완료 뒤 P06의 증거 검사와 native TensorBoard 새 snapshot/readback/영상 등록/화면 값을
  검증한다. 이번 정적 pytest 결과는 물리/학습/평가 cohort가 아니므로 공용 snapshot을
  생성하거나 대시보드를 다시 열지 않았다.
- C5b 실제 다회 LLM 4조건은 C5a와 같은 고정 구성의 별도 실행·비용 승인/상한 후 수행한다.
  이번 P02에서는 물리·렌더·비전 추론·LLM·교사 호출을 한 번도 실행하지 않는다.
