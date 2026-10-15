# crate15 — 공동 상자 교사, 기본 OFF

기준 `8007db00`(crate14), PR #500. `--crate-profile crate15_v1`만 새 `crate_motion_v15`를 켠다. 이전 결과와 합산하지 않는다. **물리 성공·속도 미검증, 관문/학습 미승인.**

| 실패 원본 | 직접 원인 (SIM초) |
|---|---|
| 77990 | 14.4s r2 접근 인계. r1 후보 966개가 상대 원판에 차단(−336.0~−198.9mm); r2는 첫 격자 연결·끝 자세 강제로 경로 140개 실패. 역할과 달리 r2도 청록 쪽에서 시작했다. |
| 79314 | 14.0s r2 접근 인계. r1 청록 미확인 0/141; 원 배치의 맞교환. r2 상대 원판 거부 133개(−53.2~−6.2mm), 경로 실패 56개. |
| 79317 / 79450 / 79451 | 11.5 / 17.2 / 13.6s 정렬 종료. 40ms 최소 펄스(명령상 7.15mm 또는 3.26°)가 좁은 정렬 창을 넘어 반복 반전. |

수정: 상자 3개 직사각 부품·상대 몸체·벽의 자세별 충돌 검사, 발행 명령으로 추정한 현재 위치를 첫 노드로 연결, 보이는 대상 쪽을 유지하는 경로 자세, 재검사한 유효 경로 유지, 오차 절반 이하의 1ms 단위 정렬 펄스. 배정 손잡이가 가리면 **현재 보이는 상자 중심**을 기준으로 측면 관측 위치를 고른다(3회 무진행 후보 제외). 숨은 손잡이·평가 GT를 제어에 넣지 않는다. ACT 학생용 대체 경로가 아니다.

검증: 원장 **1,424/1,424** 로봇 틱 일치, 관련 시험 **84 통과**(pytest 단일 프로세스). 기존 Cartesian 시험 1개는 기준 소스에서도 실패하던 fixture에 실제 접근 계획 단계를 추가했다. 새 충돌 판정에서 79314 거부 **133/133 해제**, 경로 실패 **196/196 경로 발견**; 77990 r1 **966개는 실제 자리 점유로 계속 거부**(몸체 여유 −176.5~−63.2mm). 정렬 289개 저장 상태에서 새 명령 투영은 잔여 오차의 0.485배 이하. 이는 동일 저장 입력에서의 판정/명령 비교이며 바뀐 동작 뒤의 물리 결과를 예측한 재생이 아니다.

crate14 점검: 새 시작 필터는 신규 2건에 적용됐고 재현 3건에는 원 배치를 유지했다. 197.4mm 창·축 재활성화는 적용됐지만 40ms 실행 해상도로 비수렴했다. 상대 차단 시 시계 정지는 77990 **13.7s**, 79314 **0.9s** 작동했다.

대기열: 재현 **77990·79314·79317·79450·79451** + 새 **79600–79607·79610–79611**. 새 조건부 시작 41제안 중 29거부, 완성 12개 중 벽 근처 2개 제외. 정적 setup LOS만 검사했고 mj_step/mj_forward/render는 차단했다. 79500번대는 기존 solo 큐와 충돌해 채택하지 않았다. 79600–79639 로컬 5,430 JSON 충돌 0; live 재고는 운영자가 확인해야 한다. [queue.py](queue.py)가 clean·push SHA에서 새 JSON을 만들고 기존 큐 해시를 보존한다. 승인·실행·관문·학습 플래그 전부 false.

원본/상세 기록: `/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/crate15-8007db00/`의 `report.md`, `comparison.json`, `local-verification.json`, `pytest.xml`. 영상 111프레임(각 실행 처음·중간·끝 ≥6장) 직접 확인. 회수된 manifest 항목 156개와 압축 복원 해시를 재검증했고, 미회수 111항목은 목록만 기록했다. 원격 접속·실행·학습·모델 호출 없음. 5mm 기하 패딩은 실측 위치 오차 보장이 아니며 팔·집게의 전체 주행 sweep 및 새 정책의 물리 수렴은 미검증이다.

표준 근거: [Nav2 footprint 공개 코드](https://raw.githubusercontent.com/ros-navigation/navigation2/main/nav2_costmap_2d/src/footprint_collision_checker.cpp)와 [실제 footprint 권고](https://github.com/ros-navigation/mkdocs.nav2.org/blob/rolling/docs/configuration_and_development/tuning_guide.md#robot-footprint-vs-radius)는 본문 확인. [Chaumette & Hutchinson 2006 식(1)–(5)](https://web.mit.edu/amcp/OldFiles/drg/Chaumette_Part_I.pdf)는 오차 비례 시각 서보의 근거이며 본 펄스 폭의 물리 성능을 보증하지 않는다. [McGreavy 등 2016](https://research.birmingham.ac.uk/en/publications/next-best-view-planning-for-object-recognition-in-mobile-robotics/)은 도달 가능한 관측 위치 선택의 초록만 확인했으며, 여기서는 정보이득 최적화를 구현하지 않았다.
