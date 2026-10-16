# ACT6 — 정지 분석과 통합 재학습 준비

2026-10-15, PR #504 / `claude/act-train`, 기준 `bd14057827e9d2a94c5030469808614dd86aea77`.
[act4](act4.md), [act5](act5.md), [운영 기록](operations-f609979c.md)을 먼저 읽었다.
[측정 원장](act6-measurements.json), [요약](act6-summary.json), [잡음 모형](act6-noise.json).
**실행 0회인 준비 라운드다. 정지로 투영되는 출력은 확인했으나 L1·이력·chunk의 인과 기여율은 미확정이다.**
새 교사 관문·기록·학습·보류 추론·폐루프·속도 측정은 수행하지 않았다. 원격 호스트 접속도 없다.

## 1. 정지 원인: 관측된 현상과 설명의 한계

91100 저장 900틱에서 바퀴 4개가 0인 틱은 **755/900**, 현재 자기 RGB의 cyan 성분이
보이면서 정지한 틱은 **723/900**이다. 대상 가시는 868/900, done 요청은 0/900이다.
마지막 비영점은 25.6초. 새 추론 경계 113개 중 88개가 정지하며,
**26.4–89.6초 새 추론 80/80개도 정지**한다. old chunk가 소진되지 않았거나 done이
일찍 켜져 멈춘 사례가 아니다. 기존 완료 검출 실패(보류 grasp 0/5, release 0/5,
오탐 0/1823, 임계값 .65 고정)는 접근 실패와 별도 결함이다.

실행 투영 `decode_action`은 `abs(w)<.155` 또는 pulse<1ms를 0으로 만든다.
act5에서 재현된 저장 예측을 다시 분석했다(새 추론 없음).

| 시점(SIM초) | 바퀴 예측 최대 절댓값 | .155 미만 바퀴 | 1ms 미만 pulse | 실행 바퀴 |
|---|---:|---:|---:|---|
| 11.2 | .081475 | 4/4 | 1/4 | 전부 0 |
| 44.8 | .002916 | 4/4 | 4/4 | 전부 0 |
| 89.6 | .002806 | 4/4 | 4/4 | 전부 0 |

따라서 후기 정지의 직접 경로는 **거의 0인 행동 예측 → 기존 투영 → 실제 발행 0**이다.
임계값은 바꾸지 않았다. 정규화된 숫자 0(평균 행동)으로 붕괴했다고 쓰면 부정확하다.
정지 행동의 정규화 좌표는 `[-.220507,-.264747,-.226705,-.116789]`이고,
44.8초 출력은 `[-.231187,-.265350,-.213983,-.127867]`,
89.6초는 `[-.223137,-.255408,-.214463,-.115641]`로 **정지 행동에 대응하는 좌표**에 가깝다.

### 교사에서 0은 어디에 있는가

50개 전체 RGB census 결과(13,501 local grasp 프레임)는 이미 회수됐지만,
이번 Mac에 있는 명령/학습 원본은 **86000·86001의 2/50개**다.
회수된 색 census만으로 나머지 48개의 바퀴·팬 명령을 만들어내지 않았다.
아래는 이 두 시연의 local **719행**이며, 전체 50개 비율이 아니다.

| 구간(teacher_phase) | 바퀴 전부 0 / 행수 | 해석 |
|---|---:|---|
| approach | 0/183 | 접근에서는 계속 이동 |
| align | 8/37 | 정렬 대기; 이 8행은 PWM도 그대로 |
| hover / descent / close / lift | 105/105 | 팔 동작 중 바퀴 정지 |
| lift_settle / lookback_settle | 74/74 | 고정 정착 대기 |
| lookback_pose / verify_lift / hold | 104/104 | 카메라 자세·RGB 확인·유지 |
| lookback / lookback_return | 4/84 | 말기 명령 기반 왕복; 대부분 이동 |
| lower / open / retract | 90/90 | 놓기·팔 회수 |
| backoff | 2/42 | 대부분 후퇴 |
| 전체 | **387/719 (53.82%)** | 바퀴별 중앙값 모두 0 |

정지 387행 중 팬 명령이 바뀌는 행은 32, 어느 PWM이든 바뀌는 행은 144다.
정지=불필요한 대기로 지우면 팔 조작과 정착 표적도 지워진다. navigation/inspection을 포함한
전체 기록에서는 559/894행이 정지한다. 보류 1,833행에서는 **세 발행 drive 성분 모두 정지**인
표적이 grasp 732/1398, release 235/435다. 이는 역혼합 impulse의 1e-4 기준 proxy이며,
원시 바퀴 4개가 정확히 0이라는 지표와 합산하지 않는다.

L1의 조건부 중앙값 성질과 이 표적 비중은 정지 쏠림과 양립한다.
그러나 전체 중앙값은 해당 영상에서의 조건부 중앙값이 아니며,
**데이터 불균형이 원인이라고 확정하거나 53.82%를 인과 기여율로 쓰지 않는다.**
전체 50개 명령 census용 `analyze_grasp_act_stall --teacher-runs-root`를 저장자료 점검으로 큐에 남겼다.

### 비슷한 영상에서 교사는 무엇을 했는가

같은 cyan 교사(86000)에서 현재 색 bbox의 `(cx,cy,width/640,height/480)` 유클리드 거리로
가까운 10개를 찾았다. 학생 3.2초에는 교사 10/10개가 approach 이동(최근접 거리 .0797),
11.2초에는 align 9·hover 1개 중 정지 5/10(최근접 .1274),
44.8초에는 align 8·hover 2개 중 정지 6/10(최근접 .2719)였다.
후기는 가까운 사례조차 상자가 덜 잘려 있다. 카메라 PWM·명령/RGB 이력이 동일하지 않으므로
이는 영상 유사도 기술 통계이며 **91100 상태의 교사 반사실 정답이 아니다.**

직접 본 자기 카메라: 학생 0·3·5·8·12·18·36·54·72·89.9초 **10장**;
추가 비교 시트는 학생 0·3.2·5.6·11.2·25.6·44.8·89.6초 7장과
교사 절대 SIM 2·8·10.4·10.7·10.8초 5개 고유 프레임이다.
상자는 오른쪽 경계로 이동하고 후기에는 잘린 부분만 남는다. 다른 로봇과 같은 끝을
다투는 장면은 없다. 파일·해시는 측정 JSON에 연결했다. 원본 RGB를 읽었으며 새 장면 렌더는 없다.

### 초기 이력과 0.8초 개방 루프

명령 나이 성분의 시작 최대 24.903σ는 재확인했다. 3σ를 넘는 것은 학생 **14/900틱**,
마지막 1.3초까지다. local 교사 두 개에는 11/719틱이 있다.
초기 분포 차이는 존재하지만 후기에도 24.9σ가 유지되는 것은 아니다. 초기 오차가 이후
방문 상태를 바꿨을 가능성과 그 기여율은 matched 초기화 재실행 전까지 미확정이다.

chunk8은 900틱에 113회 호출, 명령이 참조한 관측 나이 평균 .3491·최대 .7초다.
후기 새 추론 80/80 정지는 단순 chunk 지속만으로 설명되지 않는다. 다만 중간 복구 피드백을
최대 .7초 늦추는 효과는 있다. 2–4 step 재질의가 성공을 고칠지는 미측정이다.
명령 이력 dropout은 11.2초 국소 근거에 대한 비교 후보이며 후기 해결책으로 확정하지 않는다.

## 2. DART 복구 시연 — 기본 off

`harness/grasp_act_dart.py`와 `run_grasp_act_recovery.py`의 `--recovery-mode dart_wheels_v1`.
기존 solo 교사 `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`의 깨끗한 별도 checkout을
명시적으로 받는다. 없는 모듈만 그 checkout에서 로드한다. 교사·IK·파지 경로를 복사하지 않는다.
실행은 **이 ACT SHA + 교사 의존 SHA**의 조합으로 기록하고 새 관문도 같은 조합에서 잰다.
이 브랜치 자체에 없는 교사 구현을 이미 통합·물리 검증했다고 표시하지 않는다.

- 보류 첫 행동 오차 **1833/1833행**을 대조했고, grasp 1398행의 바퀴4+길이4 성분에서
  `diag(mean(e_j²))`를 산출했다. 0평균 대각 Gaussian의 MLE이며 편향 에너지도 포함한다.
  잡음 평균0, 추가 배율1(α/T=trace Σ). 바퀴 σ는
  `.071441/.129618/.125202/.070978`, 길이 σ는
  `.008961/.012066/.011552/.010046초`다. 길이의 모형 단위는 `/0.15초`다.
- 절대 오차만 회수되어 **교차 공분산은 미확인**이다. 임의 상관을 채우지 않고 대각 모형으로
  제한했다. 원 논문의 반복적 재추정 전체를 재현한 것이 아닌 한 차례 DART 기반 후보다.
  이전 보류5개는 이제 잡음 산정에 사용한 개발 자료다.
- approach/align에서, holding이 아니고 그 단계에 계속 머무를 때 실행 바퀴/길이에만 잡음을
  더한 뒤 기존 명령 범위로 투영한다. 팬·팔 PWM, 완료 라벨, held 구간은 건드리지 않는다.
  크기뿐 아니라 **투영 후 실제 잡음·잘림·가시 이탈→회복 수**를 새 원장으로 확인해야 한다.
  현재는 복구 상태를 실제 만들었다거나 시연 수가 늘었다는 결과가 없다.
- 매 틱 교사는 **지금 방문한 상태**에서 깨끗한 행동을 계산한다. 실행은 noisy,
  teacher `remember_applied`와 student 명령 이력도 noisy, 학습 표적만 clean이다.
  이전 깨끗한 궤적을 표적으로 재생하지 않는다. 관측 allowlist는 그대로다.
- 새 seed 관문40은 학습 RGB OFF. hash로 읽은 결과 40개, 성공≥38, 같은 소스·잡음·호스트,
  held/invisible 입력 감사0, weld off와 명시적 검토 승인이 있어야 **첫 기록부터** 허용한다.
  기록은 원 학생 카메라 640×480·10Hz·FOV를 그대로 쓴다. 먼저 2개를 점검한 뒤 나머지48.
  모든 실패와 HOST_ERROR도 보존하며 같은 결함 확인 시 더 채우지 않는다.

## 3. 학습·배포 후보

원 train45 + 새 recovery train45, 새 recovery 보류5로 계획했다.
기존 보류5는 새 평가 분모에서 빼고 과거 오차/잡음 산정 자료로 보존한다.
원본과 복구의 카메라·호스트/머신·각 파일 hash를 확인하고 **train만**으로 통계를 다시 맞춘다.
두 군은 같은 데이터·seed·BCE done·예산이며 명령 이력 dropout만 p0 / p.2로 다르다.
각각 smoke300 → 그 체크포인트에서 총10k. 새 보류는 고정 마지막 체크포인트 평가이며
두 군을 보고 고른 1회 폐루프는 개발 확인으로 분류한다. 정식 통신 조건 비교가 아니다.

추론 기본값은 chunk8/TE 없음/CPU1 그대로다. 선택 시 stride 1–4 + TE .01을 지원하고,
질의하지 않는 틱에도 과거 chunk의 horizon을 한 칸씩 이동한다. stride1 수식과 기존
reset/interrupt/done 경계는 유지한다. stride2–4는 upstream 기본 기능이라고 하지 않는다.
`--actor-threads 1/2/4/8/16`을 기록하며 1은 기존 inter-op 기본값, 나머지는 inter-op1이다.

GCP1 n4-highcpu-64의 저장 입력 40개(워밍업8·측정32), thread별 새 CPU worker에서
RPC+전처리+batch1 추론의 median/p95/max를 잰다. 비교 후보는
n_action_steps 1/2/3/4 각각 TE off/.01, 기본8/off다.
p95≤.1×steps는 **질의 주기 예산** 기준이며 매 틱 실시간 응답 보장이 아니다.
기존 .323/.375초에서는 1step .1초가 맞지 않고 4step .4초도 물리 비용 여유를 새로 봐야 한다.
선택 설정의 첫30 SIM초 wall/SIM·부하·원본 확인은 별도다. **Mac 속도 측정은 0회**다.

## 4. search17 명령 적분 점검 — 중복 구현 없음

`claude/e2e18-grasp-rootcause`의 `search17.md` 47–80행과 관련 소스를 읽었다
(조회 ref `2a4274ae3a90dbdd86c21a38ee348cdb69b7e809`).
1.317653배, 고정 보정의 새 물리 효과는 그 기록의 결과이며 이번에 재측정하지 않았다.
`.35 / ((.35−1/12)/(1−1/12)) = 1.203125` 산술과 코드 연결을 확인했다.

| 경로 | 확인 결과 |
|---|---|
| 1대 교사 `primitives()` | `harness.grasp_act_visible_world.command_delta`와 `sim.grasp_act_teacher_v3.propagate_owned` 재사용 |
| 고정 교사 SHA의 두 함수 | 65mm 바퀴·150rpm × PWM 공칭 적분. 목표 기억·yaw·backoff/lookback에 사용. search17 마찰/고정 보정은 없음 |
| 학생 `IssuedClock` | 명령 PWM 변경 시각·스킬 시작 시각만 재는 clock. 바퀴/PWM→속도·자세 적분 없음 |
| 학생 context | 자기 명령과 나이/PWM·clock을 수치화할 뿐, 명령 적분 자세를 넣지 않음 |

따라서 **교사는 같은 공칭 모델의 영향을 받지만 학생 clock은 그 모델을 쓰지 않는다.**
복구 교사에서 이 오차가 늘어날 가능성은 새 관문 점검 대상이다. search17 계수를 이곳에
복제하거나 빔의 1.32배를 상자·학생에 그대로 적용하지 않았다. 교사 모형을 바꾸면 같은
공통 함수에서 별도 토글로 바꾸고 새 SHA/noise 조건의 관문을 다시 통과해야 한다.

## 5. 검증·미승인 대기열

관련 고유 시험 **47 passed / 0 failed / 3 skipped**. 새 ACT6 경계21개 전부 통과:
clean/noisy 이력 분리, default off, held/말기 보호, Gaussian residual 크기,
stride1–4 horizon 정렬, gate 실제 파일·hash·38/40·중복/누락/누설 거부,
복구 데이터 자격·호스트 혼합 차단·train-only 통계, 모든 승인/ready false를 확인했다.
기존 BCE/dropout의 합성 gradient·RNG 시험은 torch가 있는 기존 Python에서 재확인했다.
남은 3개는 현재 로컬의 고정 LeRobot/draccus 부재로 upstream 직접 비교1개와
adapter 저장/로드2개가 미실행이다. 새로운 실제 모델 학습·추론·optimizer step은 없다.
workflow 등록은 read-only plan 시험1개로 확인했다. JUnit 원본은 요약 JSON에 연결했다.

커밋 뒤 아래 명령으로 로컬 큐를 생성한다.

```sh
python3 -m scripts.queue_grasp_act_act6 \
  --output-dir /Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue
```

`20261015-act6-<최종SHA8>.json`: **잡음 교사 관문40 → 기록50 → 변환/합성 →
두 군 smoke300→10k → 새 보류평가 → GCP1 속도 → 선택 모델 폐루프1회/90초**.
별도의 full-teacher 저장 원장 분석을 선행한다. 모든 단계·run의
`approved/enabled/ready/stage_ready/submitted=false`; 실제 제출 0.
마지막 실행 명령은 측정 설정·선택 모델 영수증이 생기기 전까지 null이며 template만 있다.
act4/act5 큐는 수정하지 않는다.

제안 seed: 관문8316600–8316639, 기록86600–86649, 학생91660.
열린 PR20개 변경 텍스트와 로컬 큐에서 숫자 충돌은 없었다([범위·한계](act6-seed-audit.json)).
과거 모든 ref 전수 검사는 끝내지 않았으며 근거로 쓰지 않았다. **원격 실재고 미사용은 미확인**이므로
운영자의 최신 재고 대조/예약 전에는 활성화하지 않는다.

GCP 프로젝트 고정, 예산/실크레딧·현재 가격 확인, budget-stop 발동 시 중지/통지 및 호스트 전환 금지,
8h STOP·유휴20분·단계별 종료 확인을 적었다. 학습 두 군 총상한46,800초,
교사 관문14,400초·기록18,000초·속도/폐루프 각각1,800초를 별도8h 창으로 나눈다.
예상 raw는 관문40×32MiB·기록50×96MiB; 보수 예약은 관문10GiB·기록50GiB,
변환/합성40GiB·체크포인트32GiB다. 다른 승인 작업 쓰기까지 합쳐 서버 바닥8GiB,
Mac20GiB(archive 시 ARM25GiB)를 남겨야 한다. 학습 디스크 시작 여유80GiB 제안은
실측 크기와 다른 작업을 더해 재검토한다. 디스크 추가/교체 승인은 이 큐에 없다.
선택/비교 모델이 생긴 뒤 새 Release에 보존하고 재다운로드·해시·로딩 확인은 여전히 남는다.

## 참고 자료

- [Laskey et al. 2017, DART 본문](https://proceedings.mlr.press/v78/laskey17a/laskey17a.pdf),
  §4 Eq.3–4, Algorithm1, 부록4.3 확인. 학생-교사 residual 외적에서 잡음을 맞추고
  예상 오차로 trace를 조정하며 보류 시연을 쓴다. 이번 대각 제한·바퀴만·접근/정렬만·배율1은
  우리 명령/held 경계에 맞춘 설계다. 본문의 개선률을 우리 결과에 이식하지 않는다.
- [Zhao et al. 2023, ACT](https://arxiv.org/html/2304.13705v1), §IV-A와 방법 설명 확인.
  chunk/겹친 행동 평균의 피드백 의미를 참고했다. 0.2–0.4초 재질의가 우리 과제의 권장값이라는
  근거는 없으며 배포 측정 후보일 뿐이다.
- [고정 LeRobot modeling](https://github.com/huggingface/lerobot/blob/89236ea0f4f81a81ca566081e20dd1ff5f823cbe/src/lerobot/policies/act/modeling_act.py):
  현재 웹 원문 조회는 실패. 기존 로컬 `/private/tmp/upstream-modeling_act.py`의
  ACTTemporalEnsembler를 읽었으나 이번 조회에서 원격 SHA와의 일치는 **미확인**이다.
  dense TE의 upstream 직접 실행 시험도 현재 미실행이며, sparse 평균은 독립 합성 입력으로 검증했다.
- [PyTorch set_num_threads](https://docs.pytorch.org/docs/stable/generated/torch.set_num_threads.html):
  이번 웹 응답은 redirect만 있어 본문 **미확인**. 실제 API 동작/CPU 성능은 GCP 큐에서 확인한다.
- 프로젝트 자료: [search17](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/2a4274ae3a90dbdd86c21a38ee348cdb69b7e809/experiments/2026-10-14-e2e18-grasp-rootcause/search17.md),
  고정 solo 교사 SHA의 `sim/grasp_act_solo_teacher.py`, `harness/grasp_act_visible_world.py`,
  `sim/grasp_act_teacher_v3.py`, 이 브랜치 `harness/grasp_act_contract.py`를 직접 읽었다.
  code/static, 저장 원장, 새 물리 검증을 각각 구분했다.
