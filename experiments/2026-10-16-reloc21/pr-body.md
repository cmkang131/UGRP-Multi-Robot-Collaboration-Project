reloc20의 실제 운반 제어 시작9/10·place0/9를 원본16시도 표로 확인해 공용 알림의 “제어 시작0/9”를 정정했습니다. 위치재추정 소진을 HOST_ERROR와 구분했고 기존 동작은 유지됩니다.

기본 off 경로 유지·완전 place 계획 후보를 gcp2 CPU R1에서 검증했지만 **place0/6·완주0/6**, cap_end6·위치추정 소진2·HOST_ERROR0으로 채택하지 않습니다. 기준선→후보 xy/yaw p95는93266 .387m/18.30°→.556m/89.90°,93315 .139m/16.79°→1.532m/107.04°로 악화됐습니다. 후보의 자기추정도착2/4·목적지색획득0이며 progress/complete는 시드별 같은 명령 궤적입니다. SIM 상한300/phase180·물리·카메라·성공 기준은 유지했습니다.

- 93266의 시작 enclosure 겹침1765회·29.7% hold와 반복 제거 결함을 확인했습니다. 후보별1 SIM초·3회 한도 및 전후보 소진 실패 반환으로 수정했습니다. 수정 후41개 비물리 회귀 통과, 새 물리 검증0입니다.
- 물리 source `6acde414adc6fee74d024e508a9853e4c1cafcf8`. 원본18,907파일 SHA·입력 감사8/8의0/0·fetch-lite145파일 SHA 일치. 기본 off 명령5514개·영상4616장·종료시각이 reloc20과 같습니다.
- 실패2개 전체2Hz·종료10Hz 직접검토, 실패12장·대표4배속 영상 보존. 성공영상 대조는 미충족, Mac 물리·렌더·GUI·모델 호출0.
- 추가 조정자 사용자결정 인계에 따라 CPU R2/R3를 제출하지 않고 warp5 MJWarp 후속에 인계합니다. CPU/MJWarp 합산 금지. 다른 warp4·llmhost-stage lease를 보존해 VM을 정지하지 않습니다.

Base `claude/reloc20` / DRAFT #543. 기록 `experiments/2026-10-16-reloc21/README.md`, `root-cause.md`, `round1/` 원장. DRAFT/NOT_READY이며 CI·병합·MJWarp 인수·학생/실물 성공 완료가 아닙니다.
