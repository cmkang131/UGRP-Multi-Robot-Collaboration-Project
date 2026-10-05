# 8차 연구 검토: HIGH 경계·과신·관측의 유효성을 구분하기

**지금 유용한 다음 질문은 “더 많이 보거나 더 강건하게 맞추면 되는가”보다 “현재 결정에 필요한 실제 경계를 보고 있는가, 어느 가정이 틀리면 같은 관측이 나오는가”다.** HIGH reference timeout의 알려진 OLS 취약성과, 검출에 성공해도 ROI 끝을 beam 경계로 잘못 받아들이는 합성 반례는 반대 방향의 실패다. 하나의 성공률로 묶으면 후자를 개선으로 오해할 수 있다.

우선순위는 **① 기존 HIGH 프레임에서 실제 색 전이와 ROI 끝을 먼저 구별 → ② 같은 후보점의 OLS 초기 residual과 대안 적합을 비교 → ③ 최신 guard의 최초 거부를 capture 시각·clearance·margin에 연결**하는 순서다. ①·②는 같은 영상의 분석으로 가능한 판별이며, 새 물리 실행이나 신경망 도입을 선행조건으로 두지 않는다.

검토일 2026-10-04 UTC. 코드 기준은 PR #363 `0d7c5eb3ca3643ead2a0b50dd133a1188f06f572`. 본문은 코드에서 직접 확인한 사실, 작성자가 공개한 실행 보고, geometry 에이전트의 합성 재현, 수학적 조건부 추론을 구분한다. 실제 물리·LLM·하드웨어·held-out 실행은 하지 않았다. 기존 구현을 변경하거나 새 실험을 시작하지 않았다. 인용의 직접 읽은 범위와 입력 가정은 [primary source 확인표](research-sources.md)에 있다.

## 1. 먼저 최신 진도와 판단 범위를 맞춘다

공개 PR 보고에서 `ace8b257`의 `raise_high_align`은 hover 확인→닫기→HIGH까지 REACHED다. 이후 `d5ca2ec3`의 `align_to_carry`는 99.9초 `HIGH_CARRY_EDGE_REFERENCE_TIMEOUT`에 멈췄다. 작성자는 HIGH의 `edge_line()`이 오른쪽 5–10개 이상치 열 때문에 None을 내는 것으로 진단했다. 이것은 기존 raw를 새로 독립 확인한 결과가 아니다. 단계 도달은 배달/E2E 성공도 아니다.

`0865a788`의 접근 보고는 8.7초 시작 완화 뒤 9.0초 `inside_pair_deeper`, 평가 오차 약 44 mm와 `std_xy` 2.6 mm를 담는다. **이 궤적은 최신 0d7c5eb3의 행동으로 인용하지 않는다.** 이후 수정은 과거 첫 8.7초 명령 자체를 `start_outside_pair_enters`로 막는 [회귀검사](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/tests/test_highpose_start_relief.py#L62-L72)를 추가했다. 해당 검사와 현행 조건 분기를 직접 읽었으며 이 연구 에이전트가 물리 재실행한 것은 아니다. 따라서 다음 두 문제를 분리한다.

- HIGH 검출기의 관측 모델/강건성: 현행 코드 자체와 합성 입력으로 검토할 수 있다.
- 과거 접근의 위치 추정 과신: 원인을 가르는 공개 witness다. 최신 접근의 재현된 실패 시각이나 새 충돌 확률은 알려 주지 않는다.

## 2. HIGH edge: 이상치 제거와 참 경계 식별은 별개의 일이다

[현재 `own_beam_edge.py`](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/own_beam_edge.py#L29-L96)는 140..496 열을 4픽셀 간격으로 고르고, 행 40:300 안에서 길이 40 이상인 첫 색 띠의 마지막 픽셀을 얻는다. 전체 후보에 OLS를 맞춰 4픽셀 이내 점을 고른 뒤 재적합하고, 점 수/비율과 RMS 2.5픽셀을 검사한다. 초기 직선이 잘못되면 올바른 다수점부터 탈락할 수 있다.

[MLESAC 원문](https://www.robots.ox.ac.uk/~vgg/publications/2000/Torr00/torr00.pdf)은 contamination이 있을 때 OLS 초기값이 부적절할 수 있음을 설명하고, 후보 생성과 likelihood 평가를 구분한다. [OpenCV `fitLine`](https://docs.opencv.org/4.13.0/d3/dc0/group__imgproc__shape.html)도 여러 robust loss와 반복 가중 적합을 제공한다. **이들은 표준 후보를 비교할 근거이지, 검출 점의 의미가 잘못된 문제까지 해결하는 처방이 아니다.**

### 서로 다른 설명과 반증

| 설명 | 관측과 연결되는 근거 | 최소 판별 자료 / 해당 설명에 불리한 증거 |
|---|---|---|
| H1. 소수의 큰 끝단 이상치가 OLS 초기값을 끌어당긴다 | 작성자 공개 진단과 일치한다. geometry 합성에서는 90열 중 84열이 같은 직선이고 끝 6열만 80픽셀 이동해도 초기 keep가 24열로 줄어 None이었다. | 같은 프레임의 `(column, run_start, run_end)`와 최초 residual만 있으면 된다. 넓게 분포한 다수점의 단일 직선이 있고 robust 후보에서 안정적으로 복원되는지 본다. 다수점 자체가 곡선·계단·여러 경계라면 H1만으로 설명하기 어렵다. |
| H2. ROI 끝을 물리 경계로 받아들인다 | crop 마지막 299행에서 run이 계속되면 실제 lower-edge 대신 crop 끝이 나올 수 있다. geometry 합성에서 실제 edge slope +0.04와 −0.04가 모두 slope≈0, centre299, 90 inlier로 반환됐고 트래커 `available=True`였다. | 선택 run이 ROI 끝에 닿는 열 수, 300행의 색 연속 여부, crop 밖 같은 full RGB의 실제 경계 위치를 확인한다. 실제 경계가 ROI 안에 있고 바로 다음 행에서 색 띠가 끝나며 전체 열에서 같은 물리 경계를 고른다면 이 설명에 불리하다. |
| H3. 검출은 타당하지만 자세/기준 전이가 참조를 계속 초기화한다 | `BeamEdgeTracker`는 issued servo signature 변화·unloaded 상태·큰 delta 반복에서 참조를 초기화한다. 즉 동일한 timeout 이름이 항상 line fitting 실패를 뜻하지 않는다. | 프레임 capture 시각·servo signature·loaded-by-command·`resets/no_edge/rejected`·reference sample 시각을 같이 본다. 안정 자세이고 `no_edge`만 증가했다면 H3보다 H1 같은 추출/적합 실패가 우선이다. H2의 합성 false acceptance는 성공한 line의 crop 접촉률로 별도 확인한다. |

H1은 **이미 공개된 문제의 합성 보강**이며 새 발견으로 세지 않는다. H2의 실제 코드 합성 반례는 geometry 검토의 신규 발견이다. 이 연구는 그 실험을 별도로 한 번 더 센 것이 아니다. H2가 실제 `d5ca2ec3` timeout을 일으켰다고도 주장하지 않는다. clipping은 오히려 성공 판정을 만들 수 있기 때문이다.

### 낮은 RMS가 잘못된 질문의 답일 수 있다

299행에서 잘린 한 열은 “lower-edge의 좌표가 299”라는 점 관측이 아니다. full image를 아직 보지 않았다면, 최소한 그 run의 실제 마지막 행이 299 이상이라는 **부분 제약**이다. crop 안에 실제 색 전이가 없는 점을 직선의 정확한 샘플로 취급하면 90개의 같은 오답이 완벽한 직선을 만든다. 이 경우 robust estimator도 올바르게 그 오답의 합의를 찾는다.

이는 **센서 원천의 비관측성과 소프트웨어가 관측을 잘라 버린 경우를 구별해야 한다**는 뜻이다. 합성 반례의 실제 edge는 full RGB 안에 있으나 선택 ROI 밖에 있다. 카메라 위치/FOV를 바꾸지 않고 기존 full frame의 다음 행을 확인하면 이 합성 쌍의 crop censoring과 mask 종료가 구분된다. 이것은 색 마스크의 연속 여부이며, 원하는 실제 beam과 같은 물체의 경계인지까지 한 행으로 인증하는 것은 아니다. 실제 frame 밖으로 완전히 벗어난 경우에는 같은 분석이 새로운 정보를 만들지 않는다.

`y=299`인 모든 검출을 버리는 것도 충분한 해결책이 아니다. geometry의 정상 대조에서는 실제 경계가 정확히 299행이고 300행은 배경이다. 같은 반환 좌표라도 다음 행의 실제 전이가 다르므로 정상 경계와 crop censoring을 구별해야 한다.

참조 획득 지표는 `available` 빈도만으로 충분하지 않다. 같은 프레임에서 실제 boundary transition 확인 여부, crop 접촉률, 지지 열의 가로 분포, 경쟁 직선 간 slope 차이, 참조 유지 시간을 따로 보아야 한다. 이들은 검토용 진단 후보이며 gate 완화나 특정 새 문턱을 결정한 것이 아니다. 객체가 둘이면 더 많은 inlier를 가진 직선이 원하는 beam일지도 별도 문제다.

## 3. 위치 추정 과신: 법선 방향 표준편차는 오차 모델이 맞을 때 의미가 있다

[v98 look-around margin](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/zone_pair_highpose_lookaround.py#L13-L24)은 벽 법선 방향의 covariance를 사용한다. 방향별 불확실성을 쓰는 이유는 타당하다. 예를 들어 두 합성 covariance가 mm² 단위로 `diag(100,1)`과 `diag(16,16)`이고 위험 법선이 y라면, 첫 후보는 총분산이 더 크지만 필요한 방향의 σ는 1 mm로 두 번째의 4 mm보다 작다. 따라서 `trace(Σ)` 감소만으로 유용한 재관측을 고를 수 없다.

다만 작은 `sqrt(nᵀΣn)`가 정확한 현재 위치를 보증하지 않는다. 법선 clearance를 `D=d̂+nᵀe`, `e~N(0,Σ)`로 모델링한 **한 half-space의 조건부 계산**에서는

\[
P(D<0)=\Phi\!\left(-\frac{\hat d}{\sqrt{n^T\Sigma n}}\right).
\]

이 관계는 평균이 틀리거나 covariance가 오차를 반영하지 않으면 그대로 사용할 수 없다. [Blackmore–Ono 2009](https://groups.csail.mit.edu/mers/old-site/papers/BlackmoreOnoGNC09.pdf) §III–IV는 Gaussian/선형 가정, 개별 projected variance, 전체 제약을 위한 별도 risk allocation을 명시한다. 현재 코드의 `min(...)`, cap, group start relief가 그 논문의 확률 bound를 구현한다고 주장하지 않는다. 기존 2011년 인용의 전문은 이번에도 확인하지 못했고, 위 원문은 별도의 2009년 논문이다.

공개된 44/2.6≈17이라는 비율을 “17σ tail probability를 측정했다”로 바꾸면 안 된다. `std_xy`는 단일 signed error의 σ가 아닐 수 있고, 하나의 선택된 실패만으로 calibration curve나 전체 NEES 분포가 나오지 않는다. **이 witness가 말하는 것은 좁은 추정과 큰 평가 오차가 함께 보고됐다는 것**이다. 평가 정답을 제어기에 추가하는 해결책은 현재 계약 밖이다.

### 경쟁 설명을 가르는 작은 표

| 설명 | 허용 자료에서 볼 수 있는 것 | 반증 또는 한계 |
|---|---|---|
| G1. 적은 실제 업데이트, 잘못된 연관, 한 방향만 관측된 상태에서 posterior가 수축했다 | unique accepted frame 수, 열/벽별 residual, 사용한 자연 경계의 방향, 마지막 update 시각, 입자 support와 covariance의 전후 변화를 같은 command epoch에 묶는다. | 여러 방향의 서로 다른 자연 특징이 정확한 projection model 아래 일관된 residual을 보였는데도 오차가 계속 일정하면 이것만으로 부족하다. 낮은 residual 하나도 잘못된 map correspondence를 배제하지 못한다. |
| G2. 시간 정렬 또는 camera/map/issued-pose 모델의 공통 bias다 | capture 시각과 추정 propagation 시각, pose/calibration hash, 해당 capture에 유효한 issued posture, pan/arm 전후 residual의 부호·방향을 비교한다. | 서로 다른 posture·시각·자연 벽에서 공통 오프셋이 사라지고 오차가 순수 관측 약한 방향에만 남는다면 bias 설명은 약해진다. issued posture는 실제 관절 측정이 아니라는 한계가 남는다. |

기존 admissible RGB와 명령 로그로 두 설명의 예상 residual 패턴을 대조할 수 있다. 정답 없이 calibration의 절대 정확도를 완전히 증명할 수는 없다. 이미 별도로 허용된 평가 정답이 있는 연구 결과를 쓸 때에는 평가 경로에만 남기고, 여기서는 그 raw를 새로 열지 않았다.

과신 문제에 covariance inflation을 무조건 붙이면 guard가 더 보수적으로 막힐 수도 있다. 반대로 guard를 줄여 통과시켰다고 추정 bias가 사라지는 것도 아니다. 다음 구현 판단에 필요한 것은 **추정 오류의 발생 지점과, guard가 사용한 raw clearance·margin·최초 거부 sample의 연결**이다. 0d7c5eb3 이후 실제 접근 결과는 별도로 확인해야 한다.

## 4. 관측 동작은 다음 결정의 경쟁 설명을 가를 때 가치가 있다

[ACE-NBV, CoRL 2023](https://arxiv.org/html/2309.09556v2)는 scene reconstruction만 늘리기보다 다음 grasp에 유리한 관측을 고른다. [ATAP, 2026-09 preprint](https://arxiv.org/html/2609.23504v1)는 예상 affordance의 실제 관측 verification와 여러 위치 가설의 disambiguation을 분리한다. 둘 다 RGB-D, robot pose/3D geometry와 학습 모듈을 이용하므로 현재 OpenCV own-RGB 경로에 그대로 이식할 수 없다. ATAP의 score softmax나 surrogate likelihood도 UGRP의 실제 calibrated probability가 아니다.

가져올 수 있는 원리는 다음과 같다. **같은 `look_around`라도 다음 거부 이유에 따라 가치가 달라진다.** HIGH에서 crop 끝을 이미 full frame으로 구분할 수 있으면 먼저 영상 분석이 충분하다. 허용된 다음 관측이 어떤 자세에서도 같은 잘린 band만 보여 준다면 frame 수 증가만으로 edge slope가 식별되지 않는다. 반대로 map-normal 위치가 문제라면 beam-relative slope가 더 정확해져도 벽까지의 절대 clearance를 해결하지 못할 수 있다.

`own_beam_edge`의 측정은 기준 이후 **robot-minus-beam relative yaw의 변화**다. 로봇과 beam이 같은 각도로 함께 도는 세계 기준 공통 회전은 이 상대 측정만으로 구별되지 않는다. beam만 회전하고 로봇이 그대로 있으면 상대 yaw가 변하므로 이와 다르다. 따라서 reference timeout 해소, relative tracking 안정화, absolute navigation 확보, 실제 운반은 서로 다른 검증 대상이다. slope reference를 두 개 얻었다는 사실을 초기 절대 정렬의 독립 검증으로도 쓰지 않는다.

[Blackmore–Williams 2006](https://groups.csail.mit.edu/mers/old-site/papers/Blackmore-Williams-CDC06-paper.pdf)은 입력을 경쟁 model의 구별과 연결한다. 여기서는 그 Bayes risk 수치나 optimizer를 구현하지 않고, 두 설명이 예측하는 **허용 영상상의 차이**를 먼저 적는 운영 원리만 적용한다.

| 다음 결정 | 실제로 줄여야 할 모호함 | 그 결정에 직접 연결되지 않는 지표 |
|---|---|---|
| HIGH reference를 받아들일지 | 실제 beam lower transition인지, 같은 물리 경계인지, crop censoring인지 | inlier 수·RMS·edge_seen 단독 |
| 현재 guard 앞에서 어떤 관측이 필요한지 | 제한 벽 법선과 yaw lever 방향의 위치/자세 오차, 모델 bias인지 약한 관측인지 | 전체 covariance trace·총 corner 수 단독 |
| blind 기억을 아직 적용할지 | 확인 이후 허용 명령·시간/segment 경계와, 기억에 없는 외부 변화의 가정 | fresh timestamp 또는 두 distinct frame만으로 얻은 포괄 신뢰도 |
| 통신이 추가 관측 선택에 도움을 줬는지 | 실제 메시지가 이전에 없던 조건 차이를 전달했고, 현재 허용 행동이 그 차이에 반응했는지 | message 수·길이, 정책 성공률 하나만으로 추정한 정보 매개 비율 |

정보를 얻는 동작도 실행이다. [PAMPC](https://rpg.ifi.uzh.ch/docs/IROS18_Falanga.pdf)는 시야와 image-plane velocity를 행동 목적과 함께 다룬다. 이 논문은 perception을 soft cost로 넣으며, 손목 로봇의 safety theorem이 아니다. UGRP에서는 실제 허용된 idle/look 권한과 기존 guard 안에서 가능한 선택만 후보가 된다. grasp 중 임의 팔 흔들기, 감시 신호를 새 mandatory gate로 바꾸기, 측정 관절/GT/타 로봇 영상을 입력으로 넣기는 이 분석의 권고가 아니다. 선택 가능한 관측이 없다면 그 조건에서 “관측으로 회복 가능”이라고 결론 내릴 근거도 없다.

## 5. hover 두 프레임과 22.14초의 정확한 의미

[blind close 모듈](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/0d7c5eb3ca3643ead2a0b50dd133a1188f06f572/harness/zone_pair_highpose_blind_close.py)은 hover에서 서로 다른 두 프레임, unchanged preclose check, 3 mm lateral check를 요구한다. 이후 fixed descent와 command envelope, segment, frame 기준 age, track sigma/anchor age를 검사한다. 이는 무제한 오래된 영상 재사용과 다르며 이미 구현된 보호 조건을 누락해서는 안 된다. 같은 소스가 partner nudge는 blind window에서 검출할 수 없다고 명시한다.

**두 distinct frame은 시간상의 중복을 줄이는 조건이며, 독립 잡음 두 표본의 통계 보장은 아니다.** 예시로 같은 분산 σ²와 상관 ρ를 가진 두 오차의 평균 분산은 `σ²(1+ρ)/2`다. ρ=1이면 감소하지 않는다. 실제 구현은 평균 추정기가 아니라 두 번 통과 gate이므로 이 식을 그 코드의 confidence 값으로 쓰지 않는다. 단지 frame ID가 다르다는 사실만으로 `sqrt(2)`의 정확도 개선을 주장할 수 없다는 수학적 설명이다.

22.14초는 source의 descent/settle+close wait+ramp+grid slack에서 나온 **운영 허용 시간**이다. 기억이 그 시간 동안 물리적으로 참이라는 증명은 별개다. 예를 들어 초기 lateral error bound가 ε₀이고, blind 구간에서 실제 상대 이동속도 bound가 v, 회전속도 bound가 ω, 관련 lever가 ℓ이면 단순한 최악 조건은 `ε₀+(v+ℓω)Δt`로 자란다. 이 bound들의 실증 근거가 없으면 운영 시간만으로 물리 error bound를 얻을 수 없다. 이것은 새 장애 재현이 아니라 코드가 이미 인정한 한계의 결정적 의미다.

따라서 공개 실행의 r1 11.4초/r2 1.4초 blind 시간을 합쳐 평균만 내기보다 로봇별 확인 capture→자기 descent 완료→짝 대기→close GO 시각을 보존하는 것이 해석에 유용하다. partner가 보낸 메시지도 과거 자기 관측에 관한 증언인지, 현재 물리 상태를 보장한다고 주장하는지 구분한다. 현재 no_comm의 고정 상태 채널·grip monitor record-only 계약은 그대로 두며, 새 contact/성공 판정을 소급해 제어 입력으로 사용하지 않는다.

## 6. 추가 구현 전에 확인할 수 있는 가장 작은 자료 묶음

이미 있는 공개·허용된 자료에서 다음 연결이 확보되면 대규모 새 실험 없이 다음 수정의 대상이 좁아진다. raw 재처리나 실제 실행을 이번 메모가 수행했다는 뜻은 아니다.

1. **한 HIGH 프레임의 검출 경로:** full-frame 식별자, ROI run 끝, 300행 연속 여부, OLS 최초 residual, 채택 열의 가로 범위. H1의 잘못된 None와 H2의 잘못된 success를 같은 함수 교체의 양쪽 acceptance 사례로 구분한다.
2. **한 최초 guard 거부의 연결:** 실제 사용한 code SHA, capture/propagation 시각, 후보 명령, limiting geometry pair, raw clearance와 공분산 margin. 0865의 과거 9.0초 로그를 최신 0d7c5e 궤적으로 재명명하지 않는다.
3. **한 blind close의 증거 수명:** hover 두 frame ID/capture time, 마지막 기준, own command envelope 유지, 짝 대기 길이, 확인되지 않은 외부 변화 가정. 성공한 단계 사례가 그 가정을 모든 장면에서 검증한 것은 아니다.

수학 예시는 `research-math-checks.py`와 `research-math-results.json`에 별도로 남겼다. 계산은 crop 밖 두 직선, 법선 방향 variance, 두 오차의 상관, 가상 Gaussian bias를 다룬다. UGRP 성능·실제 collision probability·calibration 추정·신규 물리 실험 결과가 아니다.
