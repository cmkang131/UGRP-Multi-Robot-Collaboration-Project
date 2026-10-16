# s4grip2 — 자기 RGB 이탈 감지용 유지/외란 짝 자료 (사전 등록)

`research_result=false`, 평가 전용 개발 자료. S4 모델·협업 효율·실물 성능 결과가 아니다.
기존 S4 LLM와 기존 CV 기본값은 그대로이며 `grip_temporal_rgb_v1`은 오프라인 선택 토글이다.

## 실행 전 고정

- S3 parent `ad844d13e01f2871e39bf9b6a59c2636365bec7e` 위에 쌓되, 새 S3fix16 동작은 쓰지 않는다.
  집기 설정은 s3fix14 `4384d61cfeafef96e62fd90355fe05c8cfa38699`의 O 지점·고정 arm tape를 재사용한다.
  원래 저장 checkpoint는 집기 **전** 상태이므로 성공 checkpoint를 불러왔다고 주장하지 않는다.
  O 설정 복원 후 8 SIM초 동일 tape로 파지·상승하고 그 시점 integration state를 eval_only에 보존한다.
  이때부터 6 SIM초를 촬영하며 시작 5프레임 양쪽 접촉을 사후 검사한다. 실패 사례도 제외 이유와 수를 남긴다.
- oracle-x86, OSMesa, LP_NUM_THREADS=4, OMP_NUM_THREADS=1, 동시 6개, 24사례.
  job당 4사례 약 65.4 SIM초(<120), 총 약392.4 SIM초. Mac 물리·렌더·실제 모델 호출 0회.
  별도 스모크는 생략하고 코드/관련 pytest 완료 뒤 전체 묶음 1회 제출한다.
- r1/r2: long_beam 두 로봇 고정 파지, r3: cyan 고정 파지. 카메라/FOV/외관/접촉 프로필 동일, weld OFF.
  각 로봇·split마다 유지 2 + 외란 2. 같은 seed의 유지/외란은 같은 초기 상태와 명령 tape다.
- 외란은 환경에서만 2.0~2.3초에 파지 액추에이터 force range를 0.001배로 제한하고 물체에
  0.4~0.8 N 수평 힘을 0.6초 가한다. 빔은 두 소유자의 힘을 함께 약화한다. 손가락 열기 명령·순간이동은 없다.
  힘 방향·크기·시점은 아래 seed에서 미리 생성했고 JSON에 고정한다. 유지 조건에는 외란이 없다.
  이는 motor fault+push 복합 외란이며 자연 미끄러짐 또는 한 로봇만 놓는 경우를 대표하지 않는다.
- 실제 접촉 이탈이 의도된 진단이므로 drop abort만 적용하지 않고 weld/비유한 상태/로봇 tilt 한도는 유지한다.
  고정 명령 tape에는 영상·접촉·판정 피드백이 전혀 없다. detector는 사후 자기 RGB와 시각만 받는다.
  자세·관절·접촉·짐 좌표는 eval_only에만 보관한다. 반복별 부하 평균·소스·입력·환경·프레임 해시 보존.
- source를 커밋·push하여 고정한다. 제출기에서 archive를 먼저 원자적으로 전송한 후 6개를 동시에 보낸다.
  메모리 <6GiB 거절(exit3)만 같은 SHA/명령으로 30초 대기 후 재제출(최대1시간); SIM 실패 재시도 없음.
  ENOSPC 및 실행 오류는 HOST_ERROR. 실패·부분 raw도 보존, 중간 변경/사례 대체 없음.

## 탐색/확증과 판정 (실행 전에 봉인)

`explore` 12사례, `confirm` 12사례. 확인되지 않은 confirm raw는 분석하지 않은 채 보관한다.
이번 후보의 코드·임계값은 `detector-freeze.json`으로 **자료 생성 전부터** 봉인한다.
explore를 먼저 분석하되 이번 확증 평가까지 수정하지 않는다. 실패하면 결과 그대로 보고하고 다음 버전을 별도로 등록한다.
seed는 외란에 사용된다. O 초기 상태는 같으므로 유지 영상/외란 이전 영상은 중복될 수 있다.
확증은 새 외란 seed에 대한 제한된 확인이며 새로운 장면·물체·자세의 독립 일반화 검증이 아니다. 해시 중복 수를 함께 보고한다.

카메라는 0.1 SIM초 간격, 사례별 61프레임. 평가 접촉은 dist<=0인 지정 물체-양 손가락 기하로 구한다.
양쪽=held, 한쪽=partial, 없음=zero. 첫5프레임 모두 held인 사례에서 연속3 zero의 **첫** 프레임을 이탈 onset으로 정한다.
partial/unknown을 이탈 정탐으로 바꾸지 않는다. 접촉을 시작 자격·라벨·지연 계산에만 쓰며 detector 호출에는 넣지 않는다.
양성 분모는 실제 확인된 이탈 에피소드, 음성은 실제 유지 에피소드다. 배정된 외란/유지 수와 실제 생성 성공 수를 별도 기록한다.
이탈 이전의 최초 경보는 조기 오탐이고 정탐으로 재활용하지 않는다. 무감지는 miss, delay=null.
정탐 지연은 최초 이탈 프레임부터 최초 경보까지 프레임 수와 SIM초(0.1초 분해능).
프레임 TP/FN/FP/TN 및 unknown도 별도 집계하되 연속 프레임을 독립 표본이라고 하지 않는다.
기존 long_beam CV의 False→이탈 해석도 비교 출력하되 원래 log-only이며 r3에는 미적용(빔 전용).

## 후보와 표준 방법 근거

[Marx et al. 2023, Frame-Based Slip Detection](https://doi.org/10.3390/app13158620),
[저자 대학 PDF](https://ris.utwente.nl/ws/portalfiles/portal/419033722/applsci-13-08620-v2.pdf):
그리퍼 기준 물체의 시간 변화와 배경 제거, 여러 시간 간격의 결합을 사용한다. depth/metadata를 쓰는 부분은
우리 입력 경계에 맞지 않아 가져오지 않는다. 이 논문의 성능 수치를 본 실험에 이전하지 않는다.
[OpenCV optical flow 공식 문서](https://docs.opencv.org/4.13.0/d4/dee/tutorial_optical_flow.html)는
밝기 보존·근방 운동 가정과 corner 기반 LK 추적을 설명한다. 현재 근접 영상은 무늬 없는 물체가 화면을 채워
flow 특징점이 빈약하므로 기존 저장 이미지와 기존 색 마스크를 이용한 실루엣 시간 비교를 먼저 시험한다.
기존 [owncam_pair_lift_v3](../../../harness/owncam_pair_lift_v3.py)의 저조도 색 마스크/시간 IoU도 재사용 근거다.

손가락 자체는 파지 영상에서 보이지 않는다. 고정 wrist-camera의 첫3프레임 다수결 색 마스크를 anchor로
유지하며 ROI는 x64:576,y48:456(4px stride), 빔 hue25~54/cyan80~105, S>=100,V>=60.
anchor 면적<2%면 계속 unknown. IoU<0.60 또는 anchor 잔존율<0.60 또는 정규화 centroid 이동>0.10이
연속3프레임이면 grip_lost, 이후 epoch 내 latched. 시간역행/0.15초 초과 간격/invalid RGB는 unknown.
이것은 '시각적 유지/변화'이며 양손 접촉을 직접 관측하거나 보장하지 않는다. 동작 중 카메라 운동·가림·조명 변화에
대한 검증은 이번 범위 밖이다. 기본 detector=legacy, 실제 S4 LLM GO 경로/컨트롤러 변경 없음.

## 고정 제출표

각 명령은 `ORACLE_HOST=oracle-x86 LP_NUM_THREADS=4 $S/oracle_run.sh <worktree> <name> -- <command>`.
`<SOURCE_SHA>`는 사전 등록 커밋 HEAD 전체40자리로 제출기가 한 번 치환한다.
전체 전송: `python3 -m scripts.submit_s4_grip_batch --oracle-runner <runner> --output <new-admissions.json> --submit`.

| 이름 | explore seed | confirm seed | 명령 |
|---|---|---|---|
| s4grip2-r1-hold-r1 | 32000, 32001 | 42000, 42001 | `.venv-sim/bin/python -m scripts.run_s4_grip_dataset --expected-source-sha <SOURCE_SHA> --output outputs/s4grip2-r1-hold-r1/raw --job s4grip2-r1-hold-r1 --execute` |
| s4grip2-r1-loss-r1 | 32000, 32001 | 42000, 42001 | `.venv-sim/bin/python -m scripts.run_s4_grip_dataset --expected-source-sha <SOURCE_SHA> --output outputs/s4grip2-r1-loss-r1/raw --job s4grip2-r1-loss-r1 --execute` |
| s4grip2-r2-hold-r1 | 32100, 32101 | 42100, 42101 | `.venv-sim/bin/python -m scripts.run_s4_grip_dataset --expected-source-sha <SOURCE_SHA> --output outputs/s4grip2-r2-hold-r1/raw --job s4grip2-r2-hold-r1 --execute` |
| s4grip2-r2-loss-r1 | 32100, 32101 | 42100, 42101 | `.venv-sim/bin/python -m scripts.run_s4_grip_dataset --expected-source-sha <SOURCE_SHA> --output outputs/s4grip2-r2-loss-r1/raw --job s4grip2-r2-loss-r1 --execute` |
| s4grip2-r3-hold-r1 | 32200, 32201 | 42200, 42201 | `.venv-sim/bin/python -m scripts.run_s4_grip_dataset --expected-source-sha <SOURCE_SHA> --output outputs/s4grip2-r3-hold-r1/raw --job s4grip2-r3-hold-r1 --execute` |
| s4grip2-r3-loss-r1 | 32200, 32201 | 42200, 42201 | `.venv-sim/bin/python -m scripts.run_s4_grip_dataset --expected-source-sha <SOURCE_SHA> --output outputs/s4grip2-r3-loss-r1/raw --job s4grip2-r3-loss-r1 --execute` |


## 결과

아래 완료 결과를 추가했다. 위 사전 등록의 실행 조건·임계값·분모는 바꾸지 않았다.
번호 확인: main+열린 PR 브랜치에서 최대 v162/workflow7.55.0 확인 후 v163/7.56.0 예약.

## 완료 결과 — 후보를 S4 안전 정지 감지기로 채택하지 않음

물리 소스 **`f95cfb75686dd2486e6844c21d28a643a96955b9`**. 6개 작업 모두 첫 admission 성공,
LP_NUM_THREADS=4, EXIT=0. 24/24사례 시작 파지 자격 충족, 유지12/외란12가 실제 유지12/이탈12로 생성됨.
각 사례16.35 SIM초, 총392.4 SIM초. job wall210.59~232.07초(동시 실행, 합을 배치 wall로 해석하지 않음).
Mac 물리0·MuJoCo 렌더0·모델 호출0; 저장 JPEG→MP4 인코딩만 Mac에서 수행했다.

[탐색 raw 판정](explore-report.json)은 정탐5/6, 유지 경보0/6이었다.
[탐색 후 봉인 유지 결정](explore-decision.json)에 따라 후보 코드/임계값 수정 없이 확증을 열었다.

| 확증 후보 | 실제 이탈 정탐 n/N | 유지 사례 경보 n/N | 이탈 전 조기 경보 | 정탐 지연 프레임 / SIM초 |
|---|---:|---:|---:|---|
| r1 | 2/2 | 0/2 | 0/2 | 2,2 / 0.2,0.2 |
| r2 | 2/2 | 0/2 | 0/2 | 2,2 / 0.2,0.2 |
| r3 | 0/2 | 0/2 | 1/2 | 정탐 없음(null) |
| 합계 | **4/6** | **0/6** | **1/6** | 관측된4건 모두 **2프레임 / 0.2 SIM초** |

[확증 원본 판정](confirm-report.json). r3 seed42200은 frame23(2.3초)에 경보를 냈지만
평가상 단측 접촉이 frame26까지 남았다. 양측 접촉 소실 onset은 frame27(2.7초)이므로
4프레임·0.4초 조기 경보를 정탐으로 바꾸지 않았다. seed42201은 anchor에 cyan 색 영역이 없어서
61/61프레임 unknown, 이탈도 미감지다. 같은 seed의 유지 사례도 61/61 unknown이다.
따라서 유지 경보0/6은 관측 완전성·안전성의 증명이 아니다.

| 확증 프레임 (서로 상관됨) | r1 | r2 | r3 | 전체 |
|---|---:|---:|---:|---:|
| 이탈 프레임 중 경보 TP | 71/75 | 74/78 | 34/65 | 179/218 |
| 실제 held 중 오경보 FP | 0/169 | 0/166 | 0/167 | 0/502 |
| held 중 unknown | 8/169 | 8/166 | 89/167 | 105/502 |
| 이탈 중 unknown | 0/75 | 0/78 | 31/65 | 31/218 |
| 이탈 중 held(FN) | 4/75 | 4/78 | 0/65 | 8/218 |

r3의 34 TP프레임은 조기 경보가 latched된 이후 값이다. **에피소드 정탐0/2와 혼동하지 않는다.**
partial12프레임은 별도이며 정확도 분모에 합치지 않았다. 후보 held 정답 응답은397/502,
초기 anchor 2프레임을 포함하여 unknown을 빼고 분모를 작게 만들지 않았다.

같은 확증 빔 자료의 기존 CV(False→이탈 진단적 해석)는 held 오경보 **335/335프레임**,
유지 사례 경보 **4/4**, 올바른 시점의 에피소드 정탐 **0/4**(전부 이탈 전 이미 경보)였다.
기존 CV는 원래 log-only이며 r3는 빔 전용식의 비교 대상이 아니다. 실제 S4 LLM 감지 성능은 여전히 미측정이다.

## 자료·라벨 감사

원본: `/Users/changmin/projects/ugrp/outputs/oracle-runs/s4grip2-{r1,r2,r3}-{hold,loss}-r1/`.
파생 평가: `/Users/changmin/projects/ugrp/outputs/s4grip2-offline/{explore,confirm}/`.
자기 RGB 1,464개 및 해시, 평가용 접촉/라벨, held-start integration state, setup/고정 tape/외란 로그 보존.
[회수 확인](raw-verification.json): manifest가 열거한2,124개 파일·63,427,202바이트 SHA-256 일치.
[경계 감사](boundary-verification.json): 유지/외란12쌍의 **발행 명령 로그 바이트 동일**, weld OFF5,328표본.
조건부 성공을 제어에 되돌리는 경로가 없다. 이미지 unique SHA는 전체1,187/1,464,
탐색592/732, 확증595/732, split 간 같은 SHA는0([중복 기록](duplicates.json)).
O 설정 위치는 같지만 seed는 외란 외에 표준 world 생성에도 전달된다. 서로 다른 seed의 scene.xml을 동일 파일이라고 주장하지 않는다.

독립적인 촬영 전 contacts 재계산 라벨은 **1,463/1,464**, 확증은 **732/732** 일치했다.
탐색 r3/32201의 12.75초 한 표본은 촬영 전 zero, 촬영 후 partial이었다.
렌더 경로 `_sync_real_camera_mount`가 `mj_forward`를 부른다. [MuJoCo 공식 문서](https://mujoco.readthedocs.io/en/stable/programming/simulation.html#simulation-loop)는
`mj_step` 후 중간 접촉 값이 한 물리 timestep 오래될 수 있음을 설명한다. 이 경로가 차이를 만든 것으로 해석한다.
주 평가는 사전 구현대로 **촬영 후 labels.jsonl**을 쓴다. 촬영 전 contacts로 바꾸는 민감도 검사에서는
해당 탐색 에피소드는 촬영 전/후 각각 onset23/25, 지연2/0프레임(0.2/0.0초)이었고 정탐/오탐 수는 같았다.
확증 수치·지연은 전부 동일하다. 다음 자료 수집에서는 완전한 contact dump도 capture 직후 같은 상태로 저장해야 한다.
원본을 덮어쓰거나 이번 결과에 새 물리 실행을 섞지 않았다.

## 판정과 다음 토글 제안

- 자료 생성/짧은 RGB 배관: 완료. 빔의 고정 wrist 구간에서는 기존 거부 문제를 줄인 증거가 있지만 이탈확증은 로봇별2건뿐이다.
- 세 로봇 공통 안전 정지 감지기 또는 움직이는 공동 운반에 대한 채택: **not-ready**.
  r3 무관측 사례, partial→zero 사이 경보 의미, 이동/가림/조명 일반화가 남는다. 기본 legacy·S4 LLM 제어 경로는 유지한다.
- 다음 버전은 `grip_warning_v2=off`로 시각 변화 warning과 확정 이탈을 구분하고,
  `grip_anchor_observable_v2=off`로 관측 가능한 기준점 확보/unknown 처리를 별도 검증하는 방향을 제안한다.
  실제 카메라 배치·FOV·외관을 바꾸지 않으며 접촉 정답은 계속 평가에만 쓴다. 이번 후보 임계값은 사후 튜닝하지 않았다.

## 검증·TensorBoard

관련3파일 pytest35통과 후 후보 파일8통과(서로 겹치므로43개 고유 시험이라고 합산하지 않음).
검증 원본과 해시는 [preflight](preflight.json). 별도 물리 스모크0회, 본 묶음 외 추가 물리0회.

[TensorBoard 확증 + 같은 자료의 기존 CV](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline/true_positive_episodes%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline/actual_loss_episodes%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline/false_positive_hold_episodes%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline/actual_hold_episodes%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline/max_delay_sim_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result/wall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result/commands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result/model_calls%22%7D%5D&smoothing=0&runFilter=%5E1010-s4grip2/confirm-#timeseries) · [이벤트/HTTP/UI 확인](tensorboard-verification.json).
새 snapshot `1010-s4grip2`:8run,157scalar; native 화면에서 확증5run 선택,8개 pinned cards,
HParams case/outcome/policy/source_sha + model_calls 표시 확인(전역4,606개 group, Time Series만 확증 필터).
0회 모델의 응답시간은 측정 불가라 0으로 만들어 넣지 않았다. 기존 viewer PID52016과 다른 작업은 유지했다.
`1010-s4grip2-media`: 저장 자기 RGB 대표4영상(r1/r2 이탈, r3 조기경보/무관측) 등록,HTTP200·Range206 확인.
[미디어 해시](media-provenance-summary.json); JPEG61장@10fps이므로 영상6.1초, 첫~마지막 SIM 간격6.0초.

재현(물리 없이):
```sh
python3 -m scripts.evaluate_s4_grip_dataset --raw-root /Users/changmin/projects/ugrp/outputs/oracle-runs --split explore --output <new-explore-dir>
python3 -m scripts.evaluate_s4_grip_dataset --raw-root /Users/changmin/projects/ugrp/outputs/oracle-runs --split confirm --output <new-confirm-dir>
```
원본과 파생 뷰는 로컬/Oracle 보존이고 Git에는 작은 기록·해시·분석기만 보존한다. raw 전체의 GitHub 백업을 뜻하지 않는다.
PR #425 초안을 유지하며 병합은 감독이 결정한다.
