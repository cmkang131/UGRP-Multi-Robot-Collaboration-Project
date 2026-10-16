# reloc20 — 실행 준비

reloc19 HEAD b73e815f6 위 claude/reloc20. locdiag.md/JSON을 먼저 읽고 기본 off 후보를 만든다. 물리 변경·LLM·ACT 학습 없음. gcp2 CPU만, 자체6동시/공유40이하, 최대3라운드. R1은 긴 운반93266/93315 baseline/candidate 짝과 짧은 자기지도93584/93583을 실행한다. 성공·cap_end·HOST_ERROR와 입력 감사를 모두 기록한다. R2/R3는 직전 실패/거부표를 보고 원인이 고쳐졌을 때만 실행한다.

|토글|기본|후보|
|---|---|---|
|reloc20_heading_forward_v1|off|on: 운반·목적지 횡 펄스 제거|
|reloc20_loaded_footprint_v1|off|on: 명령 FK 화물 enclosure+정적 초기 빔, strict 경로|
|reloc20_obstacle_wall_mask_v1|off|R2: 기존 v5 RGB 벽 마스크를 장애물 검출에도 적용|
|reloc20_contact_ode_v1|off|on: PR510 후속 ODE 별도 모듈|
|reloc20_visual_stall_v1|off|on: 자기 RGB LK+영상 변화량 불일치, 적분 억제·Q 증가·후퇴|
|reloc20_obstacle_wall_component_v1|off|R3: 벽 마스크가 만든 조각을 물체로 세지 않음|
|reloc20_rotation_stall_v1|off|R3: 자기 RGB 정지와 순수회전 명령 불일치도 검사|
|reloc20_turn_density_v1|off|R3 density 조건만: 기존 제어주기 pulse-density 회전|
|destination_direction_preserve_v1/search_replan_v1|off|on: reloc19 비물리 후속 포함|

최신 로컬 비물리 검사32 passed(1.23s). 새 footprint·heading·stall·density/벽 조각/회전 정지14개와 기존 destination18개. 물리·렌더를 호출하지 않았다. 실행 소스는 커밋·push한 SHA로 고정한다.

[표준 방법·상수 출처·한계](references.md), [수정 전 거부·funnel](prior-rejection-table.json), [정지 영상 원본 분포](flow-fit.json). 하중 metric VO 자격0/531은 완화하지 않는다. 초기 빔 keepout은 움직인 빔의 현재 위치를 알려주지 않으며, 위치 오차가 clearance보다 크면 실제 충돌 방지는 별도 검증이 필요하다.
