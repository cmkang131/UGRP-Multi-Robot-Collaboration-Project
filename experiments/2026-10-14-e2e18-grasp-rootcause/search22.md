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

## 라운드2 — 645acabd

원본 재집계3/6, 완료 실패3, HOST_ERROR0, 중단0. 첫 두 장면은 마지막10틱 모두 계획3초 예산을 소진했다. 중단 요청을 보낼 때는 이미6회가 모두 끝나 소유 worker0이었으며 SIGINT를 실제 보낸 PID는0이다. 사후 감독 기록은 기존 원본 manifest와 별도 sidecar로 남긴다. 실패3회 자기 카메라6장씩18장을 직접 봤다. base8311709는 원인 tile 대신 can_1, v6 두 실패는 낮은 yellow_1을 보았고, 원장에서도 이미 fresh=true인 같은 대상으로 유한 예산을 쓴 것이 확인됐다.

라운드3 수정은 계산·대상 선정이다. 동일 nav/world/pose 감사는 재사용하고, 시작 자세가 이미 거부되면 같은 시작을 공유하는31개 연결 후보를 다시 검사하지 않는다(기하/확률 승인 조건은 그대로). 재관측은 현재도 보이지 않는 실제 기억 차단물 중 자기 추정 위치에 가장 가까운 것을 고르며, 현재 RGB로 다시 보인 뒤0.3초면 재계획한다. 낮은 물체의 시선 높이는 계속 관측 top bound의 중간이다. 관련46통과.

## 최종 결과 — 라운드3 4c18f074, NOT_READY

| seed | 장면 | 성공 | SIM초 |
|---|---|---|---:|
| 8311709 | base | false | 12.3 |
| 8311709 | cargo_v6 | false | 14.7 |
| 315709 | cargo_v6 | false | 29.5 |
| 315709 | base | true | 33.5 |
| 8312300 | base | true | 24.8 |
| 8312301 | base | true | 28.0 |

**3/6, 완료 실패3, HOST_ERROR0, 중단0. 최대3라운드에서 종료했고 네 번째는 제출하지 않았다.** 마지막 반복 예산 소진 확인 직후 중단을 요청했지만 이미 유한 인계로 전부 종료돼 실제 SIGINT 대상0이었다. 자기 worker0·임대 제거·6슬롯 해제를 확인했다. 다른 작업의 임대/프로세스가 있어 gcpctl stop은75로 유예됐고 다른 작업이나 VM을 강제로 멈추지 않았다.

남은 결함: 두8311709는 마지막10틱이 모두 계획3초를 소진한다. 타일/red_2가 실제로 다시 보인 구간도 있으나 재관측 대상 집합에 다른 연결 후보의 can_1/yellow_1까지 섞이며 해당 대상을 반복해 보는 문제가 남았다. 315709 cargo_v6도 r2/yellow_1 재관측 뒤 연결 경로 또는 연결 중 band 가시성 실패로 인계한다. **고정140mm를 없앤 것이 완전한 실행 경로 확보를 뜻하지 않는다.** 근거리 성공 수정 완료나 관문/학습 준비로 보고하지 않는다.

추가로 search22의 유지 검사에도 새 admission envelope를 사용해 search21의2mm 유지 여유와 달라진다. 이 차이는 현 후보의 미검증 설계 한계이며, 다른 원인을 덮는 해결책으로 채택하지 않는다. 기본 off를 유지한다. 소스 관측 공분산과 M1 과정 잡음의 실제 확률 coverage도 검증하지 않았다. 이후 이 유지 정책·차단물 귀속·계획 시한을 검토해야 하며 이번 실행 상한 밖의 수정/실험은 하지 않았다.

### 후보/σ 원장과 원본 확인

라운드3의 search22 body fallback 후보 시험 수는 기억 여유924, 현재 기하1773, IK4523, 집게 각도8667이다. 나머지는 feasible7, no_path519, 연결 band 가시성164이며 후보 시험 단위다(동일 후보의 반복 재검증 포함). 전체 계획 후보의 기존 reason 집계는 `search22-final-blockers.json`의 각 교사 원장에 별도로 보존한다. 부분 계획이3초에서 중단돼 반환되지 않은 후보를 완전 후보로 세지 않는다.

실제 원장에 남은 315709 cargo_v6 red_2의 sigma7.91–37.64mm/여유28.99–119.23mm, yellow_1은19.38–27.72mm/63.81–89.13mm였다. 마지막 허용 입력을 별도 재구성한 값은 base8311709 tile_1 fresh sigma3.685mm·실제 적용 여유5mm, v6 red_2 fresh sigma3.605mm·여유5mm, 315709 v6 yellow_1 stale sigma2.605mm·여유12.904mm다. 이 재구성은 자기 관측·실제 발행 명령만 사용한 분석이며 실제 재실행/새 궤적이 아니다. 마지막 가족 목표/시작점 단독 검사가 비어 있어도 전체 연결/팔/가시성 검사가 통과한 것은 아니다.

3개 라운드 모두6/6 입력 감사 enabled, invisible_measurements=0·held_world_reads=0. 라운드3 전체 wall/SIM 중앙4.8055로 경고(>3.5, <6.0), 속도로 막힌 결과는 아니다. 별도 속도 실행은 하지 않았다. 다만33.5 SIM초에 끝난 base315709의 정확한 첫30초 wall endpoint가 저장되지 않아, 이 수치는 전체 실행 비율이며 첫30초 정밀 측정 완료로 확대하지 않는다.

GCP 원본6개씩의 `SHA256SUMS` 전체 검증과 로컬 회수 해시 대조를 마쳤다(라운드1/2/3 로컬192/193/194파일, 선택 원본 자기 프레임 각72장). 실패/중단은 각6장씩 총60장을 직접 봤다(24+18+18). 사후 중단 시도 sidecar는 원래 manifest와 별도 해시로 남긴다. 원본 경로/해시·실패/HOST_ERROR·감사·후보·프레임 목록은 `search22-results.json`; 상세 원본·원장은 이 worktree `outputs/gcp1-runs/`와 `outputs/search22/`다. GCP 영구 디스크 원본은 보존했지만 별도 외부 raw 백업을 완료했다고 주장하지 않는다.

라운드1 ep002는 로그 표현만 바꾼 분석 재생에서 명령/phase 불일치0이다. c099eb7a 원소스의 ep000 추가 재생은 wall 계획 시한 차이로68틱 불일치여서 실제 궤적/후보 증거로 사용하지 않는다. HOST_ERROR/중단3회에서 미직렬화된 최종 교사 통계를 임의로 채우지 않았다.

오프라인 최종 관련46통과, 공통 CSM/admission/search18 30통과. 문법·JSON·소스 해시·큐 검증을 마쳤다. 모델 호출0·모델 토큰0·VM 모델 키 전송0·Mac 물리/렌더0·top 렌더0.

### 비활성 대기열과 재현

`/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-grasp-search22-4c18f074-diag.json`은 **BLOCKED_FAILED_SHORT6**, `short6_passed=false`, base/cargo_v6 각각 재현4+신규12, 합계32, 전역 max_parallel16이다. 알려진 실패를 앞에 둔다. 승인·실행·제출·관문·학습·승격·과거 결과 합산 플래그는 전부false다. 신규8312200–8312211은 원격 원본 계획1163개에서 실행 중복0을 확인했다. 기존 원본/결과와 합산하지 않으며32회는 제출하지 않았다. 검토 사본 `search22-queue.json`은 외부 큐와 바이트가 같다.

재현 명령 원문은 `search22-command.json`, 셸형은 아래다. 이번에는 실행하지 않았다(세 라운드 상한). 이후 별도 실행을 요청할 경우 먼저 비용·전체40 이하와6슬롯 예약을 확인하고, 교사 소스가 시험SHA의 `source_hashes`와 같은지 검증해야 한다.

```sh
bash experiments/2026-10-14-e2e18-grasp-rootcause/search22-reproduce.sh
```
