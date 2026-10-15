# AMCL 1 — 정적 지도, 자기 RGB, 명령 오도메트리

## 범위와 출처

기본 브랜치 `c72a2b50628e549fee8032378f4c7cf709fe688c`에서 시작했다. `git fetch origin`과 열린 PR 목록을 확인하고 #480·#440·#496에 3줄 범위 댓글을 남겼다. 원본 PR #480의 `4fee842c24a2918d51cb0cbb95d3cbdab774e977`에서 정적 위치 추정·저장 RGB 추출·SE(2) 평가·관련 2개 시험을 가져왔다. 원본 바이트 해시는 `source-provenance.json`이다. 최초 평가 코드의 커밋은 `55cf561f0248b1a30203b7af71216be3f4f4ba7e`이다.

`pr480-static-localization-plan.json`의 6개 실행은 탐색용 부분집합이다. 이번 비교 목록 `cohort.json`은 #480 평가 원본에서 `route=false`인 **40실행 × 2로봇 = 80구간**을 고정했다. 스테이징 무효 8실행·감독 중단 2실행도 원본 분모대로 보존한다. 유효 물리 성공 코호트라는 뜻은 아니다.

## 구현

- `harness.map_amcl.create(..., option='off')`는 지도를 읽지 않고 `None`을 반환한다. 명시적 `amcl_walls_v1` / `amcl_landmarks_v1`만 활성화한다. 기존 제어기 기본값은 그대로이며, 실제 주행 제어기 통합·검증 완료를 주장하지 않는다.
- 초기 입자는 정적 자유 공간 전체에서 균일하게 뽑는다. 원본 #480의 정적 벽 거리장·0.15m footprint rejection과 cluster 추정은 재사용한다. 이전 자기 위치·정답 시작 위치·화물 세계 좌표를 받는 인자가 없다.
- 벽 endpoint의 `z_hit exp(-d²/(2σ²)) + z_rand/range_max`를 Nav2의 `1+sum(p³)`로 합산한다. 바닥은 #480의 **색 구역 경계선**과 문 검출을 재사용한다. 반복 checker 격자 전체를 신규 지도 랜드마크로 등록한 것은 아니다. 지도가 없는 격자선에 임의 세계 좌표를 붙이지 않는다.
- 명령의 body-frame SE(2) 증분을 Nav2 omni motion model에 준다. 센서 갱신 사이 명령은 누적하고, 측정 없는 출력은 그 누적 명령으로 예측한다. 명령은 실제 이동의 증명이 아니다. 정지 반복 영상은 재가중하지 않고, 새 명령 카메라 자세는 다른 관측 방향으로 인정한다. 명령 카메라 FK·settling은 원본 RGB adapter 그대로다.
- 정규화 전 `sum(prior*likelihood)/N`으로 slow/fast 평균을 갱신하고 `max(0, 1-fast/slow)` 확률로 자유 공간 입자를 주입한다. 매 채택 관측에서 multinomial/KLD resampling을 한다. 원본 준비 코드의 ESS-only resampling이나 GMapping motion noise를 새 후보에 사용하지 않는다.
- KLD는 Nav2의 bin 0.5m/0.5m/10°, strict `N > limit`, `k<=1 → max`를 따른다. Nav2 `pf_z=.99`는 코드에서 inverse CDF 없이 직접 쓰이므로 그대로 구현했다. 기존 vendor의 `confidence=.99 → z=2.326` 또는 최대 100,000 입자와 다르다. 원본 vendor는 수정하지 않았다.
- `scripts.extract_e2e_pose_features`는 저장 JPEG SHA와 frame ID를 검사한다. 같은 JPEG hash가 다른 시각·servo에서 반복돼도 frame ID로 결합한다. 누락은 빈 측정으로 바꾸지 않고 오류로 남긴다. no-substep frame에는 증분을 넣지 않는다.
- 재생기는 먼저 추정 궤적을 확정하고 평가 전용 trajectory를 연다. 원본 시각 변환과 동일 SE(2) 강체 정합을 적용한다. 위치와 방향에 별도 회전 보정을 맞추지 않는다. 전역 위치 착오가 강체 정합에 가려질 수 있어 AMCL의 절대 지도 오차도 함께 낸다. 기준선은 원점부터 적분하므로 그 절대 좌표는 비교 대상이 아니다.
- 모든 프레임의 명령/추정 증분·잔차를 기록한다. 5cm/5° 초과는 점프 검토 표식이며 검증된 물리 속도 한계가 아니다. 전체 구간·수렴 전·미해결 관측을 제외하지 않는다. 성공 조건과 개선 판정은 `comparison-policy.json`에 고정했다.

## Nav2 기본값과 차이

공개 구현 `b58a7573f44a984fdc5f3eaa80c4b62ac529ab9d`의 기본값을 직접 읽었다. 입자 500–2000, `pf_err=.05`, `pf_z=.99`, `alpha1..5=.2`, `update_min_d=.25m`, `update_min_a=.2rad`, resample interval 1, 60 beams, `z_hit=z_rand=.5`, `sigma_hit=.2m`, 거리장 상한 2m, range max 100m를 사용한다. Nav2의 기본 recovery alpha는 둘 다 **0**이다. 이번 후보는 요청된 augmented recovery를 켜기 위해 원본 vendor와 같은 **slow=.001 / fast=.1**을 명시했다. 차동구동 기본 모델 대신 omni를 고른 것은 MasterPi의 옆 이동 때문이다. 입자 수·잡음·측정 계수를 평가 정답으로 맞추지 않았다.

## 검증과 실행

관련 3파일만 검사: `test_map_amcl.py`, `test_e2e_static_rgb_localizer.py`, `test_e2e_stage_pose_eval.py`. 첫 실행은 시험의 자유 공간 x범위 기대치가 벽 footprint를 포함해서 1개 실패했다. 벽 배제 후 범위를 확인하도록 고쳤고 **14 passed**. KLD 적응 수·절대 likelihood recovery·omni 잡음·정지 중복관측·전역 초기화·정답/화물 입력 거부·시간 정합·누락 분모를 확인했다. 물리·렌더·학습 시험은 없다.

실행 예시(기존 환경, 저장 파일만):

```sh
python -m scripts.sim_cli workflow run map-amcl-replay -- \
  --raw-root /path/to/saved-runs --feature-root /path/to/new-features \
  --extract-saved-rgb --map-amcl amcl_v1 --output /path/to/new-replay
```

## 저장 기록 결과

실행 소스 `9ade6baf`(전체 SHA는 `summary.json`)를 커밋·push했다. 공통 관리 경로 `map-amcl-replay`의 실제 프로세스 종료 코드 0·`process_completed`를 확인했다. **이는 기준 재검산/재고 조사 종료이며 AMCL 비교 완료가 아니다.** 원본은 `/Users/changmin/projects/ugrp-wt/e2e18/outputs/azure3-runs/`, 출력은 이 worktree의 `outputs/map-amcl-replay-9ade6baf/`다. 전체 원본/프레임별 출력 SHA는 `offline-replay.json.zst`에 있고 짧은 요약은 `summary.json`이다. 원본은 로컬 보관이며 원격 백업을 새로 검증하지 않았다.

| 후보 | 평가 / 요청 구간 | 위치 중앙값 | 방향 중앙값 | 5cm·5° | 거리비도 포함 |
|---|---:|---:|---:|---:|---:|
| fused odom 기준 | 80 / 80 | 9.5148cm | 11.2121° | 3 / 80 | 3 / 80 |
| AMCL 벽 + 명령 | 0 / 80 | 미측정 | 미측정 | 미측정 | 미측정 |
| AMCL 벽 + fused | 0 / 80 | 미측정 | 미측정 | 미측정 | 미측정 |
| AMCL 벽·바닥 + 명령 | 0 / 80 | 미측정 | 미측정 | 미측정 | 미측정 |
| AMCL 벽·바닥 + fused | 0 / 80 | 미측정 | 미측정 | 미측정 | 미측정 |

기준 거리비 중앙값 **1.0582658**. #480의 구간별 위치/방향/거리비와 최대 차이 **2.54e-13**으로 같은 결과를 재현했다. 명령 대비 잔차 5cm/5° 이내인 프레임 전이는 **37,094/37,492**, 초과 표식은 **398/37,492**다. 이 표식은 명령과 다른 추정 갱신을 찾는 지표이지 실제 물리 점프 판정은 아니다. 원본 fusion 분류는 command_kept 18,392 / fused 11,300 / vo_replaced 7,880이며 초음파 zero 분기는 **0**으로 확인했다.

필요한 JPEG **37,572장 중 로컬 존재 0장**이다. 80구간 모두 frames/ownmap/평가 텍스트는 있으나 RGB 폴더는 비어 있다. 누락을 빈 관측으로 대체하지 않았고 AMCL 실패나 통과 0/80으로 세지 않았다. 따라서 개선 여부는 미측정이며 **짧은 주행 진단 요청은 만들지 않았다**.

대신 기존 JPEG 회수·특징 추출·동일 80구간 비교 요청만 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-map-amcl-9ade6baf.json`에 저장하고 복사본 해시를 검증했다(`gcp-feature-queue.json`, `queue-receipt.json`). `coordinator_approval.approved=false`, `gate_promotion_authorized_if_all_conditions_pass=false`이다. 현재 원격 JPEG 가용성은 미확인이다. 조정자가 원본 SHA가 맞는 자료를 준비하고 승인하기 전 실행하지 않는다. 이번 작업의 물리·렌더·학습·모델 호출은 모두 0회다.

## 참고 자료

- Thrun, Burgard, Fox, *Probabilistic Robotics* (2005), [저자 사이트](https://robots.stanford.edu/probabilistic-robotics/)와 [저자 공개 그림](https://robots.stanford.edu/probabilistic-robotics/fig.pdf): MCL/전역 위치 추정·KLD 그림 확인. **책 본문 전체와 Table 6.3/8.3/8.4 원문은 이번 세션에서 미확인**. 알고리즘 수식·기본값은 아래 공개 원문과 코드로 대조했다.
- Fox (2001), [KLD-Sampling: Adaptive Particle Filters](https://papers.neurips.cc/paper/1998-kld-sampling-adaptive-particle-filters.pdf): 원문 확인. occupied bin 수에 따라 필요한 표본 수를 바꾼다. Nav2처럼 resampling에 적용하는 구현과 원 논문의 sampling 절차를 구분한다.
- [Nav2 pf.c](https://github.com/ros-navigation/navigation2/blob/b58a7573f44a984fdc5f3eaa80c4b62ac529ab9d/nav2_amcl/src/pf/pf.c): `pf_update_sensor`, `pf_update_resample`, `pf_resample_limit` 직접 확인. 평균 정규화·recovery reset·KLD 종료 규칙 근거.
- [Nav2 amcl_node.cpp](https://github.com/ros-navigation/navigation2/blob/b58a7573f44a984fdc5f3eaa80c4b62ac529ab9d/nav2_amcl/src/amcl_node.cpp), [likelihood field](https://github.com/ros-navigation/navigation2/blob/b58a7573f44a984fdc5f3eaa80c4b62ac529ab9d/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp), [omni model](https://github.com/ros-navigation/navigation2/blob/b58a7573f44a984fdc5f3eaa80c4b62ac529ab9d/nav2_amcl/src/motion_model/omni_motion_model.cpp): 기본값·cubic score·옆 이동 잡음 확인. 문서 URL은 접근 실패하여 같은 고정 커밋 소스를 직접 확인했다. 다운로드 파일 해시는 `references.json`.
