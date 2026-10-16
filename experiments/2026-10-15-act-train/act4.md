# ACT4 — 학생 1차 실패 측정과 기본 off 수정 후보

2026-10-15, PR #504 / `claude/act-train`. 실패 모델·실행 소스는
`f609979cd4e0b7174f999986408401817a5c991a`다. 측정 중 운영 기록과 main을 합친
`4e6b548d1980b02ca7fe35c21c8e02b8eb62f83b`가 공용 worktree에 반영되었으며,
ACT 학습·추론 파일은 실패 SHA와 같음을 확인했다. 그 위에 이번 수정 묶음을 올린다.

**판정: 종료 학습의 실패는 확인, 접근·정렬 실패의 근본 원인은 미확정. 전체 측정은 미완료이며
후보 실행은 아직 승인 대기다.** [짧은 요약](act4-summary.json),
[상세 수치·시점별 진단·원본 SHA-256](act4-measurements.json).
Mac 물리·렌더·학습과 원격 작업 실행은 0회다. 회수 자료를 먼저 읽고 CPU 5배치(17입력)를
측정한 뒤 논문·공식 구현을 조사하고 아래 한 묶음을 수정했다.

## 1. 회수 범위와 보류 5개 행동 오차

운영 원본은 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/act-main-f609979c-ops/`,
중단 원장은 같은 상위 폴더의 `stop-act-main-f609979c-20261015.json`이다.
50에피소드·17,851행(train45 / 16,018행, 보류5 / 1,833행)과 최종 loss 0.104448은
[운영 기록](operations-f609979c.md)에 연결한다. 기존 HOST_ERROR와 실패·미제출 9건을
포함한 전체 운영 결과는 [기존 종합 JSON](operations-f609979c-summary.json)에 보존했다.
이번 작업에서 추가된 물리 실패나 학습 HOST_ERROR는 없다.

지정 회수 폴더에는 보류 평가 `summary.json`/`aggregate.json`이 있지만
`offline-main/predictions.jsonl`은 없다. 로컬 교사 원본·변환 텐서는 86000·86001만 발견했다.
보류 86045–86049 텐서·시점별 예측은 미회수다. 전체 원본을 임의로 다운로드하거나 VM을 켜지 않았다.
따라서 아래는 **저장된 운영 평가 요약을 재독해한 값**이며, 이번에 5개를 다시 추론한 결과가 아니다.

| 보류 seed | grasp 행 | 바퀴 MAE | release 행 | 바퀴 MAE |
|---|---:|---:|---:|---:|
| 86045 | 269 | 0.032964 | 87 | 0.039788 |
| 86046 | 265 | 0.030917 | 87 | 0.026903 |
| 86047 | 287 | 0.041918 | 87 | 0.032316 |
| 86048 | 290 | 0.026440 | 87 | 0.032837 |
| 86049 | 287 | 0.035673 | 87 | 0.041813 |
| 행수 가중 합계 | 1,398 | 0.033617 | 435 | 0.034731 |

바퀴 단위는 발행 명령의 정규화 출력이다. 합계 PWM MAE는 grasp 21.843 / release 21.826 pulse,
펄스 길이 MAE는 0.005057 / 0.003754초다. 각각 unique timestep의 첫 행동이며,
겹치는 chunk 전체 11,044/3,340행과 섞지 않았다.
**보류의 시점별 MAE·회전/옆 이동 부호 일치율·done 점수 분포는 원본 부재로 미측정**이다.

새 `scripts/analyze_grasp_act_predictions.py`는 저장 예측만 읽어 이를 계산한다.
회전/옆 이동은 바퀴별 `wheel × pulse_width / 0.1s`를 역혼합한 발행 명령 방향이며
실측 이동 방향이 아니다. 정지 표적은 일치율 분모에서 빼고 그 수를 따로 기록한다.
raw/실행 투영 후, 첫 행동/각 horizon/전체 horizon, 에피소드/스킬을 분리한다.
중복 ID나 보류 행 누락을 거부하고, 데이터 metadata가 있으면 시각·스킬 해시도 대조한다.

## 2. 입력·정규화·chunk와 91100

- checkpoint `model.safetensors` SHA-256:
  `9f5e469439e1ea8bc7ada73dc558b6f5e7aa48edf71cc416b64b9f7b6929576a`.
- 데이터 manifest: `da651587d3cbe51f418f63fda55642b53e985a1fe1551db98909517065ba058b`.
  adapter 안 통계를 직렬화한 SHA는 기록된 normalization
  `b7a0b271ba89461e0b5cc594a34821e068326102cc04b5e98c536bfb4d130192`와 일치한다.
- 86000·86001의 텐서·이미지·metadata·RGB 출처 **8/8 파일**이 전체 데이터 manifest와 일치한다.
  719개 local 행의 상태 벡터를 원본에서 다시 계산해 일치했고, 처음·중간·끝 6개 입력의
  학습/추론 이미지 및 정규화 상태가 각각 배열 단위로 일치했다.
- 이미지: JPEG 640×480 → PIL RGB(채널 BGR 아님) → bilinear 320×240 →
  `[5.2초, 1.5초; 0.5초, 현재]`의 2×2 배치, CHW 3×480×640.
  `/255`, ImageNet mean `[.485,.456,.406]` / std `[.229,.224,.225]`를 한 번 적용한다.
- 상태 252차원: 자기 발행 명령 16×14, skill4·kind9·role8·destination5, 명령 기반 clock2.
  바퀴는 정규화 속도, pulse 길이는 `/0.15s`, PWM은 `(pulse−1500)/1000`,
  명령 나이는 최대5.2초로 clip 후 `/5.2`, clock은 최대120초로 clip 후 `/120`이다.
  범주 one-hot은 그대로, 연속 성분만 train 통계로 표준화한다. 관절 측정·물체 정답은 없다.
- 교사/학생 모두 자기 명령 16개를 사용하며 충분히 지난 시점의 나이는 1.6…0.1초다.
  기록 주기는 10Hz; 91100 실측 간격은 0.099999999998–0.100000000000초다.
- 기존 `predict_action_chunk` + 외부 `ChunkExecutor`는 chunk8을 모두 실행한다.
  `n_action_steps=8`, temporal ensembling 없음: 900 ticks / 실제 추론113회,
  관측을 반영하는 간격0.8 SIM초. 최초 chunk는 표적이 중앙에 있어도 회전 성분이 음수다.
  이것만으로 교사의 같은 장면 정답과 반대였다고 단정할 수 없다.

91100 raw의 입력900행·명령900행은 회수됐지만 dense RGB 디렉터리는 비어 있다.
대표 프레임 0·18·36·53.9·71.9·89.9 SIM초 **6장**을 직접 보았고, 오른쪽 끝으로
밀린 상자가 끝까지 복구되지 않은 것을 확인했다. 90초 실패0/1, 안정 들기0초,
release 미진입, 잔여9개 미제출을 그대로 유지한다.

대표 0초 프레임의 SHA를 입력 참조와 확인하고 고정 체크포인트를 CPU로 재추론했다.
첫8명령(0–0.7 SIM초)의 실행 투영 결과는 저장 명령과 최대차 **2.843e−7**,
PWM 차이 **0 pulse**다. 가중치/초기 입력 경로 불일치의 증거는 없다.
이후 몇 초의 RGB 이력은 없어 출력 재추론하지 않았다.

분포는 같다고 확정할 수 없다. 학생 시작의 반복 패딩 명령 나이는0이며,
전체 train 정규화 기준 가장 큰 절댓값은24.90 표준편차(명령 나이 성분)다.
회수된 교사 local 첫 행은0.7/1.0초부터이고, 같은 초기화의 비local 교사0초도 같은
24.90 값을 보인다. 즉 데이터 통계 오류가 아니라 **local 구간 선택에 따른 초기 분포 차이 후보**다.
이 작은 표본만으로 normalization을 바꾸거나 초기 명령을 꾸며 넣지 않았다.

같은 시나리오·cyan인86000 local 첫 영상의 상자 중심x/폭은0.225/0.098,
91100 시작은0.461/0.114다(화면 너비로 정규화, 가장 큰 색 성분). 동일 관측이 아니다.
교사가 정확히91100의 관측에서 낸 반사실 행동은 저장되어 있지 않아 **미확인**이다.
회수된 학습 입력16개(각 시연 첫6개 간격 표본과 grasp/release 마지막행)를 같은 모델로 비교했다:
바퀴 MAE0.08346, PWM19.48, 유효 forward 부호12/12·옆 이동7/7·회전7/7.
종료행4개를 의도적으로 포함한 편향된 진단 표본으로, 보류 정확도나 전체 성능으로 쓰지 않는다.
각 시점의 MAE·원시 예측은 상세 JSON과 로컬 `cpu-probes.json`에 있다.

## 3. done 라벨과 수정 근거

| split/스킬 | 양성/전체 | 비율 |
|---|---:|---:|
| train grasp | 45/12,103 | 0.372% |
| train release | 45/3,915 | 1.149% |
| 보류 grasp | 5/1,398 | 0.358% |
| 보류 release | 5/435 | 1.149% |

라벨은 기존 `last_local_row_v1`: 성공 시연의 스킬별 마지막 local 행1개다.
기존 ACT는14개 출력 모두 표준화 후 동일 L1로 평균하며 KL×10을 더한다.
별도 양성 가중은 없다. done 평균0.00561868 / std0.07474697로 정규화하지만
L1의 조건부 중앙값 성질은 그대로라 희소 이진 표적을0에 붙일 수 있다.
**done은 기존 모델에서 확률이 아닌 무제약 회귀값**이고 실행 임계값은0.65다.

보류 검출은 grasp0/5·release0/5, 예측양성0이다. 추가 CPU 진단에서 학습 종료행도0/4,
종료행 점수 범위−0.001175…0.000113, 16개 전체−0.002582…0.002226이었다.
낮은 손실과 미검출이 양립하는 실제 근거다. 종료 미검출을 접근 실패의 유일한 원인으로
보고하지 않으며, 보류 분포를 보지 못한 상태에서 임계값을 낮추지 않는다.

## 4. 시연 다양성

원본이 있는86000·86001 **2/50 시연**에서만 색 기반 검사를 했다.
가장 큰 표적 색 성분 중심이화면15% 밖이거나20 pixel 미만인 구간을 표시하고,
중심20–80% 안의 가시 프레임5개 연속을 복귀로 정의했다.
이 proxy에서는86000 **1구간**(절대 SIM2.4→6.2초),86001 **0구간**이다.
86000의2.4·4.4·6.2초3장을 직접 보니 왼쪽 가장자리 근처에서 안쪽으로 돌아왔다.
이는 **완전 시야 이탈 뒤 회복**이나 오른쪽 이탈 복구 시연1개를 뜻하지 않는다.
두 시연의 말기 비가시는 정상 파지 blind 구간과 분리해야 하므로 복구 실패로 세지 않았다.
나머지48개와 전체 완전 이탈→회복 수는 **미확인**이다.

DART식 추가 기록은 전체 회복 수·학생 오차 공분산을 확인한 뒤 정한다.
현재 교사 구현은 이 브랜치에 없고 노이즈 크기 근거도 부족하므로 임의 노이즈 경로와
추가 시연 실행을 만들지 않았다. 별도 DART 실행 큐도 만들지 않았으며 후속 큐에
`implemented=false`, `approved=false`와 재검토 조건을 남긴다.

## 5. 한 묶음 수정 — 기본 off

1. `--done-loss balanced_bce_v1`: upstream ACT의 **동일 forward와 KL**을 그대로 쓰고,
   마지막 채널 L1만 제거해 class-balanced BCE를 더한다. unique train 행에서 스킬별
   양성비율p를 구하고 양성0.5/p·음성0.5/(1−p), 기본 BCE 계수1을 쓴다.
   실제 행동13채널의 기존 L1 스케일은 유지한다. Padding은 두 손실 모두 제외한다.
   기준선은 `legacy_l1` 기본값으로 보존한다. 추가 phase 진행도 회귀는 넣지 않았다.
2. 새 후보는 마지막 채널을 logit으로 학습하고 배포 시 sigmoid한다. adapter v2의
   `done_mode`와 resume/smoke provenance로 명시한다. 기존 v1 가중치는 기존 역정규화로
   읽고 재해석하지 않는다. BCE 값도 class balancing 때문에 보정된 확률로 주장하지 않는다.
3. `--n-action-steps 1 --temporal-ensemble-coeff .01`: 매 tick 겹친 chunk를
   `exp(−.01×i)`(가장 오래된 예측부터i=0)로 평균하는 선택지다. 기본은8/None이다.
   simulator 쪽은 numpy만 사용하고 pinned LeRobot `ACTTemporalEnsembler`와 합성 입력으로
   일치 검증했다. task 변경·시간 단절·interrupt·done에서 과거 chunk를 비운다.
   훈련 config의 `n_action_steps=8`은 그대로이며 **배포 외부 executor 옵션**임을 결과에 기록한다.
4. 실행 시 실제 추론113회 같은 호출마다 `chunk-predictions.jsonl`을 남겨
   재분석에 필요한 연속 출력이 요약에만 묻히지 않게 한다. 저장 예측 분석 CLI도 추가했다.

새 학습이나 물리 개선은 아직 검증하지 않았다. 매 tick 추론은 기존 CPU 중앙0.323초,
p950.375초/호출이므로0.1초 wall 주기를 만족하지 못한다. 시뮬레이션속도도 새로 재야 한다.
TE가 근본 원인을 고쳤다고 주장하지 않는다. 정답·교사·손으로 짠 파지 보정은 학생에 넣지 않는다.

## 6. 검증·GCP 대기열

CPU 전용 관련3파일 **38 passed, 0 skipped**: 기존 default8 실행, 입력 경계, 완료 전환,
BCE class 가중·padding·gradient, v1/v2 저장·로드, upstream ensembling 수치 일치,
reset·done·유효0행, 보류 누락/중복 거부, 미승인 큐를 확인했다.
실제 ACT 학습 backprop/optimizer step이나 모델 새 학습은 하지 않았다.
JUnit과 원본 해시는 요약 JSON에 있다. 새 시험을 기존 CI 목록에도 등록했다.

커밋 뒤 아래 생성기는 깨끗한 현재 SHA를 박아 **모든 단계 approved=false/enabled=false** 큐를
`/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-act4-<SHA8>.json`에 쓴다.

```sh
python3 -m scripts.queue_grasp_act_act4 \
  --output-dir /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue
```

선행 조건: 보류1,833개 저장 예측 분석·전체50개 회복 census·91100 첫30초 필요한 RGB만 회수,
오프라인 미검출/오탐 검토와 새 승인. 그 후 L4 smoke300→같은 후보 총10,000step→보류 평가,
GCP1 속도·정적 plan·미사용 seed 검증→새 후보1회·최대90 SIM초까지만 제안한다.
제안 seed91101은 기존 모델에서 미제출된 예약이지만 현재 미사용인지는 운영자가 다시 확인해야 한다.
모델 복사 목적지와 실행 argv는 큐에 구체적으로 적었고, 새 후보의 전체 해시·CPU 로딩을 요구한다.
기존 실패 모델의 잔여9개 재개는 포함하지 않는다. 전체 측정이 후보 방향을 지지하지 않으면
학습 전에 수정 묶음을 다시 검토한다. 알려진 결함을 발견하면 대기열을 이어서 소진하지 않는다.

GCP 프로젝트 고정·예산 정지·8h 상한·유휴20분·단계별 TERMINATED 확인을 유지하고,
가격/실제 크레딧·디스크는 운영 승인 전에 재확인한다. 새 모델은 생긴 뒤 별도 Release
재다운로드/해시/로딩 검증이 필요하다. 이번 커밋은 모델 배포나 학생 성공을 뜻하지 않는다.

## 참고 자료

- [Zhao et al. 2023, ACT 원 논문](https://arxiv.org/pdf/2304.13705), IV절·VI-B·Table III 확인:
  chunk100, KL beta10, batch8, lr1e−5; 겹치는 행동의 temporal ensembling을 사용한다.
  50시연은 **과제별**이며 Thread Velcro는100개다. 원 논문의50Hz·다중 카메라·관절 위치와
  우리의10Hz·자기RGB 이력·발행명령은 다르므로100step/50시연을 성능 보장값으로 옮기지 않는다.
- [LeRobot 공식 ACT 안내](https://huggingface.co/docs/lerobot/act): defaults 시작,
  batch8, 100k step 예시. 10k step은 이번 유한 비교 예산이며 수렴 충분성은 미확인이다.
- [실제 고정 LeRobot config](https://github.com/huggingface/lerobot/blob/89236ea0f4f81a81ca566081e20dd1ff5f823cbe/src/lerobot/policies/act/configuration_act.py),
  [modeling](https://github.com/huggingface/lerobot/blob/89236ea0f4f81a81ca566081e20dd1ff5f823cbe/src/lerobot/policies/act/modeling_act.py):
  설치된 동일 SHA 파일을 직접 확인. defaults chunk/n_action_steps100, KL10, TE None;
  TE 사용 시 n_action_steps1, 원 ACT 계수.01. `predict_action_chunk`만 부르면
  `select_action`의 큐/ensemble은 사용되지 않는다.
- [원 ACT 평가 코드](https://github.com/tonyzhaozh/act/blob/main/imitate_episodes.py),
  [원 ACT policy](https://github.com/tonyzhaozh/act/blob/main/policy.py): 평가 루프는 정해진
  `max_timesteps`, 정책 목적은 L1+KL이다. padding mask는 패딩 처리이며 스킬 성공 판단기가
  아니다. 독립적인 grasp/release done/phase 예측 권장값은 이 자료에서 확인하지 못했다.
- [PyTorch BCEWithLogitsLoss](https://docs.pytorch.org/docs/2.14/generated/torch.nn.BCEWithLogitsLoss.html):
  logit의 안정적인 BCE와 양성 가중을 확인했다. 우리 후보의 스킬별 class 균형·계수1은
  이번 희소 라벨에 대한 설계 선택이며 ACT 원 논문의 기본값이 아니다.
- [Ross, Gordon, Bagnell 2011 — DAgger](https://proceedings.mlr.press/v15/ross11a.html):
  자기 정책이 방문하는 상태의 전문가 행동을 축적해 모방학습 분포 이동에 대응한다.
  이번에 학생 실행/교사 재라벨링을 추가로 수행하지 않았다.
- [Laskey et al. 2017 — DART](https://proceedings.mlr.press/v78/laskey17a.html),
  [본문](https://proceedings.mlr.press/v78/laskey17a/laskey17a.pdf): 교사 행동에 노이즈를 넣어
  회복 상태를 보게 하고 학생 오차에 맞춰 노이즈 수준을 정한다. 임의 고정 노이즈는
  DART 전체 알고리즘 재현이 아니다. 추가 기록 시 보이는 대상 교사·held-object 제한,
  noisy 발행 이력과 clean 교사 표적 분리, 먼저 교사 관문 최소40회/95%를 유지해야 한다.
