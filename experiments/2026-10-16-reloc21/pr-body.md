reloc20은 운반 제어9회가 시작됐지만 place0/9였고, R3 네 실행은 운반 단계180 SIM초에서 목적지 획득 전에 끝났습니다. 공용 알림의 "제어 시작0/9"를 원본16시도 관문표로 정정하고, 재위치추정 소진6회를 호스트 오류와 구분합니다.

기본 off 경로 후보는 strict 하중 footprint 검사를 유지하며 유효 경로·목표를 보존하고, 무진행 동일 선택3회 제거와5개 slot의 경로·place 전진·후퇴 전체 검사를 추가합니다. 기존 목적지 RGB 획득을 계속 켜고 성공 기준·물리·카메라·SIM 상한은 R1에서 유지합니다.

- Base: `claude/reloc20` (`2f4f469ef`), 선행 DRAFT #543. 미채택 DEV 후보이며 병합 준비가 아닙니다.
- 비물리 검증: 관련3파일40 passed. Mac 물리·렌더·GUI0.
- gcp2 R1: 고정 source `6acde414adc6fee74d024e508a9853e4c1cafcf8`, baseline2/progress2/complete2/짧은2 실행 중. 최대3라운드·자체8동시·공용40, beamact3 예정16개 용량 예약.
- place·완주·오차 p95·감사·종료 분포·전체 raw 해시·실패 프레임은 완료 후 갱신합니다. 실행 중 결과를 성공/회수 완료로 세지 않습니다.
- 모델 가격 인상 경보를 확인했으며 신규 LLM 호출/배치0. gcp1 접근0, Google Drive 미사용.

기록: `experiments/2026-10-16-reloc21/README.md`, `prior-gate-table.md`, 압축 rejection_table과 영상 검토·공식 자료/상수 근거.
