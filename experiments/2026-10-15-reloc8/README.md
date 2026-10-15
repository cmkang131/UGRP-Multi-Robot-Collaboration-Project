# reloc8: 자기 카메라 재위치 추정 (기본 off 후보)

기준: carry7 `8c6f219cb39595a877fc0af487b3ea7e9fefb27f` / selfmap6 `c8d9b6e51a601dba5e0724e83fd1eae8929fc9d2`.
소스는 이 기록을 포함한 커밋이며, 외부 새 큐에 전체 SHA를 고정한다. 기존 큐/실행/장면과 합산하지 않는다.

- 두 브랜치의 `harness/active_relocalization.py`는 동일 바이트다. `active_relocalization=reloc8_active_vision_v1`, 기본 `off`.
- 정적 지도·자기 추정 위치/공분산·자기 명령·자기 RGB만 사용한다. 벽/문/구역의 실제 FK 투영, 7개 불확실성 표본, 후보별 예측 관측의 구별 정도로 다음 시점을 고른다. 예측은 검출/등록이 아니다.
- 기존 look-ahead 팔 자세(어깨 858, 명목 pitch −7.46°)를 발행하고 팬/제자리 회전을 한다. 카메라 장착/FOV를 바꾸지 않는다. 종전 carry look −30.05°, selfmap SEARCH −18.08°.
- carry: 전체 유한 격자를 명령 사전 분포로 좁히고, 최대 3개의 서로 다른 이전 방향 RGB 우도와 현재 관측를 명령 상대 이동으로 연결한다. 단일 관측+사전 분포만으로 보정하지 않는다. 기존 잔차/정보량/rank/innovation 관문을 모두 유지한다.
- selfmap: 미등록 후보도 시점 선택에는 쓰지만, 기존 독립 3시점 등록·selfmap6 보정/rollback·복구 횟수/시한은 유지한다. 절대 위치 앵커가 없으면 명령만으로 전역 후보를 하나로 만들지 않는다.
- 저장 carry 93261 **28건**: 모호 24→12, 그중 기존 모호 13건 해소·기존 단일 1건 보류. 수락 0→0, 위험 수락 0. 벽점 50/65.5/93개(min/median/max), 바닥선 0인 관측 18/28, 문 0/28. 평가 전용 GT 변환 시 벽점 4/1940만 정적 벽 5cm 이내다.
- **reloc9 정정:** selfmap 제안 123건의 수락 113→113·거부 10→10은 바뀌지 않은 **selfmap6 관문 회귀 재생**이다. reloc8 개선 근거에서 제외한다. 당시 10°/15 cm 위험 수락 0이었으나 5°/10 cm로 다시 계산하면 수락 113건 중 절대 기준 초과 11건, 보정 전 대비 정규화 오차 악화 53건이다. 상세는 ../2026-10-15-reloc9/README.md와 summary.json을 따른다.
- 선택 영상 전부 검토: carry 320×240 14/8/8장, selfmap 640×480 6/11장. 실행별 처음·중간·끝 **각6장 미충족**. 전체 RGB/새 시점 RGB가 없으므로 전체 인과 재생·실제 복구 개선은 미검증이다.
- 관련 오프라인 시험: carry 14, selfmap 37 통과(직렬 pytest). 새 물리/렌더/학습/모델 호출 0. PR511 질감은 각 큐의 별도 대기 조건이며 미연결/미승인이다.

상세 근거·프레임별 경로/해시/색 마스크 비율·검출 수·원본 해시는 로컬 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/analysis/reloc8/`의 `report.md`, `carry-final2.json`, `selfmap-verified.json`에 있다. 색 비율은 검은 테두리를 제외한 휴리스틱 재질색 마스크이며 의미론적 분할 정답이 아니다. carry ORB는 축소 검토 영상의 진단값이고 제어기는 ORB를 사용하지 않는다. 이전 위험 집계는 평가 xy>0.15m 또는 yaw>10°를 썼다. reloc9부터 5°/10 cm 절대 기준과 보정 전 대비 악화 및 축별 악화를 함께 보고한다. 평가 GT는 제어 관문에 넣지 않는다.

## 재현

각 worktree에서 `PY=/Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python`을 사용한다. 원본은 위 로컬 회수 경로가 필요하다. 출력은 존재하지 않는 새 경로를 지정한다.

```sh
# carry worktree
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" -m scripts.analyze_reloc8 --flow carry --output /private/tmp/reloc8-carry-review.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" -m pytest -q tests/test_active_relocalization.py tests/test_solo_carry7.py tests/test_reloc8_carry.py
# selfmap worktree (앞 pytest 종료 후)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests "$PY" -m scripts.analyze_reloc8 --flow selfmap --output /private/tmp/reloc8-selfmap-review.json
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests "$PY" -m pytest -q tests/test_active_relocalization.py tests/test_reloc8_selfmap.py tests/test_selfmap6.py tests/test_self_map_executor.py
```

큐 생성은 커밋 뒤 carry의 `python -m scripts.prepare_reloc8_carry_queue --queue-out <새파일>`, selfmap의 `python -m scripts.prepare_selfmap7_queue --source-sha <전체SHA> --output <새파일>`이다. carry 3재현+새8(93290–93297), selfmap 30→180→180(93570–93572). 모두 승인/실행 플래그 false이며 첫 30초 원본 확인 후 다음 단계를 별도 승인한다. 실제 실행은 이번 범위 밖이다.

## 참고 자료

- [Burgard·Fox·Thrun, Active Mobile Robot Localization, IJCAI 1997](https://robots.stanford.edu/papers/burgard.active.html): 저자 초록/서지 확인. 센서 방향·이동 방향의 능동 선택을 적용했다. 요청의 “Active Markov localization”은 [저자 목록에서 RAS 1998, 25:195–207](https://www.cs.cmu.edu/~dfox/research.html)으로 확인되므로 1997 IJCAI 논문과 구분한다. 연결된 PS 전문은 열람 실패했다.
- [Thrun·Burgard·Fox, Probabilistic Robotics](https://robots.stanford.edu/probabilistic-robotics/): 저자 사이트 확인. 다중 가설/명령 이동/관측 갱신 원칙을 따르며 완전한 AMCL을 새로 구현했다고 주장하지 않는다. [Nav2 공식 odometry update](https://raw.githubusercontent.com/ros-navigation/navigation2/main/nav2_amcl/src/motion_model/differential_motion_model.cpp)의 명령 이동 불확실성 전파도 확인했다(코드 복사 없음).
- [Next-Best-View Selection for Robot Eye-in-Hand Calibration, 2023](https://arxiv.org/abs/2303.06766): 초록 확인. 유한 후보 시점의 정보 기준 선택을 참고했다. 이 과제의 RGB 검출 성능을 보증하는 자료로 사용하지 않았다.
