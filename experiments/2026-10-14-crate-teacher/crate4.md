# crate4: 6f312f74 관문 실패 두 계열 수정 후보

사용자 요청(2026-10-14): "실패 16개는 두 계열이다. 한 묶음으로 고친다", "각각 새 토글로 넣는다(기본 off, 관문 대기열에서 켬)", "unknown이면 놓기를 막는 규칙은 유지한다". 기준은 `6f312f74f25e284f9339a18de901e24667c17a31`, gcp1/n4-highcpu-64, 24/40. 원본 40개의 result/teacher/eval 원장 해시를 manifest와 대조했다([전체 기록](crate4-offline-summary.json)). 소스 수정·오프라인 시험과 새 GCP 성공은 구분한다.

## A: 조기 탐색 핸드오프가 아니라 재탐색 결함과 막힌 축방향 목표

- 원본 8/8에서 `search_handoff=false`; `search_timeout_handoff`는 **0/8**이다. 2.5–8초의 `handoff`는 `sim/grasp_act_teacher_v3.py`의 보이는 손잡이와 추정 자기 위치 간 거리 ≤0.8 m 표식이다. 탐색 종료/상위 지도 복귀가 아니다. 이를 혼동한 요약을 교정한다.
- 77209/12/13/24/28/29의 r1은 처음 띠를 본 뒤 놓친다. 기준 `sim/grasp_act_teacher_v3.py:144`의 `not self.ever_seen` 때문에 v2 완전 탐색에 다시 들어가지 못한다. 대신 155–164행의 팬/기울기 순환+차체 회전으로 돌아간다. 77212는 8초 첫 획득→23초 상실→65.6초 재획득, 77213은 30.5초 이후 짧은 획득/상실이 반복된다. 초기 LOS는 원래 **같은 XY에서 3 pitch×360° 회전하면** 보인다는 검사이며 초기 팬에서 즉시 보인다는 보장이 아니다. 배정은 서로 다른 손잡이이고 8건 모두 가시 관측 이력이 있다.
- 남은 77208은 r1 가시 593/593인데 blocked_goal/no_path **59/59**다. 77225는 가시 234/234인데 정렬 재관측 3회 후 중단한다. 별도 평가 좌표+정적 지도에서 축방향 목표의 하단 벽 여유는 각각 **9.98 mm / 60.59 mm**, 코드 여유는 **130 mm**다. 기준 `_route`의 단일 목표 거부와 `_approach`의 벽 여유 없는 정렬이 원인이다. 77225 실제 최종 차체 중심의 같은 벽 여유는 92.04 mm다. 이 수치는 평가 분석이고 제어 입력에 쓰지 않았다.
- `search_reacquire_v1`(기본 off): 이전 가시 여부와 무관하게 기존 v2의 발행 자세 안정화·3 pitch별 완전 회전을 재사용한다. 재획득은 0.3초 연속 가시여야 하며 짧은 깜빡임은 진행 중 탐색/시한을 초기화하지 않는다. 자기 화물을 가림 원통으로 넣던 `beam_1` 고정 제외도 해당 토글에서 cargo profile로 바꾼다. 경로/IK/학생 제어를 새로 만들지 않는다.
- rootcause의 완료 커밋 `a3f3be78f5547d7b44396cab38b6e57354b4a49d`를 병합해 `approach_goal_set_v1`을 재사용한다. 선택된 접근 자세를 정렬/READY까지 유지하고 모든 후보가 막히면 유한 시간에 끝난다. 상자에서는 모든 constraints 호출과 select_goal에 `CRATE` 형상 프로필을 전달한다. 빔 기본 profile=None은 그대로다. 다른 작업의 worktree는 수정하지 않았다.
- **rootcause 브랜치로 옮길 변경:** `sim/grasp_act_teacher_v3.py`의 재탐색 토글·0.3초 재획득·자기 화물 제외, 같은 파일 및 `sim/grasp_act_goal_set.py`의 선택적 cargo profile 전달. `_route` 후보 알고리즘은 다시 구현하지 않았다.

영상 확인 범위: 이번 세션은 **0프레임**이다. fetch-lite에는 원본 이미지가 없다. 처음/중간/끝 6시각×overview/r1/r2를 A/B 16건에 요청했다. 위 내용은 소스·명령/평가 원장에 근거한 결함 확인이며 물리 동작 원인(자세 회전/벽 접촉)의 영상 독립 검증은 회수 뒤 수행해야 한다.

## B: 분홍 몸체 외곽을 손잡이와 똑같은 강체로 요구

기준 `sim/crate_rgb_lift.py:135–143`은 lug/pink 모두 면적비·중심·외곽 크기에 같은 한도를 요구한다. B 8건은 모두 평가 안정 들기 **10.1초**다. 거부된 9개 로봇 판정은 전부 pink 외곽 변화가 원인이다: 정규화 외곽 변화 **0.10000000000000003–0.20417**가 한도 0.10을 넘는다. 그 비교에서 lug는 면적비 1.0494–1.1943, 중심 변화 0.0122–0.0362, 외곽 변화 0.0208–0.0667로 기존 조건을 통과한다. 일부 v2 판정은 첫 실패에 조기 반환하므로 뒤의 settled 비교는 원장에 없으며 이미지 없이 재구성하지 않는다. 물체 회전 자체가 원인인지는 영상 확인 전이다.

### 수정 전에 읽은 출처와 적용 경계

1. [QT-Opt, Kalashnikov et al. 2018, §5 및 Appendix D.3](https://proceedings.mlr.press/v87/kalashnikov18a/kalashnikov18a.pdf): 고정 외부 카메라에서 물체를 떨어뜨리기 전/후 장면 차분으로 성공 보상을 만든다. 놓기 후 라벨이므로 놓기 허가의 선행 조건으로 그대로 쓸 수 없다. 손목 영상 강체 조건의 검증 근거가 아니다.
2. [Levine et al. 2016, §5.2](https://arxiv.org/html/1603.02199v4): 집게 위치 판독과 drop test 장면 비교. 측정 집게 위치는 이 과제에서 금지이고 drop test는 놓기 전에 불가능하다.
3. [Amargant et al. 2025, GraspCheckNet §III–IV](https://arxiv.org/html/2505.03046v1): 집게 관심영역을 찾고 그 안에 물체가 있는지 분류한다. 물체 전체의 실루엣이 고정되어야 한다는 조건은 없다. [공개 저장소](https://github.com/pauamargant/HSR-GraspSynth)와 [generate_dataset.py](https://github.com/pauamargant/HSR-GraspSynth/blob/main/blenderproc_scripts/generate_dataset.py)의 충돌 기반 합성 라벨/COCO 출력을 읽었다. 공개 코드는 데이터 생성이며 이 상자에 검증된 분류기 체크포인트가 아니다. **집는 부위의 국소 근거와 물체 존재를 분리**하는 방식을 채택한다. 색이 고정되고 집게가 시야 밖인 우리 카메라에서는 할당된 색 손잡이 마스크를 관심영역의 기준으로 사용한다. 학습된 ResNet을 재현한 구현이라고 주장하지 않는다.
4. [Verginis et al. 2019, 협동 운반, Assumptions 1–2](https://people.kth.se/~dimos/pdfs/TCST2019_Manipulation.pdf): 힘 센서 없이도 자기 관절 위치/속도와 강체 파지 상대량을 요구한다. 자기 RGB+발행 명령만인 본 과제에는 하중 추정기를 그대로 넣을 수 없다.

`crate_rgb_lift_v3`(기본 off)는 기존 명령 검증과 두 완료/유지 표본을 유지하고, lug에 기존 강체 조건을 적용한다. pink에는 최소 면적/40% 잔존과 lug 대비 영상 아래쪽 중심 변화 ≤0.06을 요구한다. pink 외곽 크기 고정은 요구하지 않는다. 기존 0.06을 재사용했지만 이 규칙·임계값은 여전히 **미보정 후보**다. 영상 아래 방향은 실제 중력/바닥 높이 측정이 아니다. 팔이 완전히 정지했는데 영상도 그대로인 경우는 여전히 모호하며 이 후보를 물리적 하중 확인으로 보고하지 않는다. unknown은 계속 놓기를 차단한다. 정답/접촉/측정 관절 입력을 추가하지 않았다.

단독 교사 `b48ebdf1`의 `sim/rgb_lift_evidence.py`는 이번 브랜치에 아직 병합되지 않았다. crate의 v2를 복사해 공용화한 코드 및 적용용 patch가 그 브랜치에 있다. 이번에는 **공용 코어와 crate v2를 수정하지 않고** crate 전용 v3를 추가했으므로 solo_rgb_lift_v2의 기준/판정은 바뀌지 않는다. 향후 병합 때 v3 body 정책을 solo에 기본 적용하지 않는다.

## 검증·인계

- 관련 3파일만: `test_grasp_act_crate_teacher.py`, `test_grasp_act_search.py`, `test_crate_rgb_lift_v2.py`: **101 passed, 1 skipped, 1 deselected**. skip=선택 lookaround 모듈 부재, deselect=MuJoCo world 생성 시험. 명령 기반 재탐색 3회전·깜빡임·재획득, crate 형상 전달, CLI 토글, 합성 body 회전/소실/하향 이동/unknown 차단을 검사했다. 이는 GCP 성공 증거가 아니다.
- 새 gate **77300–77339**, split `crate_gate_v4`, 시작 시선 **40/40(두 로봇 80/80)**. 원래 제안 26/40 통과·14/40 거부를 보존했다. `mj_step`, `mj_step1/2`, `mj_forward`, `Renderer`를 예외로 바꾼 정적 kinematics/ray 검사다. 실행·렌더 0회.
- 실제 RGB 재판정 완료: **B 0/8, 기존 성공 0/24**, 음성 대조 **0/2**. 전부 이미지 미회수 상태로 8/8 또는 오탐 0을 주장하지 않는다. A는 들기 명령이 없으므로 시퀀스 부재를 음성 분류 성공으로 세지 않는다. 음성 대조는 실제 들기 실패한 과거 0.9 kg 77900/77901의 저장된 review 시각을 사용하며 0.30 kg 관문과 합산하지 않는다.
- `outputs/e2e18-admin/fetch-requests/crate4.txt`: 원본 해시와 GCP/Mac 경로, 양성/영상 480개+음성 12개, 총 **492개** 회수 요청. 운영자가 파일을 채우면 아래 명령으로 판정을 다시 만든다. 누락/오탐/미탐이면 exit 2이며 VM 실행을 제출하지 않는다.

```sh
python -m scripts.replay_crate_lift --root /Users/changmin/projects/ugrp/outputs/gcp1-runs \
  --negative-sequences experiments/2026-10-14-crate-teacher/crate4-negative-sequences.json \
  --out outputs/crate4-retrieved-replay.json --require-ready
```

대기열은 push SHA 확인 뒤 `20261014-crate-<sha8>.json`, ready=true로 발행하되 위 회수/재판정과 영상 검토가 실행 전 필수다. A 재현 77208/77212, B 재현 77204/77231 + 기존 77920–77922/77930–77932의 **진단 10개**가 모두 성공/감사0이어야 새 관문40을 시작한다. 동시 최대16, 진단/관문 순차, ≥38/40, 알려진 결함 확인 즉시 정지. 구 6f312f74 대기열은 superseded/ready=false다. 첫 gate 동시16의 30 SIM초 속도를 새로 확인한다(목표 후보 계산 비용이 바뀌었으므로 과거 속도를 승계하지 않는다). 원격 실행·새 관문·실제 파지·입력 감사·CI는 미확인이다.
