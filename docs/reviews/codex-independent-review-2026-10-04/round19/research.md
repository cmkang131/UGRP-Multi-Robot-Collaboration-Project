# R19 — 최근 근접 연구 세 편으로 좁힌 다음 판별

**지금 가장 유용한 질문은 ‘재관측 뒤 무엇이 달라졌는가’다.** 유효한 자기 영상의 정보, 명령의 정지·완료, 상대와의 동기화가 함께 바뀌면 관측의 효과를 따로 설명할 수 없다. 아래 세 연구는 이 구분을 구체화한다. 현재 inspect 자세/worker 경계를 먼저 닫아야 한다는 [기존 우선순위](README.md)를 바꾸거나, VLA·새 센서를 도입하자는 제안은 아니다.

2026-10-04에 공식 원문을 읽었다. 기존 R1–18 bibliography와 겹치지 않는 세 편만 선정했다. [정확한 버전·읽은 범위·게재 확인 수준](primary-sources.md)을 별도로 남겼다. **새 코드·실험·모델 호출·원본 결과 분석은 수행하지 않았다.** UGRP 비교점은 #363 `66ff0978a817caa949d2d738b51d7ae89dd17e71`, #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`의 기존 소스 검토다. 최신 공개 stage의 inspect/relook 중단은 작성자 보고이며 여기서 독립 검증하지 않았다.

## 1. 같은 ‘분산 협업’에서도 다른 조건

| 연구 | 관측·통신과 학습/실행 | baseline·성공 판정·전이 | UGRP에서 직접 승계할 수 없는 부분 |
|---|---|---|---|
| [CHORUS, 2026 v1](https://arxiv.org/html/2606.12352v1), §3–5, App. B–C | 로봇별 local tuple을 모아 공유 VLA를 학습하고 독립 실행한다. 자기 top/wrist views와 proprioception, identity/role prompt를 사용하며 시연 전략은 teammate/workspace가 보이도록 선택한다. | 별도 weights·centralized VLA 등은 message 유무만 바꾼 대조가 아니다. 두 로봇 과제에는 partial credit이 있다. 실물 시연·평가이며 basket은 synchronized chunks를 쓴다. | 자기 wrist RGB+발행 명령만의 관측 충분성을 보장하지 않는다. shared training·가시성·실행 동기화 조건을 제거한 ‘무통신이면 충분’ 주장이나 sim-to-real 성능 증거가 아니다. |
| [CommCP, 2026 v1](https://arxiv.org/html/2602.06038v1), §III–V | RGB-D·현재 2D pose와 전체 질문을 알고, 관측 물체/근사 위치의 관련성을 골라 보낸다. CP는 option-token confidence를 이용한다. | 무통신, CP 제거, 관측 물체 수를 맞춘 무작위 선택, answer-sharing 제거가 있다. 정량 평가는 Habitat EQA의 정답 비율과 이동+전송 시간이다. | depth/pose 권한과 EQA 정답은 UGRP의 beam 운반·release 판정과 다르다. 물체 수를 맞춰도 token·전송 시각·총비용이 같다는 보장은 아니다. 프로젝트의 실물 영상 표기를 정량 sim-to-real 대조로 승격하지 않는다. |
| [Planned synchronization, 2025/2026](https://link.springer.com/article/10.1007/s10514-025-10225-4), §3–6 | 중앙에서 macro-action/check-in 계획을 구하고 각 로봇이 자기 부분을 실행한다. 기본 check-in은 공통 joint state를 복구한다. 실물 상대 관측은 ArUco·카메라·IMU를 사용한다. | 가변/고정 관측 간격과 비용을 비교하며 과제는 formation 유지다. 실물 check-in에는 heading 재보정/정지도 포함된다. | fixed ENUM이나 fresh fix가 완전한 공동 상태가 되는 것은 아니다. §6.1.2의 간단한 실행시간 보정은 분리된 dynamics와 무비용·무드리프트 대기가 전제여서 공동 빔에 그대로 적용할 수 없다. |

세 논문을 합친 성능 순위나 UGRP의 novelty 판정은 하지 않는다. CHORUS는 **허용된 view에 실제 필요한 정보가 있는가**, CommCP는 **보낸 양과 보낸 내용 중 무엇이 작용하는가**, synchronization 연구는 **관측과 기다림의 비용/효과를 어떻게 나누는가**를 묻는 데 가깝다.

## 2. 확률 보증은 특히 좁게 읽기

CommCP §IV-B의 calibration label은 LLM의 최고 confidence option으로 기술된다. Eq.2의 option/score set membership을 선택된 메시지 각각의 사실 정확도나 episode 성공률로 바꿀 수 없다. history를 입력에서 제외했다는 것만으로 같은 scene의 적응적 표본이 독립이라는 증명도 되지 않는다. 이는 논문 오류나 실제 표본의 가정 위반을 확인했다는 말이 아니다. **현재 UGRP에 확률 보증이 이전됐다는 근거가 없다는 뜻이다.** 적용 검토에는 독립적인 정답 정의, 표본 단위·분할, 고정 모델/prompt, 선택 후 평가 사건이 먼저 필요하다. [독립 원문 QA](validation.md#statistical-scope)

CHORUS의 local observation만 사용하는 학습은 공동 observation/centralized critic 학습과 구분한다. 반대로 weights를 공유하지 않는다는 통신 조건도 아니다. synchronization 연구 역시 분산 **실행**과 중앙 계획을 구분해야 한다. [관측·실행 가정 QA](validation.md#geometry-scope)

## 3. 논문별 최소 반증 설계 — 제안만, 미실행

아래는 각 연구에서 얻은 질문을 **우리의 진단 설계**로 바꾼 것이다. registered 본실험 arm을 고치거나 새로운 입력 권한을 부여하지 않는다. 진단용 입력 변형은 명시적으로 별도 fixture/ablation으로 표시하며 본실험의 정상 관측으로 위장하지 않는다. 하나의 request/단계에서 얻은 결과를 폐루프 임무 효과로 확대하지 않는다.

| 연결 질문·좁은 가설 | 최소 대조와 필요한 기록 | 가설을 반박/지지하는 형태와 한계 |
|---|---|---|
| **CHORUS → 자기 view의 역할.** 특정 다음 동작이 wrist 영상의 teammate/beam 관련 영역을 바꿔도 불변이라는 가설 | 통신 조건과 frozen own history를 고정한 **한 decision-level probe**에서 원래 허용 wrist 영상과 사전 지정한 관련 영역만 가린 입력을 비교한다. 같은 면적의 무관 영역 mask와 원본 재입력을 음성 대조로 둔다. frame ID/hash, 변형 영역, 실제 request bytes, next-action 분포를 기록한다. 추가 TOP·peer camera·pose 입력은 없다. | 관련 영역에만 반응 변화가 있으면 그 probe의 행동 불변 가설에 반한다. 동일 반응은 이 probe에서 행동 민감성을 찾지 못한 것이며, 중복 단서·정책의 불변 영역 때문에 내부 정보 사용 여부를 증명하지 못한다. mask의 분포 이탈 때문에 변화만으로 의미 이해나 물리적으로 가능한 hidden-state 구별을 증명하지 못한다. 현재 OpenCV 경로와 #371 모델 경로는 따로 판정하며, LLM 자기설명은 판정값으로 쓰지 않는다. |
| **CommCP → 내용 선택의 역할.** 같은 수의 메시지이면 내용 관련성은 중요하지 않다는 가설 | 한 frozen receiver request를 대상으로, **실제로 발행된 허용 메시지 후보** 중 사전 정의한 관련/무관 내용 선택을 대조한다. 새 oracle 문장은 만들지 않는다. 후보의 발행·근거 관측이 frozen request cutoff 이전이고 해당 진단에서 허용되는 정보인지 확인해 미래 정보를 제외한다. 각 원본 message ID/sender/본문 hash와 진단용 수신 슬롯을 보존한다. 전송 수·수신 슬롯·SIM 비용을 같게 둔 별도 replay이며 원래 실제 inbox였다고 기록하지 않는다. token 길이를 맞출 수 없는 후보는 제외하거나 길이 차이가 남은 대조라고 표시한다. 조건을 만족하는 후보가 없으면 이 대조는 구성 불가로 남긴다. | 같은 비용의 내용 교체만으로 다음 탐색/확인 요청이 달라지면 해당 request의 내용 불변 가설에 반한다. 동일 반응은 그 probe에서 효과를 찾지 못한 것이지 일반적 무효의 증명이 아니다. message availability를 확인한 뒤 비교하며 accepted reply/decision_sources를 사용 증거로 대체하지 않는다. 정상 arm의 총효과나 실제 sender의 최적 선택은 별도다. |
| **Planned synchronization → 관측과 기다림의 역할.** 한 relook 뒤 gate 변화가 시간/hold만으로 설명된다는 가설 | 카메라 자세가 유효하고 명령이 완료된 **동일한 합성 제어 snapshot**에서 초기 PF belief·RNG 상태·receipt·반복 관측 이력을 같게 두고 time·own commands·barrier messages·phase를 같게 재생한다. 허용 observer 경계에 authored supported scan과 no-support 결과를 주는 한 쌍을 만들고 동일 scan 재생 대조를 둔다. scan 적용, current quality, fix receipt/age, report revision, guard branch를 함께 기록한다. | 오직 scan이 달라져서 report/gate가 달라지면 그 fixture에서 시간만의 설명은 반박된다. scan 없이도 같은 변화라면 timer/명령/기존 belief 경로를 먼저 본다. no-support도 시간이 흐른다. 양쪽 모두 실패하면 관측이 무가치하다고 결론내리지 않는다. 이 대조는 filter→decision 기여만 검사하며 실제 RGB의 기하 타당성·최적 재관측 간격·공동 빔 정지 안정성을 입증하지 않는다. |

각 probe에서 모델 sampling이 있으면 한 번의 동일/상이 출력을 인과 결론으로 읽지 않는다. 고정 request의 반복 변동과 사전 정의한 행동 분류를 함께 보고해야 한다. 여기서는 모델을 호출하지 않았다. CommCP 대조의 비용 고정은 진단의 인위적 통제이므로 현재 live billing이나 폐루프 시간 동등성을 인증하지 않는다.

## 4. 현재 로그로 가능한 부분과 먼저 필요한 것

[R17 producer 표](../round17/trace.md)에 따라 frame ID/hash와 pair input phase는 기존 키로 묶을 수 있다. 동일 capture의 상위 servo target/포트 명령 상태는 command-layer 불일치 진단에 쓸 수 있지만, 실제 joint pose나 모든 순간 issued setpoint를 복원하지는 못한다. 저장 grasp mean의 revision과 provider의 frame별 consumed 시각은 일반 HIGH 기록에 충분히 남지 않는다. 따라서 마지막 probe의 `report revision` 연결은 **최소 진단 추가 제안**이지 기존 로그에서 복원됐다는 말이 아니다.

R10의 scan/receipt 구분, R15의 절차 완료/물리 성공 구분, R17의 producer 경계는 그대로 유지한다. 이번 새 문헌으로 기존 합성 증인을 새 실험으로 다시 세거나, mask/replay fixture를 actual camera data로 인정하지 않는다. 임무 효과를 나중에 평가한다면 동일 버전의 별도 task predicate와 유효성 판정을 사용하고 stage `REACHED`·partial credit·EQA 정답률을 섞지 않는다.

후속 설계의 아직 열린 질문은 **대조가 원래 입력의 유효 범위를 유지하는가**다. mask가 만드는 영상의 분포 이탈, message replay의 발행 cutoff/비용 고정, observer fixture의 물리적 실현 가능성을 각각 따져야 한다. 이 조건을 만족하기 전에는 진단 민감성과 실제 통신·재관측의 임무 효과를 분리한다. 현재 막힘에는 세 번째의 명령/관측 분리를 먼저 적용할 가치가 있지만, 실제 실행 권고나 현재 원인 확정은 아니다.
