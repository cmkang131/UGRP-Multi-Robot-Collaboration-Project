# ACT15 — 초기 분포 공백 진단, DAgger 1회와 폐루프 재평가

초기 동작 공백은 고쳤지만 폐루프 성공 개선은 확인하지 못했다. 새 모델은 같은20 **0/20**, 새20 **0/20** 완료다.
`ready=false`, 기본 제어기 채택 없음. 한 로봇의 상자 근거리 staged grasp 결과이며 주행·놓기·E2E·실물 결과가 아니다.
이전 ACT14, DAgger 수집, 보조 시간 앙상블 시험을 합산하지 않았다.

|조건|N|접근|기능 정렬|집기|안정 들기|학생 완료|cap_end|HOST_ERROR|
|---|---:|---:|---:|---:|---:|---:|---:|---:|
|ACT14 p0 같은20|20|12|2|2|1|1|6|0|
|ACT14 p02 같은20|20|12|1|1|1|0|7|0|
|ACT15 같은20|20|13|2|2|0|0|8|0|
|ACT15 새20|20|12|1|0|0|0|7|0|

새 결과의 최초 거부 분포: same20: alignment_not_passed 11, approach_not_passed 7, lift_confirmation_not_passed 2; new20: alignment_not_passed 11, approach_not_passed 8, grasp_not_passed 1.
단계는 기존 ACT14 기능 관문 그대로이며 stable lift·낙하 없음·학생 done·비cap을 모두 만족해야 완료다.
고정 교사40/40은 [ACT11 기록](act11.md)이며 이번에 다시 잰 교사 성공률로 표현하지 않는다.
후보/실행·입력 프레임의 순차 통과·거부 수, 물체 이름/틈, 원본·해시·재현 명령은 [funnel](act15-funnel.json),
모든 완료/실패/중단/사전 거부는 [전체 기록](act15-summary.json)에 있다.

## 실패 진단

수정 전 거부표를 먼저 만들었다: [기존 거부표](act15-rejection-before.json).
정렬21, 접근16, 들기1이며 들기 통과 후 완료 없는 cap_end1은 따로다.
관측 접촉 이름·간격은 평가 근거이며 충돌 원인으로 확정하지 않는다.

[열린 고리 결과](act15-openloop.json)는 기존 val5, 1,811개 선택행에서 실제 실행 decode 후
교사 행동과 비교했다. 청크 horizon0–7과 단계별 분포를 모두 남겼다. 아래는 horizon0이다.

|모델·단계|행|휠 부호 불일치|펄스 MAE(ms)|PWM MAE|
|---|---:|---:|---:|---:|
|p0 접근|451|7.04%|12.44|21.79|
|p0 정렬|115|15.87%|8.39|22.76|
|p02 접근|451|9.26%|14.80|38.43|
|p02 정렬|115|15.22%|7.51|27.13|

낮은 train/val 손실 비율만으로 행동 일치를 보장하지 않는다. 특히 정렬에서 부호 오류가 이미 있다.
원본50개를 조사하니 시작/접기350행과 인계 전 접근102행이 선택에서 빠졌다.
첫 학습행은 스킬 시작 후0.7–4.9 SIM초인데 학생은0초부터 예측한다.
따라서 “열린 고리는 맞고 후반 compounding error만 발생”이라는 판정은 근거가 부족하다.

[정확 명령 재생·반사실적 라벨](act15-replay.json)은 p0/91420 실패, p0/91434 기존 성공,
p02/91420 실패의347/519/620행을 재생했다. 자기 RGB·발행 명령·clock이 원본과 정확히 같고
보이는 것만 아는 같은 ACT11 교사로 라벨했다. 교사 행동 실행0, invisible_measurements=0,
held_world_reads=0이다. 첫 휠 불일치는 셋 모두 절대SIM1.3초=스킬0초다.
p0/91420에서 교사는 정지/접기, 학생은 평균0.352875 전진·73.252ms 펄스였다.
정렬 전 접근 오차가 기존 val의 단계별95백분위를 처음 넘은 시각은 실패 둘2.0초,
기존 성공7.9초다. 이는 행동 차이의 기술 통계이고 통계적 상태 OOD 검출이나 단독 원인의 증명은 아니다.
기존 성공에서도 초기 차이가 있으므로 그 차이만으로 모든 실패를 설명하지 않는다.
[해당 자기 프레임과 해시](act15-divergence-frames.json), [몽타주](figures/act15-divergence.jpg).

## 표준 방법과 적용

[Zhao et al. 2023 ACT](https://arxiv.org/html/2304.13705v1)와
[공식 구현](https://github.com/tonyzhaozh/act/blob/main/imitate_episodes.py)을 확인했다.
ACT14 학습 청크8,10Hz와 실행 n_action_steps8,ensemble off는 길이·주기 불일치가 아니다.
원 ACT는50Hz/청크100, 측정 관절·4카메라이고 이 과제는 자기 명령과 자기 RGB 이력/10Hz다.
원 논문과 입력·주파수가 동일하다고 주장하지 않는다. 최종40회는 ACT14와 같은 **n8/ensemble off/CPU1thread**다.

[Ross et al. 2011 DAgger](https://proceedings.mlr.press/v15/ross11a/ross11a.pdf) Algorithm3에 따라
기존 p0 학생만 돌린 별도87020–87039 방문 상태를 전문가로 라벨하고 기존 자료와 합쳤다.
학생 방문 상태20회(수집 완료20,cap_end11,안정 들기1)는 최종 평가40회와 구분한다.
교사의 기억에는 실제 학생 발행값만 동기화했다. 교사 시간 기반 팔 시퀀스를 학생이 실행했다는
가정을 막기 위해 **첫 hover 전환까지만** 채택해6,161행을 추가했다. 이후 라벨은 버렸다.
연속 학생 방문 상태의 expert 표적이지 expert가 실제 그 청크를 실행한 반사실적 후속 궤적은 아니다.
교사 정답 보정·접촉·측정 관절은 학생 실행에 들어가지 않는다.

기록된 원래 교사 prefix를 포함하는 `include_initial_approach_v1`은 기본 off, 이 후보만 on이다.
수정 base50은train16,691/val1,847행, DAgger 합친 최종train22,852/val1,847행이다.
val은86865–86869 같은 원본5개지만 prefix36행을 추가했으므로 옛1,811행과 같은 선택행이 아니다.
학습에는86820–86864 및87020–87039만 썼고 평가91420–91439/91500–91519와 겹치지 않는다.
정규화는 고유 train 저장행만 사용했다. 282개 전달 파일과 모든 입력/발행 이력을 감사했다.
[data·감사·출처](act15-data.json), manifest SHA256 `314539e8d815eee17dcc8bbf488afaefca18e4fe6cb425ff5bd98b5dcd407b64`.

교사 흔들기9틱80/80과 회전 보정 on/off 동일 결과는 사용자 전달 감사이며 이번에 재계수하지 않았다.
[Laskey et al. 2017 DART](https://proceedings.mlr.press/v78/laskey17a/laskey17a.pdf)는 학생 오차에 맞춘
노이즈 분포를 최적화한다. 임의1–12틱 혼합을 정확한 DART로 부르지 않았다. 이번은 DAgger1회다.
prefix 추가와 DAgger를 함께 적용했으므로 둘의 개별 효과를 분리한 ablation은 없다.

## 학습·고정 평가와 별도 시험

훈련 소스1535c8a3e4e10184669304081aaaf7ce4eff3512, L4 g2-standard-4, seed20261015,
batch8, dropout0, balanced_bce_v1. smoke300→resume10,000이며 검증으로 체크포인트를 고르지 않고
고정 마지막 모델을 썼다. loss 0.148365, 재로딩 torch.equal 확인.
[학습 설정·명령·전체 보고서 해시](act15-training.json).
모델 SHA256 `d90a2b545709df6cd1a5972874db2e20c264007f9a798888f1bdccac22882ed1`.

최종 물리는 GCP1 n4-highcpu-64, 실행 소스686cccb6e31342a9edfadb30a8047ad57ceb9291,
장면/교사는 기존6f057f7e를 고정했다. 40회 전부 EXIT0·기록 회수·관문 재계수 완료다.
같은20 시작 자기 RGB·발행 이력·clock은 ACT14 p0와 모두 일치했고 새 첫 명령은20/20 정지다
([비교 원장](act15-initial-input-comparison.json)). 입력 감사 전부0, teacher_assisted=false,weld off다.
새 같은20 중앙은 기존3.5 기준을 넘었으므로 속도 관문 통과로 보고하지 않는다.
최종 같은20 wall/SIM 중앙 3.547, 새20 3.347.
계획 탐색 없는 ACT이며 setup은 기존400/2000회 계산 상한, 결과 cap은90 SIM초다.
wall watchdog은 HOST_ERROR 자원 상한이고 행동 선택에 쓰이지 않는다.
같은 장면16동시 CPU속도는 ACT14 실측 프로필을 재사용했고 최대16으로 제한했다.

보조 시험은 같은 가중치의 n1/시간 앙상블m=.01이다. m은 ACT 공개 구현 값이다.
L4 batch1·결정적 연산을 쓴 private inference의 같은 입력10회/동시16회 출력이 바이트 일치했다.
CUDA 결정성은 [PyTorch 문서](https://docs.pytorch.org/docs/stable/notes/randomness.html),
cuBLAS `:4096:8`은 [NVIDIA 재현성 문서](https://docs.nvidia.com/cuda/cublas/index.html#results-reproducibility)를 따랐다.
완료4회는cap_end4·안정 들기1·학생 완료0, 후속8회는 느린 보조 프로필을 종료하면서 감독 중단했다.
이12회는 최종40회 성능에 합산하지 않는다. 최종 모델은 바꾸지 않았다.

원본 해시를 확인하고 압축 후 재해제 SHA를 검증했으며 원본 경로를 유지했다.
[raw 검증](act15-raw-verification.json)59회와 data 기록의 수집20회를 보존했다.
OpenGL 초기화/빈 추론 통계 진단 HOST_ERROR2와 frozen import 초기화 HOST_ERROR4도 따로 기록했다.
후자는 학생 명령0이며686에서 고친 뒤 최종40회를 새로 쟀다. 저장공간 사전 거부4 및 미추적 영상으로
소스 청결 검사에 막힌 사전 제출1은 시뮬레이션이 만들어지지 않았고 결과 분모에 넣지 않았다.

## 영상·산출물·남은 한계

40회×6장=240 슬롯을 처음·중간·끝에 고르게 직접 확인했다. 프레임 최대 간격은60 SIM초 이하다.
첫4회 첫30 SIM초6장씩도 별도로 봤다. [검토 시각·해시·관측](act15-frame-review.json).
모달 실패 단계의 같은91420을 대표로 보존했다. 영상에서 접근 후 목표가 화면 밖으로 빠진다.
이 영상은 실패 증거이며 전체 실패의 단일 원인을 증명하지 않는다.
[자기 RGB4배속](videos/act15-91420-4x.mp4),22.5초/900프레임/169,401bytes,
SHA256 `e9a95fd808c256f12d37ffa5b753a29bf8e441201340100f4b5ca3d2bb3a34fd`.
640×480/10Hz 원본90초와 milestone raw 복제는GCP에 있다([원본 위치·해시](act15-video.json)).

선택 모델은 [GitHub Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/download/models-20261015-act15-1535c8a3/grasp-act15-dagger1-step10000-1535c8a3.zip)에 actor/config/adapter/출처/의존성/결과와 묶었다.
실제 재다운로드 뒤 ZIP·내부 전체파일 SHA256과 GCP CPU 모델 로딩을 확인했다
([검증](act15-model-release-verification.json), [레지스트리](../../configs/model_artifacts.json)).
원시 시뮬레이션은 GCP 영속 디스크에 남아 있고 독립 디스크 전체 백업은 미완료다.
Mac에는 요약·몽타주·실패 프레임과 배포 검증용 모델 ZIP만 회수했다. 가중치는 Git 이력에 넣지 않았다.

L4는 학습0.788913h+보조 추론0.526444h=**1.315356h**, 기준$0.907714/h로
**추정$1.193967**이다. 준비·전송 시간을 포함한 VM 창이며 디스크/네트워크/세금/크레딧/실청구는 제외한다.
ACT15 두 창 모두종료 `TERMINATED`,8h STOP·idle20분 유지. 이후 같은 VM은13:38:58Z에
다른 simalt2 작업으로 다시 시작돼 최종 조회는 RUNNING이다. ACT15 GPU/학습 프로세스0을 확인했고 다른 작업은 정지하지 않았다. [종료·비용·예산 장치 확인](act15-resource-cost.json).
최신 비용 알림의 순비용0은 지연 집계값이고 크레딧 잔액이나 실제 청구0의 증거가 아니다.

이번 한 라운드는 성공을 해결하지 못했다. 초기 행동 공백을 고친 사실과 파지 성공은 별개다.
다음 학습의 우선 대상은 실제 학생 상태에서의 정렬·목표 재관측 및 파지/완료 라벨 다양성이다.
val5와 한 결합 변경만으로 방법별 효과·일반화·교사 관문 충족을 확정하지 않는다.
관련 Mac 단위검사32통과/1skip(torch 미설치), 모델 레지스트리 검사10통과.
독립 병합 검토를 수행하지 않았고 기본 채택·병합은 하지 않았다.
