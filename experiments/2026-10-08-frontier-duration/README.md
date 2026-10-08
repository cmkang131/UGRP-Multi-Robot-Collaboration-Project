# egomap46 — 별도 360초 탐색 예산 조건 (실행 전 사전등록)

2026-10-08 사용자 결정: 예산을 늘린 조건을 비교한다. **180초 결과와 합산하지 않는다.**
동일한 새 seed46001에서 **A 다음 B, 각각 MuJoCo DEV 1회**. 알고리즘·문턱 재튜닝0.
등록 이전 기준 소스5d5e36be, PR405 DRAFT. 모델 호출0·freeze0·GT는 평가만.

## 조건과 기준

|조건|탐색기|SIM 예산|seed|구분|
|---|---|---:|---:|---|
|egomap34|기존 frontier_rbpf_v1|180초|32002|기존 개발 결과, 합산 금지|
|egomap45|yamauchi_cycle_v1|180초|45001|기존 개발 결과, 합산 금지|
|A|egomap34 기존 탐색기 그대로|**360초**|**46001**|새 조건·1회|
|B|egomap45 frontier 목표 유지+360° 관측 주기 그대로|**360초**|**46001**|새 조건·1회|

A/B 차이는 `frontier_observation=off` / `yamauchi_cycle_v1`뿐이다.
벽 tape_v1, SEARCH, servo_stiffness=real_v1, s2_pulse_v122_rotL_v1,
RBPF100·pose_graph·switchable·wall_confidence·TSDF support,
selective resampling·insertion 수정·Manhattan·20° 검색, public_ros_v8·Nav2 recovery는 불변.
검출기 개선 중단 유지, egomap44 매 프레임 SLAM 삽입 off.
기존의 초기 대기2초도 cap에 포함하며 촬영1801개·제어1791프레임이 정상 완주 수다.

**사전 성공 기준(각 조건 개별 판정)**:
1. 전체 벽 덮음 **≥80%**(기존0.1m 벽 표본329개에 대한0.15m 이내 비율).
2. 실제 관측 영역 점유칸 정밀도 **≥0.636**(사용자 지정63.6% 그대로; 결과 후 반올림 조정 없음).
둘 다 만족해야 기준 통과. 정상360초 완주 여부는 별도로 표시하며 조기 실패를 성공으로 승계하지 않는다.
문 통과·hold·벽 RMSE·영역 R·B 도달·접촉·삽입 수/거부 사유도 숨기지 않는다.
서로 다른180초 seed 대비는 기술적 비교이며 시간 증가의 인과효과 확증이 아니다.
A/B 같은 seed도 표본1쌍으로 통계적 일반화하지 않는다.

## 시점별 평가·영상

- 120/180/240/360초는 reset 완료 시각을0으로 한 경과 SIM 시간이다.
- 그 시각 이하 `online-maps.jsonl`의 가장 최신 **당시 frontend snapshot**만 사용한다.
  최종 pose graph를 과거 지도에 소급 적용하거나 미래 관측을 섞지 않는다.
- 곡선은 online frontend 전체 벽 덮음, 점유칸 수, 사용 snapshot 시각·스캔 수를 함께 저장한다.
  최종 표는 기존 egomap34/45와 같은 completed graph 지도 평가를 사용하며, 마지막 online
  frontend와 다르면 두 값을 별도 표시한다. 과거180초 자료의240/360초 값은 **해당 없음**.
- 조기 물리/호스트 실패 이후 시점은 censored/결측; 마지막 지도를 미래 값으로 반복하지 않는다.
- 전체 P/덮음/RMSE, 영역 P/R 및 각각의 칸·표본 분모, 실제 시야 표본/329를 같이 보고한다.
  영역은 기존 GT카메라 FOV·4m·벽 가림의 잠재 시야(물체/자기 가림 미모델링) 정의 그대로.
- 문 통과는 egomap45 평가기를 재사용: 실제 중앙/아래 개구부에서 오른쪽→왼쪽 중심 횡단 및
  이후 x<2.175 확인. 제어기는 이 좌표를 받지 않는다.
- B 목표는 자기 RGB로 관측·기억한 후보만. 세계 좌표로 목표를 주지 않으며 미관측은 별도 기록.
- A/B 각각 `wrist-map-4x.mp4`: 자기 손목 RGB | 당시 자기 지도·추정/실제 경로(실제는 평가 표식).
  20fps, 정상 완주1801프레임이면90.05초. 영상/원본은 로컬 outputs, 해시·표·작은 그림은Git.

## 실행 관리

README 사전등록 커밋 → 바뀐 실행 어댑터/평가 시간선 시험과 off bytes 검사 → 소스 동결 커밋/push
→ agent_lock null에서 드라이버PID로 원자 acquire → A → release → supervisor/잠금 확인
→ B acquire·실행 → release. S2 잠금이 있으면 대기하며 다른 프로세스에는 손대지 않는다.
관리 진입점은 sim_cli workflow + ugrp_session. 기존 제어기/지도 파일은 수정하지 않는다.
A 결과에 따라 B 설정을 바꾸거나 취소하지 않으며, 정상 실험 실패는 그대로 남긴다.
실행마다 호스트 상한30분(기존 그대로), 총 물리 최대60분, raw 예산2GiB.
여유10GiB 미만이면 실행하지 않음, ENOSPC=HOST_ERROR. 실제 물리 실패·실행 오류는 종료·보존.
실패 후 재튜닝·추가 물리0. push 서버 장애는 로컬SHA로 진행 후 다시 시도.

실행 명세: 사용자 지시의 **A/B 구성 그대로**를 우선해 기존 Nav2/costmap/pulse 충돌예측 hold를
유지한다(egomap45의 실제 hold259프레임 포함). 이 부분을 로그 전용으로 완화하지 않는다.
모든 보수적 가드를 기록 전용으로 바꾸는 strict dev_light와는 다르며, 그 차이를 숨기지 않는다.
실험 전체는 품질/σ 미달로 조기 종료하지 않고360초까지 기록한다. 가드를 바꾸면 시간 외 변인이
추가되므로 이번 ‘시간만 변경’ 비교에는 넣지 않는 기본 가정이다. 관련 확인 질문은 사용자에게 전달했다.
사전등록 후 알고리즘 source/hash 및 두 조건의 적용값을 freeze.json에 고정한다.

원문/코드는 [egomap45 출처](../2026-10-08-frontier-visibility/REFERENCES.md)와
[egomap34 고정 구성](../2026-10-08-wall-segment-dev/README.md)을 그대로 재사용한다.
새 방법 조사·튜닝·라이브러리 설치 없음. TensorBoard 생략 유지, PR405 DRAFT/병합 금지.
raw: `/Users/changmin/projects/ugrp/outputs/frontier-duration-v1/{A,B}/new-seed`.
