# reloc21 — RUNNING / NOT_READY

reloc20 HEAD `2f4f469ef8e3c3bedeaebb0aff698332b426fbaf` 위 `claude/reloc21`.
gcp2 CPU 전용, Mac 물리·렌더·GUI·LLM0. 최대3라운드, 자체8동시·공용40 이하.

수정 전 [16시도 종료 관문표](prior-gate-table.md)와 [압축 원장](prior-rejection-table.json.zst)을 gcp2 원본에서 생성했다.
운반 제어 시작9/10·운반 단계9/9·목적지 획득 진입2/9·place0/9다.
"제어 시작0/9"는 원본 수치와 맞지 않는다. 0/9는 place이며 전체 계획 감사는 오프라인 기하 재검사였다.
원상태 HOST_ERROR7은 재위치추정 소진6과 이미 수정된 지도 선언 누락1로 구분했다.

- 동작 불변 수정: 재위치추정 소진을 `CONTROLLER_FAILURE`로 분류한다. 원래6회 원본은 고치지 않는다.
- 기본 off `reloc21_route_progress_v1`: 유효한 strict 하중 경로·목표점을 유지하고 단조 cursor로 진행한다. 변화 없는 실패 선택3회면 그 slot 후보만 제거한다.
- 기본 off `reloc21_complete_plan_v1`: 같은5개 slot의 전 경로·전진·후퇴를 검사하고 기존 명령 한도 기반 비용으로 선택한다.
- 목적지 `destination_visual_acquire_v1`는 이전부터 켜져 있었으며 계속 켠다. 기존 RGB footprint 성공 기준·관측 자격을 완화하지 않는다.

[공식 방법·상수 근거](references.md), [수정 전 전체2Hz/종료10Hz 영상 검토](playback-review.md).
관련 비물리 시험40 passed(1.76s). 물리 제어 SHA `6acde414adc6fee74d024e508a9853e4c1cafcf8`의 R1 8회가 실행 중이며 아직 완료·회수 결과로 보고하지 않는다.
조건은 reloc20 R3 baseline2·progress2·complete2·짧은93584/93583 2회, SIM cap300·운반 phase180 유지.
raw는 `/home/ugrp/ugrp-sim/runs/reloc21-r1-*`에 보존한다.

gcp2 lease `leases/reloc21.json`, batch `reloc21-round1/queue.json`의 절대 rejection_table로 선행 표를 연결한다.
beamact3 예정16개 용량을 선예약하며 VM은 다른 lease/실행이 있으면 정지하지 않는다.
완주/배치·입력 감사·원본 해시·실패 프레임6장 이상의 최종 검증은 진행 중이다.
