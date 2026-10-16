# reloc19 — 목적지 시각 획득: NOT_READY

최대 3라운드·18회(gcp2 CPU, 운반12·짧은 위치 추정6)를 완료했다. **최종 R3 place A_pan 0/2, AB_pan 0/2; 실제 목적지 획득 0/4.** 전체 운반 진단도 place 0/12다. 완주 성공과 성공 영상이 없으며 기본 전환·학습 데이터 생성에 사용할 수 없다. [Draft PR #541](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/541).

시작은 reloc18 기록 HEAD `d271566155d6946240b53c15ddb5eb1f8c42de99`, 별도 worktree `claude/reloc19`다. 전역 위치 추정으로 도착한 뒤에도 자기 RGB로 목적지를 확인하도록 접근을 전환했다. 판단 LLM·ACT 학습/학생·실물은 실행하지 않았다.

## 구현과 실행 범위

- 기본 off `destination_visual_acquire_v1`(A): 정적 지도·자기 추정 위치/공분산으로 유한 시점·타원 격자 후보 생성 → 자기 RGB 목적지 바닥 색 확인 → 명목 바닥 역투영 패치의 서보 → 기존 RGB footprint 관문 → 기존 place. 시간은 SIM초, 경로 검색은 기존40,000 검사 예산이다. 모든 이동은 기존 정적/RGB 충돌 관문을 유지한다.
- 기본 off `carry_relocalize_v1`(AB): 95% 명령 예측 타원이 구역 반폭보다 커지면 재관측한다. R1의 무정보 전회전 뒤 R2는 기존 정적 지형지물 정보량 기반 시점 선택, R3는 닫힌 집게에서 기존 metric XY 관문이 자격을 주지 않는 경우 기존 내려놓기·둘러보기 복구를 요청한다. 들고 있는 상태의 compass는 heading용이며 XY fix로 부르지 않는다.
- R3의 기본 off `destination_camera_pan_v1`: 기존 서보 범위에서 카메라 팬 후 원래 자세 복귀. 배치·FOV·물리·장면을 바꾸지 않았다. RGB 기억은 자기 발행 명령으로만 전파하며 기존5.2초 후 만료한다.
- 실행 뒤 발견한 기본 off `destination_direction_preserve_v1`, `destination_search_replan_v1`는 **비물리 후보**다. 해당 코드가 포함되지 않은 R3 물리 결과와 분리한다. 추가 물리 실행0회다.

[문헌 조사·상수 출처·미구현 범위](references.md), [비물리 검증](tests.md), [직접 영상 검토](playback-review.md), [모든 실행 수치](metrics-table.md), [18회 요약 JSON](summary.json).

## 라운드별 결과와 실패 원인

|라운드|동결 실행 소스|place A / AB|실제 획득|첫30 SIM초 wall/SIM 중앙값|
|---|---|---|---|---:|
|R1|`3da9f8d97240a211edfc0baf9522ef4dcc72c59a`|0/2 / 0/2|0/4 (검출1은 벽 오인)|4.161|
|R2|`595b3eec3fa27b1dde2369a1e6aa7f73b977c434`|0/2 / 0/2|0/4|4.168|
|R3|`e042139b0930ee7b31eae08a917ff501ee01075f`|0/2 / 0/2|0/4|4.172|

경고3.5를 넘었지만 배치 중앙값 차단6.0 미만이며 HOST 실행 자체는 회수됐다. 자체 동시6≤8, 각 queue의 lease snapshot 기준 공유 합계≤40이었다. gcp2 `n4-highcpu-64`·C MuJoCo CPU만 사용했고 gcp1을 조회·시작·복사하지 않았다.

변경 전 [거부 표](prior-rejection-table.json)는 reloc18 R3의 실제 place 관문93프레임 중 목적지색0/93, 최종거부2/2 `destination_floor_not_visible`였다. 각 라운드의 queue에는 직전 표의 절대경로 `rejection_table`을 연결하고 실재를 검사했다. 최종 표는 `roundN/rejection-table.json`, 제출 당시 표는 `.initial.json`으로 보존했다.

R1 A·93315의 검출기는 보라 벽을 C 바닥으로 오인했다. 기존 `reloc16_floor_mask.floor_clear`를 새 획득기에 연결하지 않은 누락으로, 실제 획득으로 세지 않는다. 원본 마지막10초101프레임을 gcp2에서 재생하면 이전 footprint 수용10/101 → 기존 벽 제외를 적용한 수용0/101이다(`round1/wall-replay.json`). R2는 획득과 place 양쪽에 이 기존 RGB 마스크를 연결했다. 색·성공 수치를 완화하지 않았다.

R1 B의 완료한48.3 SIM초 전회전3회는 모두 new_fixes=0이었다. R2/R3 B는 기존 내려놓기·둘러보기·재파지를 반복했고 최종 목적지 획득에는 진입하지 못했다. R3 재위치 요청은 93266 3회·93315 2회이며 성공한 XY 보정 횟수가 아니다.

R3 A·93315의 획득 프레임1772개 중1597개는 `wall_divider_1` 한 틱 경로 거부(최소 틈 −.001753m),175개는 목적지색 없음이었다. 안전한 waypoint를 전후/좌우 독립 clip하면서 방향이 바뀌었다. 실제 후보 함수로 저장 추정 상태를 재생한 방향 보존 수정은 R2 210/210, R3 1597/1597에서 **같은** 충돌 관문을 통과했다. R3 1597개는 같은 정지 자세1개의 반복이므로 독립 성공 표본이 아니다. 물리·place 성공은 미검증이다.

R3 A·93266은 획득 프레임1535개 모두 목적지색 없음이며, 이후 새 RGB 장애물이 기존 검색 목표를 가렸다. 저장 상태에서 목표까지.367m이고 waypoint가 없어도 같은 목표를 계속 유지했다. 후속 재계획 토글은 그 목표를 사유·물체·최소 틈과 함께 폐기하고 남은 유한 후보를 다시 검사한다. 기존 장애물을 지우거나 충돌 허용치를 넓히지 않는다. [실제 반례](search-goal-counterexample.json).

## 긴 운반과 종료 분류

최종 A·93266 전체 궤적 xy 중앙/p95는 **1.828/2.294m**(3000틱,300 SIM초), 실제 carry_to_zone 틱만은 **.692/2.309m**(881틱)다. AB는 전체 .304/.833m지만 운반 최대 변위가.875m이고 복구를 반복했다. 따라서 작은 AB 오차를 긴 운반 완료·p95 개선으로 보고하지 않는다. 경로·관측·시간이 달라 reloc18/다른 조건과 통계를 합치지 않는다. [실행별 전체/운반 오차·yaw 수용 표](metrics-table.md).

운반12회 중 전체 cap_end6·phase_timeout4를 합쳐 **cap_end10회**로 분류하고 whole_run_SIM/phase_SIM을 구분했다. 나머지는 destination_floor_not_visible1·carry_recovery_setdown_envelope_blocked1이다. 짧은93584/93583은 매 라운드 원래 상태 HOST_ERROR, 이유 `selfmap4_relocalization_exhausted`로 총6회다. VM 장애로 바꿔 해석하지 않았으며 place 분모에 넣지 않는다. 짧은 R3 주행 xy p95는.092/.111m지만 재위치 소진으로 완주 실패다.

## 입력 감사와 증거 보존

모든18회의 `invisible_measurements=0`, `held_world_reads=0`을 원본에서 확인했다. selfmap의 `truth_pose_inputs=0`, TOP/peer 제어 프레임0이다. 새 탐색·서보·재위치 코드는 자기 RGB·자기 명령·정적 지도·추정치만 사용한다. 기존 교사의 가시 pregrasp 상대 위치 측정과 평가 전용 정답은 남아 있으므로 “모든 시뮬레이터 정답 읽기0”이라고 주장하지 않는다. cargo 세계 좌표는 들고 있을 때 행동 입력에 들어가지 않는다.

gcp2에서 manifest가 열거한 **43,171개 원본 파일 해시를 재검증, 누락/불일치0**이다(R1 13,105·R2 14,899·R3 15,167). `roundN/final-integrity.json`에 실행별 결과·원본 경로, `retrieval-manifest.json`에 파생 자료 해시, `retrieval-verified.json`에 Mac 회수 대조를 남겼다. `summary.json.zst`는 원본 JSON 전체를 압축 왕복 검증했다. 전체 원본·상세 frame ledger는 gcp2 영구 디스크에 남았고 전체 외부 백업 완료를 의미하지 않는다. Google Drive는 사용하지 않았다.

18회 모두 종료 직전 실제10 Hz 자기 카메라 버퍼를 기록했고, 실행마다6장과 몽타주를 `roundN/media/`로 회수했다. R1/R2/R3 각2개 실패의 개요+r1+r2+r3 4배속영상과 전체2 Hz·직전10초10 Hz 띠를 직접 읽었다. [검토 범위·시간순 타임라인](playback-review.md), [파일 대조](playback-verification.json), [대표 실패 영상](videos/representative-r3-A-pan93315-failure.mp4). 성공0이므로 요청된 성공1개 영상 비교는 미충족이다. Mac GUI·물리·렌더·ffmpeg는 실행하지 않았고 파일로 프레임을 읽었다.

## 재현과 남은 문제

동결 queue의 source SHA·각 run 명령·seed를 그대로 사용한다. `run_round.py`는 최대3라운드·6동시·직전 DONE/속도/거부표를 검사하는 실행기다. **완료한 이 작업에서 다시 제출하지 않는다.** 소스 사본은 공유 bare repo만 직접 참조했으며 shared repo와 원본은 삭제하지 않았다.

분석은 gcp2에서 다음과 같이 재현한다(물리 실행 없음). R1/R2도 --round만 바꾼다.

```sh
PYTHONPATH=/home/ugrp/ugrp-sim/src/e042139b0930ee7b31eae08a917ff501ee01075f \
/home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python \
/home/ugrp/ugrp-sim/analysis-tools/reloc19-finalize-evidence.py --round 3 \
--source /home/ugrp/ugrp-sim/src/e042139b0930ee7b31eae08a917ff501ee01075f \
--analyzer /home/ugrp/ugrp-sim/analysis-tools/reloc19-analyze.py --media
```

새 제어 비물리 검사35개가 통과했다. CI는 로컬 검사와 별개이며 최신 PR 상태를 확인해야 한다. 후속 두 기본 off 후보는 물리0회다. 목적지의 완전한 구역 중심 복원·B구역 원뿔 전용 검출·미래 경로 전체 정보이득 최적화는 구현하지 않았다. 현재 서보 특징은 보이는 바닥 패치 중심이며 큰 초기 위치 오류에서의 획득은 계속 실패했다. 다음 실행을 승인하기 전 이 한계와 기본 off 후보를 따로 검증해야 한다.

다른 lease와 UGRP python·mujoco·ffmpeg가0임을 확인해 자기 lease를 제거하고 gcp2 **TERMINATED**를 재확인했다. 디스크·원본은 보존했다. [cleanup.json](cleanup.json). PR은 DRAFT/NOT_READY로 유지하며 병합하지 않았다. primary checkout은 변경하지 않았다(공유 ops-alert 추가 제외).
