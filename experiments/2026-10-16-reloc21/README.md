# reloc21 — CPU_R1_DONE / NOT_READY

**place0/6·완주0/6, cap_end6·위치추정 소진2·HOST_ERROR0.** gcp2 CPU R1 8회를 완료·회수 검증했다. 새 후보는 오차가 악화돼 채택하지 않는다. [DRAFT PR #547](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/547), base reloc20 `2f4f469ef8e3c3bedeaebb0aff698332b426fbaf` / PR #543.

추가 조정자 인계([원문](coordinator-handoff.md), [SHA·범위](scope-change-receipt.json))에 따라 CPU R2/R3를 제출하지 않았다. 실행기는 추가 CPU 라운드를 거부한다. 위치추정·운반 MJWarp 후속은 warp5가 이 기록을 읽고 별도 검증한다. CPU와 MJWarp 결과를 합산하지 않는다.

[최종 요약 JSON](delivery/summary.json), [전체/운반 xy·yaw p95](delivery/metrics.md), [우선순위 원인표·수정·warp5 인계](root-cause.md), [8회 관문·거부 원장](round1/rejection-table.json.zst), [전체 세부 결과](round1/summary.json.zst).

|조건|place/완주|자기추정도착/목적지색획득|93266 xy/yaw p95|93315 xy/yaw p95|
|---|---|---|---|---|
|reloc20 R3 baseline|0/2·0/2|0/2·0/2|.387m/18.30°|.139m/16.79°|
|경로 유지 progress|0/2·0/2|1/2·0/2|.556m/89.90°|1.532m/107.04°|
|완전 계획 complete|0/2·0/2|1/2·0/2|.556m/89.90°|1.532m/107.04°|

8시도→제어8→운반6→들기6→운반6→자기추정도착2→색획득0→place0→완주0. 완주는 교사 명령 완료와 평가자 zone placement 성공을 함께 요구한다. 자기추정도착은 실제 도착·완주가 아니다. progress/complete는 각시드 발행 명령 궤적이 같아 독립 성능 표본으로 합산하지 않는다. 거리·기간·단계도 다르다.

[reloc20 16시도 표](prior-gate-table.md)에는 cap_end9의 마지막 단계·자기추정 잔여거리와 원래 HOST_ERROR7의 종류를 모두 분리했다. 실제 운반 제어 시작은9/10이고 place0/9였다. 공용 알림의 “제어 시작0/9”는 오기였다. HOST_ERROR7은 위치재추정 소진6과 이미 수정된 지도 선언1이다. 전체 계획 감사는 실행 관문이 아닌 오프라인 기하였다. [거부·통로 재생](prior-route-table.md)의20/20 경로 검사가 통과해도 최소 여유는.0000447–.0017527m로 작았고 실제 운반을 보장하지 않는다.

기본 off `reloc21_route_progress_v1`은 strict 하중 경로·목표를 유지하고 단조 cursor로 진행한다. `reloc21_complete_plan_v1`은5개 slot의 경로·place 전진·후퇴를 검사한다. 기존 `destination_visual_acquire_v1`는 이전부터 켜져 있었고 R1에도 켰다. 상한300/phase180 SIM초·성공 관문·물리·카메라를 유지했다([방법·수치 근거](references.md)).

R1의93266 후보는 시작 enclosure 겹침1765회·기하/무경로 hold53.4/180 SIM초(29.7%)와 같은 제외slot을 반복해서 세는 결함이 있었다. 후보별1 SIM초·3회 한도와 전후보 소진 실패 반환으로 수정했다. 오래된 잔여경로는 null/시각으로 구분한다. **수정 후41개 비물리 회귀만 통과했고 새 물리0**이다. R1 물리 결과를 수정 후 성능으로 승계하지 않는다.93266의 잘못 수용한 heading145/184와93315의 목적지색0/1253 판독도 남는다. 반례·원본 SHA는 root-cause.md와 round1/root-cause-evidence.json에 있다.

물리 SHA `6acde414adc6fee74d024e508a9853e4c1cafcf8`, gcp2/n4-highcpu-64/C MuJoCo3.12, Python3.12.3. 자체8동시, beamact3 예정16개 용량 예약·공용40 이하. 첫30 SIM초8/8, wall/SIM 중앙4.18593(PASS,3.5 경고). source는 git-shared.git 직접 reference clone이다.

**원본18,907파일 SHA 일치**, 입력 감사8/8 `invisible_measurements=0`, `held_world_reads=0`, **Mac fetch-lite145파일 SHA 일치**. 원본은 gcp2 영속디스크의 `/home/ugrp/ugrp-sim/runs/reloc21-r1-*`에 보존하며 외부 raw 백업 완료를 뜻하지 않는다. 기본 off 명령5514개·영상4616장·종료시각은 reloc20과 정확히 같다([대조](round1/off-replay.json)). 위치추정 소진 분류만 바뀌었으며 과거 원본은 고치지 않았다. R1 plan의 PR metadata543은 부모 상속값이고 실제 작업은 PR547이다.

[실패2개 전체2Hz·종료10Hz 직접검토](playback-review.md), 실패12장·대표4배속 영상·ffprobe/SHA를 보존했다. 성공0이므로 성공영상1개 대조는 미충족이다. Mac 물리·렌더·GUI·LLM·ACT 학습0이며 입력 감사가 정확도·실물 성공을 보장하지 않는다. 모델 가격 경보로 신규 LLM 배치0을 유지했다.

종료 시 다른 작업 lease `warp4.json`·`llmhost-stage.json`을 확인해 보존했고 VM은 정지하지 않는다. 자기 lease만 제거하고 확인 결과를 host-lifecycle.json에 남긴다. PR은 DRAFT/NOT_READY이며 CI·병합·MJWarp 인수·학생/실물 성공 완료가 아니다.

최종 Mac 여유는 약15GiB로20GiB 제출/회수 바닥 아래다(storage-final.json). 후속 대량회수·제출 차단 조건으로 남겼고 다른 작업/원본을 정리하지 않았다.
