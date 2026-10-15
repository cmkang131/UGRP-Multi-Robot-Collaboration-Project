# beamact1 — 빔 짝 ACT 첫 학습 준비 (NOT_READY)

PR #537 위의 기본 off 후보다. beampair8 원본185시드에서166/19시드로 학습/검증을 나누며 두 로봇 기록을 시드별로 묶는다. 보류8329000–8329019는 모두 제외한다. 정규화는166개 TRAIN 시드의 고유 행에서 다시 계산한다.

공유 가중치 하나를 선택했다. 동일 기체·카메라·행동 형식이고 청록/파랑 역할이 로봇 사이에 교차 배정돼 사례를 공유한다. 로봇 ID는 텐서에 넣지 않는다. 입력은 기존 v6 자기 RGB4장과 자기 발행16명령·고정 작업 토큰/명령 시계뿐이다. 평가용 교사 단계 sidecar는 텐서에 넣지 않는다.

act16a/act16w와 동일한 `history_causal_split_v1=wheel_pulse_train_mean`을 학습과 배포에 함께 적용한다.16개 wheel/pulse 슬롯만 정규화 TRAIN 평균(0)으로 가리고 PWM·age·작업·명령 시계는 유지한다. whole-history dropout은 act16 첫 A/B 계획과 같이0이다. 임의의 추가 확률을 합치지 않는다. 기본값은 off다. adapter v3와 입력 변환을 함께 저장하고 stock loader의 묵시적 마스킹 누락을 거부한다.

학습은 고정 LeRobot ACT/ResNet18·batch8·chunk8·10Hz·balanced_bce_v1을 재사용한다. smoke300스텝 저장/재로딩 후 총10000스텝까지 optimizer/RNG를 복원한다. 최종 step 고정이며 validation/보류20으로 checkpoint를 고르지 않는다. act16w의 h0-only DAgger 경계는 확인했으나 이 첫 데이터에는 학생 방문 DAgger가 없어 사용하지 않는다. 교사185/200=92.5%는 새≥95% 관문 통과가 아니다. 이 데이터 사용은 사용자 명시 지시이며 기존 beampair7 관문40/40과 합산하지 않는다.

## 자원 차단

두 번째 L4 `ugrp-act-l4-gcp2b` 생성은 `GPUS_ALL_REGIONS=1`에 막혔다. 기존 GPU 한도 preference를2로 증설 요청했으나 GCP가 `Quota request denied`로 거절했다. `gpu-quota-final.json`·`l4-create.json` 참조. warp3의 L4는 변경하지 않는다. 첫 프로젝트·다른 호스트·Mac 계산으로 대체하지 않는다.

GPU 학습·저장/재로딩·ACT 검증 MAE·학생 폐루프20·실패 영상·Release 배포는 **미실행**이다. 데이터 준비와 persistence 기준선은 GCP2 CPU에서 별도로 검증하며 아래에 결과를 추가한다. 학습된 모델이 없어 registry에 가짜 파일/해시/URL을 등록하지 않는다.

## 학생 평가에 남은 연결

기존 pair ACT 출력은14차원 명령+done이며 별도 READY head는 없다. 교사 READY phase를 학생에 넘길 수 없다. 학생 자기 명령의 닫기 요청을 READY로 해석해 기존 boolean GO/ACK 장벽에 연결하는 방식은 후보 설계다. 보류20을 쓰기 전에 이 연결과 학생-only 실행기를 구현/검증해야 한다. 정답으로 READY/스킬을 정하거나 교사 근거리 경로로 대체하지 않는다.

평가는 gcp2 C MuJoCo·같은 장면·두 학생·held 숨김·weld off·16동시(호스트 합계≤40)·60 SIM초 cap이다. n/20과 접근→정렬→READY→집기→3초 들기 퍼널을 raw에서 재계수한다. 실패 전10SIM초10Hz 자기 RGB ring을 기록하고 분석/몽타주는 gcp2에서 만든다. eval 큐는 실행기 검증까지 command=null,ready=false다.

## 참고 자료

- [ACT 원 논문](https://arxiv.org/abs/2304.13705), [공식 코드](https://github.com/tonyzhaozh/act)
- [Causal Confusion in Imitation Learning](https://arxiv.org/abs/1905.11979)
- PR #504, act16a PR #528, `claude/act16w` c6a4569cf의 마스킹·h0-only DAgger.

빔 학생에서 마스킹 효과는 미측정이다. 원 논문이 프로젝트의 마스킹 수치/성공률을 보증하지 않는다.


## 실제 완료한 검증

- 데이터 아카이브 SHA-256 전체 일치. 원본 manifest는 `87a1b094…12fb9`, 새 분할 manifest는 `a0f5d8a1…58d6cd`다.
- 학습166시드/60,023행·검증19시드/6,908행, 총66,931행. 동일 시드의 두 로봇은 같은 split에 있고 보류20과 중복0이다. 모든 shard의 원본 바이트 해시를 검사했다. [데이터 요약](dataset-summary.json).
- Mac 관련 비물리 검사34pass/2skip(기존 torch 의존 검사) 및 새 workflow/입력 검사26pass/1skip. 서로 겹치는 시험이 있어 합산하지 않는다. GCP2 CPU의 opt-in 실제 ACT adapter 저장/재로딩·동일 예측과 입력 검사6pass. 임의 초기화 모델이며 optimizer0, L4 smoke는 아니다([검사](cpu-adapter-check.json)).
- persistence는 마지막 **실제 발행** 명령을 유지하는 오프라인 기준선이다. 마스킹한 입력값을 복사하지 않는다. 검증 전체6,908행의 휠 MAE0.02312898·pulse2.9610ms·PWM8.3018, 재추론 격자913행은0.02280942·3.3832ms·8.9093이다. ACT MAE는 미측정이다([전체/단계/에피소드 지표](persistence.json)).

|검증 구간|행|persistence wheel MAE|pulse MAE(ms)|PWM MAE|
|---|---:|---:|---:|---:|
|전체 h0|6908|0.023129|2.961|8.302|
|재추론 격자 h0|913|0.022809|3.383|8.909|
|전체 접근|2968|0.034729|5.753|2.455|
|전체 정렬|1142|0.045359|2.096|4.050|
|재추론 접근|385|0.032955|5.552|2.915|
|재추론 정렬|145|0.036810|1.679|4.548|

재추론 격자는 연속 구간별8틱마다 잡은 오프라인 배포 모사이며 실제 학생 방문의 재추론이 아니다. ACT15 학생 방문상태의 교사 라벨 MAE와 분포가 다르므로 직접 우열 비교하지 않는다. pick의 정지 휠이 전체 MAE를 낮추므로 단계별 수치를 함께 본다.

학생 성공 `n/20`은 아직 값이 없고 시도0·미시작20이다. 접근·정렬·READY·집기·3초 들기 퍼널도 null이며0/20 실패로 쓰지 않는다. 실패 실행이 없어 영상/프레임과 원인 주장은 없다. 물리/렌더/교사행동/학습 step은 모두0이다.

## 재현과 재개

소스: 준비 `2ce58845b`(전체 SHA는 verification.json), CPU adapter/오프라인 `5cf752b5e5e885bf4effe353829fd89806b30ce9`. 모든 gcp2 사본은 git-shared.git만 직접 참조한다. 데이터는 gcp2 영속 디스크에 있고 전체 독립 백업은 없다. Mac에는 이 요약/검증 기록만 회수했다.

원본 `/home/ugrp/ugrp-sim/ops-reviews/beampair8/dataset-v1/dataset.tar.zst`, 분할 `/home/ugrp/ugrp-sim/ops-reviews/beamact1/data-v1/split-v1`, 단계 sidecar `.../data-v1/stages.json`이다. 원본 아카이브/기록은 그대로 보존한다.

```sh
# gcp2 CPU; 새 output만 사용
PYTHONPATH=. /home/ugrp/ugrp-sim/ugrp/.venv-sim/bin/python -m scripts.sim_cli workflow run beamact1-offline -- \
  --dataset /home/ugrp/ugrp-sim/ops-reviews/beamact1/data-v1/split-v1 \
  --stages /home/ugrp/ugrp-sim/ops-reviews/beamact1/data-v1/stages.json --output NEW_EMPTY_OUTPUT
```

초기 분할은 등록 전 direct CLI였고 표준 관리 기록으로 소급하지 않는다. persistence는 실제 관리 기록의 exit0·입력/소스 변경0을 확인했다. smoke의 구체적 명령은 [plan.json](plan.json)에 있지만 GPU가 없어 비활성이다. main은 같은 source/data/mask의 smoke300 readback 후에만 source/data/smoke 해시를 묶은 admission을 만들고 `--resume .../step-000300 --steps 10000`으로 이어야 한다. 평가 큐는 READY 연결도 완료되기 전에는 열지 않는다.

[PR #540](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/540)은 DRAFT이며 병합하지 않았다. GPU VM과 디스크 생성은 둘 다0이며 GPU0h·추가 VM 계산비용$0이다. 기존 CPU의 공유 비용은 별도 작업과 분리 청구되지 않아 이 작업 비용으로 확정하지 않았다. 비용/유휴/8h 장치는 해제하지 않았다.


자기 실행 프로세스0·beamact1 임대 제거를 확인했다. reloc18·beampair9 임대와 타 작업 계산 프로세스9개가 있어 gcp2 CPU는 정지하지 않았다([정리 기록](lease-released.json)). 두 번째 L4와 디스크는 API 조회 모두 빈 목록이며 생성 실패로 정지할 인스턴스가 없다. CI check는 아직 보고되지 않았으므로 통과로 표시하지 않는다.
