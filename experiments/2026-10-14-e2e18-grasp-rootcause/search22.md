# search22 — 기억 장애물별 확률 여유와 능동 재관측

기준 `961b2e81`(search21 시험 `38266bde`), PR #484, 기본 off `search22_v1`.
사용자 승인: gcp1 기존 n4-highcpu-64, 최대 3라운드, 각 같은 6계획·동시6·60 SIM초. 알려진 실패를 먼저 배치한다. 관문40·학생·학습·실물 성공으로 확대하지 않는다.

## 구현과 입력 경계

기억 장애물의 여유는 `5mm + sqrt(-2 log(.01)) * sigma`다. sigma는 상대 위치 2D 공분산의 최대 고유값 제곱근이다. 관측 공분산(2px/622.165px 초점 + 2mm 바닥, **설계 가정·미보정**)에 마지막 관측 이후 발행 바퀴 명령의 공분산을 합친다. `harness/self_map_csm.py`의 기존 50ms 속도 잡음·1초 상관 scale 모형을 `harness/command_covariance.py`로 분리해 그대로 재사용한다. M1 고정 프로필을 사용하고 정답 오차로 튜닝하지 않는다. 명령별 만료·yaw 레버암과 좌표 회전을 반영한다. 현재 프레임의 상대 기하는 search21의 5mm를 유지하고, 공분산이 없는 과거 기록은 140mm로 보수적으로 남긴다. 개별 장애물/검사점의 Gaussian 모형이며 전체 경로 99% 안전 보증이 아니다.

보이는 장애물은 그 관측으로 위치와 관측 공분산을 다시 쓴다. 기억 화물은 시간 만료만으로 지우지 않는다. 자기 발행 카메라 자세, 현재 시각의 보이는 기준물, 전체 장애물 반경+불확실 영역의 FOV/거리·가림 검사를 통과한 미검출이 0.3초 이어질 때만 clearing한다. 다시 보이면 즉시 복원한다. Nav2의 marking/clearing 분리를 자기 RGB에 맞춘 적용이며 LaserScan을 사용하지 않는다.

기억 여유만으로 거부된 후보의 장애물을 지정해 낮은 상자에는 카메라를 아래로 향한다. search21의 최대2회·각1.4초 유한 복구 구조를 유지한다. 발행 카메라/팔 sweep이 불가능하면 기존 충돌 검사 후진·옆걸음·재계획으로 돌아간다. 모든 후보가 막힌 경우 실제 실행 가능한 재관측을 남기며, 물리적으로 막힌 공간에서 병진 가능성을 꾸며내지 않는다. 변함없는 후보 3회 제외와 유한 인계를 유지한다.

`search22_v1`은 search21을 요구하며 기본 off다. off에서 기존 세계 모델과 search21 140/5mm 동작을 보존한다. 실행/보고/학습 적합도 모드 매칭에 포함한다. 정답은 평가에만 남고 invisible_measurements/held_world_reads 감사를 유지한다. 새 실행은 top 카메라 렌더도 끄고 자기 카메라 검토 프레임만 저장한다. Mac 물리/렌더·모델 호출은 하지 않는다. 로컬 결과/회수/운영 기록은 이 worktree에만 저장(`UGRP_RESULTS_ROOT`), 비활성 큐만 지정된 기본 checkout 큐 폴더에 둔다.

## 검증

오프라인 72통과: search22/21/20/batch 42, 기존 CSM/admission/search18 30. 공분산 성장/재관측 축소·정답 거부·off 보존·기하 겹침 거부·최대2회 낮은 화물 gaze·clear dwell/복원과 기존 전파/입력 경계를 검사했다. MuJoCo World/렌더 실행 없음.
GCP 결과는 실행 완료·원본 재집계 뒤 아래에 기록한다.

## 참고 자료

- Blackmore, Ono & Williams (2011), *Chance-Constrained Optimal Path Planning With Obstacles*, IEEE T-RO 27(6), 1080–1094, DOI https://doi.org/10.1109/TRO.2011.2161160 . MIT 저자 원문 저장소 URL https://dspace.mit.edu/server/api/core/bitstreams/1bcd431a-3fdd-4735-a689-2ea5d1f2b5d0/content 는 도구 본문 열람 실패(미확인); 제목/초록 수준 확인. 논문의 최적화기를 그대로 구현했다고 주장하지 않는다.
- Du Toit & Burdick (2011), *Probabilistic Collision Checking With Chance Constraints*, IEEE T-RO 27(4), 809–815, https://authors.library.caltech.edu/records/44h4y-qcn35 . 2026-10-15 저자 기관의 초록·서지 확인, 전체 논문은 metadata-only라 미확인. 로봇/장애물 상대 불확실성을 함께 다루는 원칙을 적용한다.
- Nav2 사용자가 준 obstacle.html / inflation.html URL은 모두 404. 2026-10-15 공식 이전 경로의 실제 본문 확인: https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/obstacle/ (marking, clearing, raytrace_min/max_range), https://docs.nav2.org/jazzy/configuration_and_development/configuration_guide/core_servers/costmap_2d/costmap_plugins/inflation/ (inflation_radius, cost_scaling_factor). footprint 내부를 무조건 비우는 옵션은 이식하지 않는다.
- 저장소 기존 자기 불확실성: `harness/self_map_csm.py:UncertainCommandOdometry.advance`, `harness/self_odom_grid.py:motion_profiles`, M1 calibration SHA 검사 유지. 기존 search21의 유한 복구·경로 진행 구현 재사용.

## 라운드1 — c099eb7a

2/6 성공, HOST_ERROR1, 감독 중단3. `candidate_audit`가 충분히 멀리 떨어진 장애물에 대한 검사 조기 반환값 `inf`를 원장에 그대로 넣어 `allow_nan=False` 최종 결과 직렬화가 실패했다. 감독기가 CHILD_HOST_ERROR로 전체 잔여3회를 중단했고 소유 worker0을 확인했다. 기하 계산과 승인 결과는 바꾸지 않고 원장에는 `gap_m=null`, 검사를 통과한 하한을 `gap_lower_bound_m`로 기록하도록 수정했다. 해당 비유한 값 직렬화 회귀를 추가해 관련43통과. 원격 전체 SHA256SUMS 검증과 로컬 lite 회수 완료. 실패/중단4회는 자기 카메라6장씩24장을 직접 확인했다. 원본은 `gcp1:/home/ugrp/ugrp-sim/runs/grasp-search22-r1-short6-gcp-c099eb7a`, 로컬은 이 worktree의 `outputs/gcp1-runs/`다. 첫30초 측정은 HOST_ERROR 때문에 미완료이므로 속도 통과로 보고하지 않는다.

라운드1의 315709 cargo_v6 원본을 명령/phase 불일치0으로 순수 재생했다. 재관측 대상 선정이 목표 자세의 거부만 보고, 실제로는 연결 경로에서만 기억 여유가 막힌 경우를 빠뜨렸다. 목표의 yellow_1은 현재 관측으로5mm였지만, 과거 red_2의 sigma35.16mm·여유111.70mm가 연결 경로를 지웠다. 라운드2에서는 연결/후퇴 검사에서 **기하 겹침 없이 기억 여유만** 거부한 샘플도 대상 선정과 후보 원장에 포함한다. 단순 여유 축소/정답 보정은 하지 않는다.
