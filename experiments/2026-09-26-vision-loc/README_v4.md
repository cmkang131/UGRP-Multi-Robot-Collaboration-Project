# VIS4: 태그 없는 위치 추정의 dev 분해·운동 예측 수정

브랜치 `codex/vision-loc-v4`, 시작 HEAD `1aa8f0c7e78dd3395cd04bfa04c5d9b53c5e1e48`
(PR #233과 일치). **사용자 요청으로 git 커밋·push·PR 생성·병합을 하지 않는다.**
소스 위치는 `harness/`가 아니라 이 실험 디렉터리다. 새 산출물은
이 worktree `outputs/vision-loc-v4/`에만 둔다. 기존 primary의 원본은 읽기만 한다.

## 선택 전 고정

`dev_plan_v4.json` SHA256 `ca9edfe79423bd745a5659f1517b5f66b4908013adae0d24ce35e88c88ce591e`.
PF 변형을 실행하기 전에 저장했다. fit 6회(s909/910/911/941/942/943),
validation 3회(s945/946/947)이며 새 적합·선택에는 기존 train/test를 사용하지 않는다.
기존 train에서 학습된 분할 모델과 고정 카메라 보정은 그대로 재사용한다.
전체 dev 9회 20,433프레임, 문 근처·운반 1,347프레임이다.

- b0: 기존 VIS3 a1의 완전한 비전/오라클 추정을 해시와 함께 재사용.
- x1: 명령 만료 경계에서 적분을 나누고 1차 지연 속도의 구간 적분을 해석적으로 계산.
  yaw는 구간 중간값을 써서 베이스 좌표 속도를 지도 좌표 이동으로 바꾼다.
  잡음 계수는 유지하지만 표준편차의 속도 항은 구간 평균 속도를 쓰며, 경계 분할로
  난수 소비 순서도 달라진다. "정확 적분"은 결정론적 1차 속도 적분을 뜻한다.
  같은 seed를 쓰더라도 두 필터의 개별 난수 표본까지 일치하는 비교는 아니다.
- m1: x1 + fit dev에서만 구한 unloaded/loaded 이동 배율·지연 계수.
  fine 프로필의 학습 계수·분할 네트워크·지도·카메라 보정·입자 수(2,000)는 유지.

선택은 validation과 all-dev 모두에서 문 위치 p90이 3 mm 이상 좋아지고,
횡 p99/yaw/전체 p90/소실 프레임의 정해 둔 악화 한도를 지킬 때만 허용한다.
오라클 문 p90도 5 mm 넘게 악화되면 기각한다. 아무도 만족하지 못하면 b0 유지.
부분 결과로 선택하지 않는다. 실행 전 소스·설정 해시는 comparison/source_freeze.json에 있다.

## 원인 분해 (dev만)

`diagnose_v4.py`, `analyze_motion_v4.py`는 교사 정답을 읽는 **오프라인 분석기**다.
`vision_motion.py`와 PF의 런타임에는 정답·접촉·측정 관절을 전달하지 않는다.

1. **편향 재현:** door_loaded 비전 dx 평균 **+2.119 cm**, body-forward **+2.121 cm**,
   오라클 dx **+1.417 cm**. 비전 위치 p90 **6.452 cm**, 횡 p99 **4.778 cm**,
   yaw p90 **2.361°**. 오라클 위치 p90 **5.155 cm**, 횡 p99 **15.398 cm**.
   이는 user가 제시한 test 사후 +2.4 cm와 별개의 dev 측정이다.
2. **관측 시각:** 20,433프레임 모두 input↔eval↔label 시각 일치, 라벨의 RGB 해시 일치,
   라벨 base_gt↔frame 평가 XY 차이 0. 같은 시각 frame→command 순서는 자기 팔 명령과
   불일치 0건, command→frame으로 바꾸면 **3,723건**. RGB 해시는 두 metadata의
   기록값을 대조한 것이며 여기서 모든 JPEG 바이트를 다시 해시한 것은 아니다.
   영상 timestamp 이동은 하지 않는다.
3. **명령·짐 상태:** 정적 gain만 일정 비율 잘못된 경우로 단정할 수 없다.
   loaded fit: 기존 gain 행 배율 [**0.999901, 1.000866, 1.0**], tau **0.8 s**,
   추가 순수 delay **0 s**. loaded yaw는 유효 자극 0개여서 적합하지 않고 기존 값을 유지한다.
   unloaded fit: 배율 [**1.011319, 1.147554, 0.5**], tau **0.8 s**(기존 0.3), delay **0 s**.
   unloaded yaw 배율은 탐색 하한에 닿았으므로 일반화/식별성 한계를 가진다.
   검증 dev moving 구간의 기존 loaded 전진 속도 잔차는 회차 평균 **+0.000318 m/s**,
   적합 뒤 **+0.000314 m/s**다. 따라서 loaded 고정 gain/순수 delay 보정만으로
   수 cm의 위치 편향이 사라진다는 근거는 없다.
   validation 3회에서 on/off 변경 후 1초 구간을 따로 보면, unloaded 출발 전진
   속도 잔차(회차 평균)는 **+2.391→+0.700 cm/s**로 줄지만 정지는
   **+0.207→+0.762 cm/s**로 늘어난다. unloaded는 기존에 별도 stop tau가 없어
   적합된 0.8 s를 정지에도 쓴다. 출발·정지 동특성의 상충이며, 이번 고정 비교에서
   stop tau를 사후 추가 적합하지 않았다. 이는 속도 모델 잔차이고 PF 위치 오차는 아니다.
   추가 평가 전용 짐 감사(`cargo_state_v4.json`)에서 own-loaded 문 구간 1,347장의
   상자 중심 z는 **0.1519–0.1931 m**였다. 이 구간에서 짐이 바닥에 남았는데
   loaded로 잘못 분류된 경우를 주원인으로 볼 증거는 약하다. 접촉력/실제 파지의
   별도 판정은 아니며, 이 정답 상자 위치는 런타임이나 계수 선택에 쓰지 않았다.
4. **명령 만료·적분:** 기존 M1은 dt 끝의 속도로 전체 dt를 이동하고 명령 만료가
   dt 중간에 있어도 나누지 않는다. 최장 한 step만큼 명령을 더 적용할 수 있다.
   dev에서 다음 명령 전에 만료가 오는 기회는 **395회/34,714 wheel event**다.
   s909/s941은 각각 7,183회 명령 중 만료 기회 0개라, 이 둘의 끼임을 만료 처리만으로
   고칠 수 없다. 교사 stationary 구간은 별도 통계로 남기고 정상 운동 적합에서 제외한다.
5. **우도 비대칭·약한 정보:** 매 10번째 settled door_loaded 프레임 96장을 GT 중심에서
   x만 ±10 cm, 1 cm 간격으로 탐색했다. 비전/오라클 모두 **45/96장**에서 우도 범위가
   0.001 미만으로 사실상 평평했다. 최댓값 구간이 탐색 경계에 닿는 것은 비전 **60/96**,
   오라클 **54/96**. 경계에 닿지 않는 최대점의 평균은 각각 **+1.472/+1.250 cm**다.
   교사 라벨에도 남는 방향 비대칭이 있으므로 인식만의 문제가 아니다. 다만 고정
   y/yaw·카메라 보정 조건의 1D 진단이어서 전체 자세의 유일한 원인이나 정확한
   물리 지연을 식별한 것으로 해석하지 않는다. camera extrinsic 오차도 배제하지 못했다.
6. **카메라 보정 잔차:** 추가 offline dev 점검(`analyze_camera_v4.py`)에서 settled
   door_loaded 922장의 실제 카메라 원점과 고정 train 보정 모델 차이는 전후 평균
   **+1.064 mm**, 절댓값 p90 **1.154 mm**였다. pitch 잔차 절댓값 p90은 **0.01775°**,
   azimuth는 **0.00619°**다. 큰 고정 카메라 보정 오차를 주원인으로 볼 증거는 약하다.
   이 값으로 런타임 보정을 적합하거나 카메라/FOV를 바꾸지는 않았다.

자기 명령으로 inferred-loaded가 바뀌어도 VIS3는 입자별 slip scale을 계속 가진다.
loaded에서 영상의 전진 방향 정보가 약하면 이전 scale과 편향이 남을 수 있다.
새 추정에는 `diag.scale_mean`, `diag.command_velocity`, `diag.motion_profile`을 기록한다.
scale 재초기화·stuck/recovery는 이번 세 후보에 추가하지 않았다. 기존 VIS3 실험의
상호작용 문제를 완주 전 임의 조합으로 바꾸지 않는다.

## 비교 결과

**고정 규칙 판정: x1/m1 모두 기각, b0 유지. VIS4 개선 후보 채택 없음.**
선택·원 수치는 `outputs/vision-loc-v4/comparison/selection.json`, 방향 편향은
`outputs/vision-loc-v4/report.json`에 있다. x1/m1 각각 9회·20,433프레임,
비전/오라클 동시 재생을 끝냈으며 중단·누락 회차는 없다. b0는 재실행이 아니라
기존 완전 기록 재사용이다. 원본 meta 18개를 새 조건과 비교해 설정·seed·지도·
카메라·checkpoint·M1·관측 경로 불일치 0건을 확인했다(`baseline_meta_audit.json`).

전체 dev 문/운반 1,347프레임(6회에서 관측됨; 도달하지 못한 3회도 전체 지표에 포함):

| 후보 | 비전 위치 p90 cm | 오라클 위치 p90 cm | 비전 횡 p99 cm | 비전 yaw p90 ° | 비전 전진 평균 cm |
|---|---:|---:|---:|---:|---:|
| b0 기준선 | 6.45 | 5.16 | 4.78 | 2.3605 | +2.121 |
| x1 적분/만료 수정 | 7.35 | 4.50 | 18.42 | 2.3523 | +3.890 |
| m1 dev 운동 적합 | 339.39 | 4.51 | 139.53 | 88.3256 | −53.282 |

적합에 쓰지 않은 validation 3회·6,197프레임, 문/운반 713프레임:

| 후보 | 비전 문 위치 p90 cm | 오라클 문 위치 p90 cm | 비전 횡 p99 cm | 비전 yaw p90 ° | 전체 위치 p90 m | 소실 프레임/6,197 |
|---|---:|---:|---:|---:|---:|---:|
| b0 | 5.92 | 13.38 | 4.31 | 2.6152 | 0.6235 | 858 |
| x1 | 21.96 | 8.16 | 18.80 | 3.4926 | 0.8077 | 1,251 |
| m1 | 359.27 | 11.64 | 140.50 | 90.0583 | 3.0738 | 1,651 |

전체 dev 비전 위치 p90/소실은 b0 **1.5118 m/5,279**, x1 **1.3518 m/4,500**,
m1 **2.2691 m/5,642**(각 20,433프레임)이다. x1의 전체 지표 일부 개선도
validation 악화와 문 꼬리 오차를 상쇄하지 못하므로 채택하지 않는다.

문 오라클 위치 p90의 개선과 전진 편향 해소는 다른 결과다. 오라클 전진 평균도
b0 **+1.419 cm**, x1 **+1.615 cm**, m1 **+2.307 cm**로 개선되지 않았다.
실제 인식 s945의 문 위치 p90은 b0 **4.71 cm** → x1 **32.39 cm** → m1
**3.8316 m**다. x1은 문 첫 프레임에 이미 35.94 cm 오차가 있었고 이후 줄었다
(`posthoc_x1_s945.json`). m1은 큰 위치·방향 소실을 일으켰다. 일정한 +x bias만
빼는 보정으로 다룰 문제가 아니며, 오라클 개선을 학생 개선으로 보고하지 않는다.

새 수정은 **기본 OFF 옵션**으로 보존한다. 다음 dev 계획의 대상은 출발/정지 lag의
분리 적합, 약한 영상 정보 구간의 scale/자세 posterior 유지, PF seed 반복에 따른
민감도다. 이번 결과를 보고 계수를 재적합하거나 새 변형을 추가하지 않았다.
각 회차의 PF seed는 한 개뿐이다. 추가 seed 반복으로 확률적 필터의 분산을
분리하는 비교는 새 dev 계획이 필요하며 이번 고정 코호트에는 추가하지 않는다.

## 추가 요청: VISW σ 보정

[sigma_results_v4.md](sigma_results_v4.md)에 정의·원인·설정·전 수치·한계를 기록했다.
`sigma_plan_v4.json`을 추가 비교 전에 고정했고 원래 운동 선택 규칙/판정은 유지했다.

- VISW 2,375장: error>3σ **19.03%**, 파지 300장은 **100%**. 최근 적용 관측에서
  0.25초 이내인 파지 215장도 전부 3σ 밖이라 단순 관측 부재만의 문제가 아니다.
- 구역 A `pose_uncertain` 8건 모두 **yaw σ>3°**, XY σ는 7 cm 상한 이내다.
  구역 A yaw 실제 오차 p90 **0.558°**, σ p90 **3.527°**. XY와 yaw를 구분해야 한다.
- 보고 공분산 보정기를 기본 OFF로 추가하고 full covariance/관측 시각 저장을 보강했다.
  자기 명령 상태와 관측 나이만 받으며 입자·난수·위치/yaw 평균은 바꾸지 않는다.
- u1 전역 배율과 u2 상태/관측 나이 보정은 **둘 다 기각, u0 유지**다.
  validation 95% 포함률은 61.55%→100%/80.17%, σ 중앙값 3.56→65.97/8.53 cm.
  u2의 VISW fit 포함률 95.07%·무관측 분산 감소 0건은 독립 성공 근거가 아니다.
- 기존 full covariance가 없으므로 XY NEES는 등방 근사로만 보고했다. 새 기록에는
  정확한 NEES 계산을 위한 covariance를 남긴다. yaw 보정과 VISW worker 통합은 남았다.
- 새 native TensorBoard snapshot `0927-vis4-sigma`: **21 runs·50,295 scalar·21 HParams**
  실제 재로딩 대조 일치. viewer 화면 확인은 아래 sandbox 제한으로 미완료다.

## 게이트·새 test 초안

`gates_v4.md`와 계산 함수 `gates_v4.py`에 문 폭·실제 드라이버 외형·슬롯 크기·경로
여유를 연결했다. 기본 경로 margin 2 cm는 전역 5 cm 위치 오차를 지지하지 않는다.
문 횡 p99 5 cm + yaw p99 3° + 결합 오차, 슬롯 위치 p99 1 cm,
경로 여유≥6 cm에서 위치 p99 3 cm + 결합 오차 기준을 제안한다.
tracking/형상/배치 오차 예산은 설계 가정이고 실측 검증이 남았다.

`prereg_v4_DRAFT.json`은 execution_enabled=false, source_commit=null이다.
dev fallback b0의 해시를 기록했지만 승격 권고는 NO_GO다. 개선된 새 학생이 없으며,
새 test로 진행하라는 뜻이 아니다. formal v4 채점기·정적 경로 감사가 남았다.
관련 pytest는 아래의 사용자 잠금 예외를 적용해 완료했다.
`episodes_v4_DRAFT.json`의 primary seed는 **1002,1008,1009,1010,1011,1015,1021,1023**,
reserve는 **1024,1025,1037,1038**이다. 이전 31회 metadata와 seed·두 경로 쌍이 다르다.
렌더 후에는 old/new 모든 쌍의 JPEG/1 mm·0.1°/정렬 궤적 감사를 먼저 해야 한다.
기존 test 좌표·추정·점수를 읽어 선택하지 않았다. renderer는 코디네이터만 실행한다.
필요 목록과 명령은 `render_requests_v4.md`에 있으며, 추가 dev 렌더는 필요 없다.

## 검증·저장·제약

최종 증거 목록은 `outputs/vision-loc-v4/artifact_manifest_sigma.json`이다.
이전 motion 완료 기록/manifest는 당시 상태 그대로 보존하고, 이후 σ 확장과 테스트
완료는 새 기록으로 추가했다. 원본 108개·기존 산출물 91개·σ 입력 42개 재해시
불일치 0건(`integrity_after_sigma.json`). 새 test 초안의 게이트/seed는 아직 미커밋이다.

- 완료 후 입력/cache·기준선 추정/meta **108개 파일**의 SHA256을 재대조했고 불일치 0건이다.
  재생 소스 12개·운동 적합 파일·선택 규칙 해시도 전 코호트 동안 유지됐다.
  `completion_verification.json`에 범위와 실패 0건을 남겼다. 모든 raw JPEG를 다시
  해시했다는 뜻은 아니며 입력 inventory의 최초 캡처는 재생 시작 후였다.
- `tests/test_vision_loc_v4.py`를 CI `tests/test_vision_loc*.py` 수집에 포함했다.
  만료/정확 적분/분할 불변성/회전/지연 인과성/명령 순서/own-load/fine/legacy RNG/
  dev 경계/선택 규칙/기하 예산/새 split/덮어쓰기 방지를 다룬다.
- 기존 잠금/sandbox로 중단됐던 두 시도는 `pytest_attempt{,_2}.log`에 보존했다.
  이후 사용자·코디네이터가 이 작업의 **물리/모델 호출 없는 오프라인 테스트는
  잠금 없이 허용**한다고 명시하여 기존 suite **101 passed, 1 skipped (28.55 s)**,
  최종 **132 passed, 1 skipped (29.19 s)**를 확인했다.
  건너뛴 1개는 torch가 없어 실행하지 못한 선택적 분할 모델 shape 검사다.
  `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`로 실행했고 임시 폴더는 삭제했다.
  로그는 `pytest_authorized_offline.log`, `pytest_sigma_precompare.log`, `pytest_sigma_final.log`다.
  로컬 테스트이며 GitHub CI 실행·통과를 뜻하지 않는다.

  ```sh
  OMP_NUM_THREADS=1 /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python -m pytest -q \
    --basetemp=./.pytest_tmp tests/test_vision_loc.py tests/test_vision_loc_v4.py \
    tests/test_vision_loc_sigma_v4.py tests/test_markerless_probe.py
  # 종료 후 .pytest_tmp 삭제 (이 작업에서는 finally 블록으로 수행)
  ```
- git fetch는 sandbox의 Git 메타데이터 쓰기 제한으로 실패했다. GitHub connector로
  저장소의 현재 정식 이름 `cmkang131/UGRP-Multi-Robot-Collaboration-Project`와
  PR #233 HEAD 일치를 확인했다. origin URL을 바꾸지 않았다. 공용 main도 바꾸지 않았다.
- 관련 PR 댓글은 connector가 승인을 요구하고 approval policy가 never여서 게시되지 않았다.
  위 기록이 로컬 작업 공유 자료다. Google Drive를 사용하지 않는다.
- TensorBoard 스냅샷 `outputs/vision-loc-v4/tensorboard/0927-vis4-dev`: **12 runs,
  scalar 344개, HParams 12개 모두 실제 로딩·원 수치 대조 일치**. 기존 스냅샷은 보존했다.
  pin·표시 열·전체 URL은 `outputs/vision-loc-v4/tensorboard-view.json`에 있다.
  [뷰어 준비 주소](http://127.0.0.1:6016/)는 현재 서비스 중임을 뜻하지 않는다.
  `ugrp_session`의 `/bin/ps` 소유 확인이 sandbox에서 거부돼 뷰어 실행/화면 확인은
  미완료다(`tensorboard_start.log`, `tensorboard_display_attempt.json`). 정리 중 SIGKILL
  권한 오류도 기록되었지만 wrapper의 `child.wait()`가 반환하여 실행기는 종료됐다.
  코디네이터 환경에서 native viewer 실행과 실제 pin/HParams 화면 확인이 남았다.
  사용자 출력 위치 제약과 sandbox 때문에 primary 공유 root·공용 view 설정을
  바꾸지 않았다. 새 영상 0개이며 기존 영상도 수정하지 않았다.
- 오프라인 정확도 비교이며 wall 시간 속도 비교가 아니다. 새 모델/API 호출·실제 명령 발행 0.
  원본과 새 결과는 로컬 보관이며 원격 백업·독립 test·폐루프/실물 검증을 뜻하지 않는다.
