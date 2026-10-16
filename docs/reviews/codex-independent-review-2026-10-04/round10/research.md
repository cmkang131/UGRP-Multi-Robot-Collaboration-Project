# 현재 uncertainty 판별과 dialogue 주장 범위

첫 감사는 현재 제어 중단의 판별 순서, 둘째는 대화 지표에서 연구 주장으로 넘어갈 때의 증거 의무를 다룬다. 새 버그 수나 실제 인과 효과 추정으로 합산하지 않는다.

# R10 — 현재 uncertainty 중단에서 먼저 구분할 것

**다음 판별의 우선순위는 실패 tick의 gate 이유 → 실제로 소비된 관측 → 수치 갱신과 informative fix의 차이 → 남은 기하·모델 가설이다.** `POSE_UNCERTAIN`, 영상 수, 마지막 성공 quality 하나만으로 실패 원인을 고르면 이 순서의 서로 다른 사건을 섞게 된다. threshold를 낮추거나 새 물리 실행을 제안하는 문서가 아니다. 현재 own-input 기록으로 알 수 있는 범위와 기록이 부족한 범위를 고정한다.

검토 source는 PR #363 `6727751b49ce11fb62234bb97274137f22850765`이며 `de03fe87d08879abefaa7dac67c7ff313df5df89`의 변경은 README뿐이다. 아래 구현 근거는 `../round9/pr363-source/harness/`의 해당 source다. 최신 공개 DEV 보고와 독립 fixture를 실제 raw trajectory 검증으로 합치지 않는다. own wrist RGB, static map, own issued commands, actual messages 계약을 유지하며 GT·측정 관절·접촉·성공 여부를 제어 진단 입력으로 추가하지 않는다.

## 1. 현재 막힌 위치와 아직 모르는 것

작성자의 de03 공개 README 보고에서는 dock→raise_high 경로가 r2의 입장 실패에서, align_to_carry 경로가 carryGO 이후 r1의 loaded uncertainty에서 멈춘다. 과거의 OLS 전부 거부/edge reference timeout은 현재 blocker가 아니다. 공개 요약은 [frontier-de03-public-update.md](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/blob/de03fe87d08879abefaa7dac67c7ff313df5df89/experiments/2026-10-03-pair-carry-highpose/README.md)에 고정했다.

| 경로 | 공개된 사실 | 여기서 결론낼 수 없는 것 |
|---|---|---|
| dock→raise_high | r2 look 종료7.8s, 입장101회 `SELF_UNCERTAIN`, σxy65.2→78.5mm, r1 rendezvous timeout12.85s | 101회가101개의 독립 관측/추정 실패라는 해석. 현재 50mm는 unloaded gate 회복 low 경계이며 모든 tick의 단일 high 판정값이 아니다. |
| align_to_carry | edge reference88.9s, carryGO89.1s, r1 `POSE_UNCERTAIN`92.2s; 거부 시점 r1 σ 값 미기록이라고 작성자가 명시 | σxy와 σyaw 중 어느 값이 넘었는지, 새 PF 감쇠가 원인이었는지, edge fit 성공이 absolute pose를 회복했는지. |

SELF_UNCERTAIN과 POSE_UNCERTAIN은 모두 복합 판정 이름이다. admission은 `readiness_snapshot()`의 `failed_checks`를 먼저 읽어야 한다. gate 외에도 report 초기화·freshness·유한 σ·observation freshness·servo completeness 등이 있다(`zone_pair_admission.py:7–63`). `fix_age_s`는 이 admission receipt의 설명용 값이며 새 admission threshold가 아니다.

`LOOKED_POSE_UNCERTAIN`의 `failed_checks`는 이 admission 목록과 다르다. look 완료의 목록은 accepted-fix 검사만 담으므로, fix는 수락됐지만 gate가 uncertain인 경우 빈 목록일 수 있다. 빈 목록을 “모든 제어 판정 통과”로 읽지 않는다. frontier의 `uncertainty-fault-tree-repro.py` (Mac 전달본 증거)과 `uncertainty-fault-tree-result.json` (Mac 전달본 증거)가 이 대조를 포함한다.

loaded carry에서는 `_pose(now)` 유효성, 현재 high σ, `gate.ok`의 이력 등이 같은 `POSE_UNCERTAIN`에 모인다(`zone_pair_guards.py:502–577,619–796`). 순수 hold, approach, reobserve, relative manipulation은 경로가 다르므로 이름만 같다고 같은 분기를 비교하지 않는다. current b-v6g는 beam_relative가 꺼진 경로다. 정확한 분기·profile·dwell 우선순위는 [frontier의 소스 감사](pose.md)와 함께 읽는다.

unloaded gate의 high는80mm/0.10rad, low 회복은50mm/0.06rad와0.4s dwell이다. loaded high는70mm/3°다. 따라서 공개 dock σ65.2–78.5mm가 high80mm보다 작다는 사실만으로 gate가 열려야 한다고 주장할 수 없다. 이전 불확실 상태에서 low 회복을 하지 못하면 중간 범위에서도 gate는 닫힌 채일 수 있다. 반대로 이 수치만으로 실제 모든 admission의 실패 predicate가 gate 하나였다고 확정하지 않는다.

## 2. 이미지, PF 갱신, fix 영수증은 세 사건이다

실제 wrapper의 순서는 `quality 계산 → 원본 apply_scan의 likelihood/weight 갱신 → informative이면 fix clock 유지, 아니면 clock 복원과 measured=False`다(`zone_final_pair_scan.py:14–49`). 마지막 단계는 앞선 수치 갱신을 취소하지 않는다. quality의 `posterior_support`라는 이름도 이번 scan 반영 후 posterior가 아니라 **그 scan 직전 pf.logw가 나타내는 belief의 지지 질량**이다. source도 scan 수나 좁은 posterior 자체를 새 absolute fix로 취급하지 않는다고 설명한다. 이는 partial information을 사용할 수 있으면서 full fix 인증은 보류하는 의미이며, 그 자체를 새 구현 결함으로 집계하지 않는다.

`scan-receipt-results.json` (Mac 전달본 증거)은 실제 interval likelihood, quality, PF consistency, RobustPF scan과 resample 경로에 authored27개 particle과 선형 expected rows를 넣은 독립 source fixture다. 실제 RGB·지도·위치오차 실험은 아니다. 아래 covariance 숫자는 fixture가 명시한 weighted-population estimator의 값이며 production PoseReport의 σ/cov 계산을 재현한 값이 아니다. [scan-receipt-semantics.md](vision.md)에 source와 반증 대조를 자세히 적었다.

| source fixture | 현재 quality | 수치 결과 | fix 의미 |
|---|---|---|---|
| rank1인6열, 이전 fix 없음 | accepted=True, informative=False, curvature=0 | scan_updates1; ESS27→24.40086; x 분산0.00166667→0.00128203 | last_fix_t 없음, 반환 measured=False |
| full-rank인6열 | informative=True | 원본 PF 수치 갱신 | t10에 fix 발생 |
| 그 다음 t10.5 rank1 관측 | 현재 informative=False | 갱신은 계속 가능 | 마지막 성공 quality는 True/t10을 유지, 실제 facade의 fix_age=0.5s |
| usable support 없는 대조 | current quality 없음 | 해당 scan 갱신 없음 | fix age만 진행 |

따라서 **`measured=0` 또는 fix 나이 증가를 “영상이 오지 않았다”, “PF가 영상을 전혀 반영하지 않았다”로 번역하면 안 된다.** 반대로 scan_updates 증가만으로 세 축을 재식별한 새 fix라고 말할 수도 없다. fixture 내부 update 반환의 오래된 since_scan 값은 실제 facade가 재계산하므로 외부 freshness 오류로 승계하지 않는다.

## 3. 무엇이 저장되고 무엇은 메모리에만 있는가

아래는 검토한 writer의 범위다. 별도 파일에 같은 데이터가 있는지는 그 파일을 실제로 확인해야 한다. 이 표는 공개 raw가 완전하다는 가정도, 모든 입력이 영구히 사라졌다는 가정도 하지 않는다.

| 필요한 증거 | source에서의 의미 | 현재 확인된 보존 범위 |
|---|---|---|
| admission `failed_checks`, gate profile/state/후보 시작 시각, report σ와 age, 관측 frame/age | 입장 판정의 직접 근거 | `zone_pair_admission.py:20–63`; `Runtime.record()`의 robots.admissions에 보존 |
| `pose_uncertain` 전이 이벤트 | gate가 uncertain에 들어간 사건 | `zone_own_executor.py:241–246`에는 level/profile/σxy가 있으나 σyaw/full report가 없음. 매 uncertain tick의 snapshot도 아님 |
| provider counts·localizer_stats | frame/worker/측정과 PF 작업의 집계 | `vision_pose_source_p03.py:294–306`의 record에 있음. 종료 집계 하나는 실패 직전의 증가분을 복원하지 못함 |
| report `last_fix_t`, `fix_age_s`, diagnostics, `last_fix_quality` | 현 시점 추정과 마지막 성공 receipt | 런타임 PoseReport에 존재. 이를 매 tick 저장하는 writer가 있다고 추정하지 않음 |
| PoseReport `cov` | x/y/yaw 공분산 행렬 | dataclass에는 있지만 `owncam_pose_source.py:53–61`의 as_dict에는 빠짐. 저장된 σ 두 개만으로 주축·교차항 복원 불가 |
| `pf.v3_scan_quality` | 이번 scan의 accepted/informative/support/curvature | wrapper 메모리 값. report의 `last_fix_quality`와 다름. 이번 quality 전체의 시계열을 record가 자동 보존하지 않음 |
| 지연 wrapper의 captured/available/consumed 시각 | 관측의 세 시각 | `zone_study_pose_delay_p03.py:130–142`에서 timing에 추가하나 `record():189–195`는 timing을 직렬화하지 않음. frame_rejections는 저장 |
| edge available와 level_frames | relative yaw/fallback 선택의 가용성 | 해당 tracker/cfg 런타임 값과 source record 범위를 구분. available=True만으로 관측 정밀도나 absolute fix를 인증하지 않음 |

`Runtime.record()`는 pair records와 robots의 events/jobs/admissions/provider record를 저장한다(`zone_final_pair_runtime.py:83–87`). `PairExecution.save`의 input receipt는 frame_id/hash/time/phase이고 pose trajectory 자체가 아니다. collision guard의 상세 estimate 기록을 일반 POSE_UNCERTAIN 사건에 자동 적용해서도 안 된다.

마지막 성공 snapshot은 특히 주의해야 한다. `vision_pose_source_pair_v3.py:140–144`가 내보내는 `observation_quality.informative`는 **마지막 성공 fix의 quality**를 가져온다. 최근의 약한 scan이 False인데 이 값이 True인 상태가 위 실제 fixture에서 성립한다. p03 report의 `accepted`도 `last_fix_t == report 시각` 비교이므로 현재 camera frame의 일반적인 acceptance 변수처럼 읽지 않는다. `informative_columns`는 마지막 성공 `last_obs`의 열 수다.

## 4. 경쟁 설명을 좁히는 판별표

이 표의 가설은 서로 배타적이지 않다. 먼저 판정 분기를 고정한 뒤 동일 시간 구간의 관측·command 이력에 연결해야 한다. M 표시는 해당 값이 메모리에 존재하지만 검토한 record가 그 시계열을 보장하지 않는다는 뜻이다. D는 기존 허용 RGB/모델 상태로 계산 가능한 분석량이며 현재 저장 필드라고 주장하지 않는다.

| 후보 설명 | 최소 판별 | 지지하는 패턴 | 이 설명을 약화시키거나 반박하는 대조 | 남는 한계 |
|---|---|---|---|---|
| A1. 필요한 시점에 frame이 provider에 전달·소비되지 않았다 | 관측 frame/time, rejection 사유; 지연 captured→consumed(M) | release 전 대기, 지연 wrapper에서 오래된/중복 frame 거부 | 같은 구간에 새 capture가 provider.on_frame에 전달된 기록이면 “미소비” 설명 반박 | 새 frame 수와 새 시점/독립 정보 수는 다름 |
| A2. frame은 소비됐지만 적용 가능한 scan update까지 도달하지 못했다 | Δframes/worker/scan, initialized/settled 상태, rejection·usable column 수 | frame 수는 증가하나 unsettled/uninitialized로 worker 생략, observer 거부, usable support 미달 등으로 scan 미적용 | 해당 frame의 scan_updates 증가이면 “미적용” 설명 반박 | delayed.timing의 consumed는 likelihood 적용을 뜻하지 않음. 각 생략 분기는 구분해야 함 |
| B. scan은 반영됐지만 full fix 조건에 못 미쳤다 | Δscan_updates, 이번 quality(M), last_fix_t; full-rank 대조와 현재 지원 축 | scan_updates 증가, fix 시각 정지, 이번 informative=False. rank1 fixture가 가능한 사례 | 같은 tick의 current quality informative=True와 fix 시각 갱신은 “fix 미발생” 반박 | 왜 quality를 못 넘었는지는 support·saturation·curvature를 각각 봐야 함 |
| C. prediction/motion 불확실성 누적이 유효 감소량을 앞섰다 | 동일 시각에 정렬한 σ/공분산(M), own issued command, fix/scan 이력 | predict 구간에서 증가, scan 직후 일부 축 감소에도 gate 실패 | scan이 전혀 없다는 단정은 B fixture로 반박. 공분산이 낮아졌는데 실패했다면 gate 이력/다른 predicate 우선 | command는 실제 이동 측정이 아님. 종료 σ 두 점만으로 process와 measurement 기여 분해 불가 |
| D. 관측 모델에서 여러 pose 후보가 구별되지 않는다 | particle 위치·weight/cluster(M), 현재 likelihood 대비와 mode별 support(D), local curvature(M) | 서로 떨어진 후보군이 같은 자기 영상에 양립; local curvature가 좋아도 전체 분산은 큼 | 같은 모델/주어진 prior 범위에서 하나의 좁은 지배 mode이고 다른 후보의 likelihood가 명확히 나쁘면 그 범위의 다중-mode 설명 약화 | PF가 이미 버린 mode의 부재는 관측의 전역 식별성 증명이 아님 |
| E. segmentation/캘리브레이션/동작 모델의 체계적 불일치 | actual RGB의 column별 residual·mask 지지 위치(D), 이번 support/saturation(M), issued pose/load 전환 | 반복되는 같은 부호/영상 위치의 잔차, 전환 후 호환성 상실 같은 구체적 패턴 | 지목한 모델 오차가 예측한 패턴이 허용 관측에 없으면 그 좁은 가설 약화 | residual이 작아도 common bias와 pose가 상쇄될 수 있음. 자기 관측만으로 모든 bias나 실제 pose error를 식별할 수 없음 |
| F. 상대 yaw edge가 available이지만 angular leverage가 약하다 | accepted inlier span/Sxx(D), fit RMS/count, dyaw/available, fallback level | 같은 count/RMS에도 좁은 span에서 boundary perturbation 민감도 큼 | 지지 span·잔차 구조가 유지되면 “span 변화” 가설 우선순위 감소 | relative yaw 정보가 약하다는 것과 실제 loaded gate 거부 원인은 별개. xy fix를 직접 보장하지 않음 |
| G. 현재 σ보다 gate 이력·stale/invalid 조건이 직접 거부를 결정했다 | 실제 branch, gate.ok/profile/candidate_since/last_update, report age, failed_checks | σ가 중간 범위인데 이전 uncertain 상태가 남음, 또는 pose가 stale/invalid | 현재 state/profile/dwell이 모두 OK이고 직접 high 비교에서 거부되면 이 좁은 설명 반박 | 최상위 reason 문자열 하나로 이 정보를 복원할 수 없음 |

이 표에서 A1/A2와B가 가장 값싼 첫 대조다. 모두 같은 `measured` 감소/old fix처럼 보일 수 있으나 조치의 의미가 다르다. A1에는 frame 전달·소비 시각을, A2에는 소비 후 settle/observer/usable support 생략을, B에는 실제 적용한 scan의 기하 조건을 봐야 한다. D와E는 같은 residual/support 패턴을 만들 수 있어 허용 로그만으로 완전히 분리되지 않을 수 있다. 이런 경우 “원인 미식별”이 정직한 결과다.

기존 admission receipts가 있으면 checks→gate history→last_fix/frame age 순서로 분석할 수 있다. carry 거부 tick에 해당 상태가 기록되지 않았다면 이 문서는 원인을 채워 넣지 않는다. 가장 작은 향후 진단 기록은 **이미 제어기에 있던** branch id, profile/gate state, σxy/σyaw, report와 fix 시각, consumed frame id, 이번 quality와 마지막 quality를 같은 tick에 구분해 남기는 것이다. 아직 구현하거나 새 실행을 요구한 것이 아니다.

## 5. local curvature·ESS·edge 성공에서 바로 얻을 수 없는 결론

현재 fix quality는 residual support, inlier 비율, saturation, 최선점의 수치 local curvature를 결합한다(`owncam_recovery_v6.py:21–46,69–89`; `zone_final_pair_scan.py:14–29`). source는 threshold가 development hypothesis이며 calibrated coverage가 아니라고 명시한다. 여기서 curvature는 m/rad 좌표에서 negative log-likelihood 유한차분 Hessian의 최소 고유값을0 아래에서 잘라낸 값이다. 따라서0은 rank deficiency뿐 아니라 음의 local curvature도 합쳐 나타낼 수 있으며, 실제0 로그를 rank1이라고 단정하지 않는다. 다른 좌표계·측정 모델의 보편적 정보량 문턱으로 옮기지 않으며 기존 threshold를 바꾸지 않는다.

두 짧은 수학적 대조는 위 해석의 경계만 설명한다.

* 동일 가중 particle4개의 위치가 모두0이거나, −0.1 두 개와+0.1 두 개이면 두 경우 ESS는 모두4다. weighted x 분산은 각각0과0.01m²다. ESS는 가중치 집중도이지 공간 분산/실제 위치오차 자체가 아니다. 현재 resample은 logweights를 균등화하므로 post-resample n_eff 하나로 “particle depletion 없음”이나 정확도를 인증하지 않는다. 필요할 때는 source의 `ess_pre`와 resample/injection 사건도 구분한다.
* 스칼라 likelihood가 두 Gaussian의 동일 가중 혼합이고 중심이±a, 각 분산이s²이면, 양쪽 mode 주변 local curvature는 a/s가 클 때 약1/s²인 반면 전체 분산은 a²+s²다. 이는 “각 mode가 날카롭다”와 “하나의 pose로 전역 식별된다”가 다른 명제임을 보이는 해석용 식이다. 실제 UGRP likelihood가 이런 혼합이라고 가정하거나 현재 실패의 mode 개수를 추정한 것이 아니다.

상대 yaw edge는 또 다른 정보원이다. [edge-support-geometry.md](vision.md)의 원본 tracker fixture는 count27/RMS0.274482가 같아도 support span104px와312px에서 같은 authored boundary 변화에 대한 yaw increment가3배 달라짐을 보였다. IID noise나 실제 yaw error를 측정한 결과가 아니다. 현재 `HighPoseSource.on_frame → owncam_carry_v6e.update_availability`는 edge available의 이진값과 pair 가용성/hold로 fallback을 선택해 extra yaw std를 설정하며 span/Sxx는 직접 입력하지 않는다(`owncam_carry_v6e.py:258–275`). edge reference 성공을 곧 absolute xy 정밀도 회복으로 번역하면 안 된다. 이 관찰 또한 source가 약속하지 않은 정밀도 보장을 위반한 새 버그가 아니다.

## 6. 이 검토가 현재 줄 수 있는 결론

de03의 공개 carry 결과는 **loaded uncertainty 경계에 도달했다**는 단계 진전이다. 원인별 분산 기여나 true error를 보고하지 않았으므로 PF consistency가 실패를 만들었다거나 edge robustification만으로 문제가 해결됐다고 결론내릴 수 없다. 현재 가장 실용적인 정보는 숫자 threshold 변경안이 아니라, 저장된 admission 체크를 먼저 쓰고 carry의 누락된 동일-tick 판정 근거를 구분하는 위 판별 순서다.

이 문서는 새 primary paper 요약을 늘리지 않았다. 새 근거는 현재 원본 source, 허용된 synthetic source fixture, 명시 가정의 두 해석용 수식이다. 기존 R8의 bias/coverage 논의와 R9의 equicorrelation likelihood 검토를 실제 trajectory의 원인 증거로 재사용하지 않는다.

독립 검토: frontier는 현재 policy의 gate 분기·이력과 공개 상태 경계를, geometry는 quality·fix·edge 연결을, evaluation은 source 의미와 두 수식의 적용 범위를 확인했다. 초기 초안에서 frame 미소비/소비 후 scan 미적용을 분리하고 support가 scan 이전 belief의 질량임을 명확히 했다. [독립 QA](validation.md)에 검토 범위가 남아 있다.

---

# R9 후속 — 현재 dialogue metric을 evidence use로 읽을 수 있는 범위

**현재 지표를 버릴 필요는 없다. 지표가 측정하는 대상을 그 이름 옆에 고정해야 한다.** 가장 실용적인 구분은 `발화 형식`, `transport 관계`, `실제 request에 포함`, `주장의 참/거짓`, `정책 선택에 기여`다. 이 다섯 가지를 하나의 “grounded” 점수로 합치면 원인 해석이 흐려진다.

대상은 #371 `a009112ff5fb18c6b64f58d8cd6392c58d4c028c`. 이 문서는 source-only 분석과 명시적인 논리 예시다. 실제 run의 점수·LLM 행동·새 데이터는 계산하지 않았다. `information-flow-review.md`를 이어서 실제 metric caller까지 읽었다.

## 1. 실제 구현의 의미표

| 현재 필드/함수 | 코드가 계산하는 것 | 보고에서 지켜야 할 경계 |
|---|---|---|
| `CALL_FIELDS.message_ids` / `_call_view` | **해당 call이 내보낸** 메시지 ID | 수신하거나 action의 근거로 인용한 메시지 목록이 아님. message_id를 call.message_ids에 join하면 sender의 발화 생성 관계가 만들어짐 |
| `decision_sources` | reply의 enum 목록을 call record에 복사 | 개별 observation/message ID가 아님. `CALL_FIELDS`의 설명 문자열에는 own ref/command/message ID라는 표현이 남아 있으나 현재 validator·writer는 source 종류를 저장 |
| `pair_llm_prompts_ko.py:80` | own_status를 사용하면 own_commands로 기록하라는 지시 | command history와 자체 상태의 자기보고 기여를 이 enum 하나로 구분 못함. 의도된 mapping이며 지시 누락 버그가 아님 |
| `decision_influence` (`zone_study_eval.py:1627`) | decision change 시각 앞 30 SIM s(default)에 recipient에게 전달된 발화 목록 | 이 함수의 docstring과 상위 `dialogue_metrics`의 반환 note(:1621–24)가 이미 **association only**라고 명시. request start/실제 prompt 포함/decision_sources/본문 의미를 검사하지 않음 |
| `grounds_verdict` (`:1544`) | 주어진 grounds 문자열의 허용/금지 prefix 분류 | `grounded`는 이 함수에서 허용 prefix를 인용했다는 뜻. ref 존재·이미지 내용의 지지·참/거짓·실제 인과 사용을 증명하지 않음 |
| canonical `_utterance_view` (`:379`) | message body/시간/수신자/reply_to 등을 생성 | 현재 이 변환은 grounds를 붙이지 않는다. 그러므로 위 helper의 약한 판정을 근거로 “현재 pair run이 grounded를 과다 집계한다”고 주장하지 않음 |
| `extract_claims` → `check_claim` | 추출 가능한 특정 명제를 referee와 대조 | 진실성은 별도 축이다. 모델이 그 사실을 해당 RGB에서 확인했는지, 그 사실로 행동했는지는 다름. 평가는 actor로 역류시키지 않음 |
| pilot `references_new_peer_utterance` | `zm.references`가 상대 robot ID 또는 상대가 쓴 item label의 표면 출현을 찾음 | source 의미의 채택/새 정보 획득/인과 영향과 다름. 이는 옛 pilot script이며 현재 pair runtime의 모든 통신 평가지표라고 부르지 않음 |

읽은 source: `harness/zone_dialogue_metrics.py`, `harness/zone_study_eval.py`, `harness/zone_study_contract.py`, `harness/pair_llm_prompts_ko.py`, `scripts/pilot_korean_dialogue_analysis.py`. 문서 비교: `docs/report/02-experiment-design.md:179`, `docs/design/2026-09-25-zone-dialogue-study-design-codex.md:401`의 “결정 연결” 설명. **코드가 이미 명시한 비인과 한계를 새 버그로 세지 않는다.** 개선 대상은 그 지표를 더 강한 연구 주장에 재사용할 때의 해석이다.

## 2. 실제 provenance 반례가 metric에 주는 함의

Runtime의 `runtime-protocol-repro.json`에는 call start 3.9, inbound delivery 4.1, release 8.1인 실제 scheduler fixture가 있다. 생성 prompt에는 peer ID가 없는데 그 ID를 reply_to로 낸 합성 reply가 나중에 수락된다. 별도 존재하지 않는 ID는 거절된다.

`decision_influence`가 위와 같은 8.1의 change와 4.1의 inbound를 받는다면, 기본 lookback 식 `8.1−30 ≤ 4.1 ≤ 8.1`은 참이다. 따라서 prior inbound association은 성립할 수 있다. **그 call의 생성 입력으로 메시지 내용을 읽었다는 해석은 성립하지 않는다.** 이는 함수가 의도한 association semantics와 일치하며, 이 함수의 구현 오류가 아니다. 실제 fixture에 decision_changes 로그를 추가하거나 새 점수를 산출한 것이 아니라 소스의 부등식을 적용한 논리 예시다.

분석자가 단순히 “행동 전에 도착”, “reply_to가 valid”, “decision_sources에 message”를 모두 만족해도, 실제 prompt membership이 확인되지 않으면 직접 content-use를 주장하기 어렵다. 반대로 membership이 확인돼도 다음 절의 모호성은 남는다.

## 3. 모든 기록이 같아도 사용 기제는 다른 최소 예시

가상 관측 support에서 static order의 destination과 상대 메시지의 destination이 항상 B라고 하자. 두 정책은 다음과 같을 수 있다.

- 정책 A: 메시지 destination으로 claim destination을 선택한다.
- 정책 B: static order destination으로 선택한다.

두 정책 모두 동일한 action `claim B`와 자기보고 `decision_sources=['message']`를 출력하도록 구성할 수 있다. 이 관측 support에서는 payload·action·발화·source enum이 전부 같아도 메시지를 이용하는 기제는 다르다. 모델을 바꿔 실행한 결과가 아니라 **유한 observational log만으로 자기보고의 causal faithfulness가 보장되지 않는다는 논리 증인**이다. 정책 B가 실제 UGRP 모델이라는 주장도 아니다.

이 예시 때문에 source 자기보고를 버려야 하는 것은 아니다. 다음 네 축을 별도로 보관하면 된다.

| 축 | 로그로 확인할 수 있는 것 | 미확인으로 남겨야 하는 것 |
|---|---|---|
| Reachability | final request에서 본문/ID/이미지 ref의 실제 존재 | 존재하는 입력을 내부적으로 읽고 썼는지 |
| Declared use | source enum, 명시적 reply/참조 | 사실인 causal attribution인지 |
| Evidential support | 허용된 기록이 특정 주장과 양립/불일치하는지, unknown 포함 | 문장의 유창함이 곧 센서 증거라는 주장 |
| Causal use | 현재 로그만으로 일반적으로 확정 못함 | 성공과 동시 발생했다는 이유만으로 원인으로 명명 |

참인 주장이 우연히 나올 수도 있고, 잘못된 영상 해석을 실제로 사용해 거짓 주장을 낼 수도 있다. 따라서 truthfulness와 faithful source use는 서로 대체되는 점수가 아니다. action이 바뀌지 않았다는 이유만으로 메시지가 무시됐다고도 할 수 없다: 이미 선택한 적법 행동을 확인하는 정보일 수 있기 때문이다.

## 4. 신규 primary 두 편과 적용 범위

**P6 — Alon Jacovi, Yoav Goldberg (ACL 2020), _Towards Faithfully Interpretable NLP Systems: How Should We Define and Evaluate Faithfulness?_** [공식 원문](https://aclanthology.org/2020.acl-main.386.pdf), DOI 10.18653/v1/2020.acl-main.386. 직접 읽은 범위: §§2,4,5,6의 가정 정리, §7–8 논의 일부. 이는 opinion/conceptual paper다. 설득력과 모델 기제의 충실성을 구별하고, 평가가 가정에 의존함을 지적한다. UGRP에는 평가명과 증거 의무를 분리하는 개념으로만 사용한다. 이 논문이 현재 모델의 source enum 오류율을 측정하거나 특정 사람이 한 판정을 무효로 만든다는 뜻은 아니다.

**P7 — Miles Turpin, Julian Michael, Ethan Perez, Samuel R. Bowman (NeurIPS 2023), _Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting._** [공식 최종 원문](https://proceedings.neurips.cc/paper_files/paper/2023/file/ed3fea9033a80fea1376299fa7863f4a-Paper-Conference.pdf). 직접 읽은 범위: §§1–3.1, §6 limitations. GPT-3.5/Claude1.0의 선택형 과제에 입력 편향을 주고 설명의 누락과 예측 변화를 비교한다. 저자도 이 검사가 필요조건이며 faithfulness의 충분조건이 아니라고 명시한다. 현재 Gemini·로봇·짧은 enum 자기보고에 그 수치를 이전하지 않는다. **이 리뷰는 hidden reasoning 수집이나 CoT 공개를 요구하지 않는다.** 공개 request/action/message와 source 자기보고의 분석만 다룬다.

두 원문이 지지하는 것은 “설명이 그럴듯하니 사용 근거가 입증됐다”는 추론을 피하자는 좁은 원칙이다. current UGRP의 실제 자기보고가 부정확하다는 empirical claim은 원자료나 별도 검증 없이는 하지 않는다.

## 5. 기존 로그만으로 준비할 수 있는 보고 형태

지금 단계에서 추가 실행 없이 정의할 수 있는 것은 request-level 분류표다. 예: `reported_message=true`, `message_body_in_final_request=false`, `reply_id_transport_valid=true`, `action_release_recorded=true`. 각 축을 그대로 보이면 어디까지 확인됐는지 독자가 판단할 수 있다.

실제 데이터 분석에서는 분모도 분리한다. source 자기보고는 valid reply, prompt membership은 archive가 완전한 request, action 연결은 실제 release/dispatch가 기록된 action에 대해 정의한다. missing archive를 미사용으로, unknown ground를 거짓으로 바꾸지 않는다. 서로 다른 분모의 비율을 곱해 새로운 “grounding 성공률”을 만들지 않는다.

더 강한 인과 주장은 그때의 구체적인 intervention/가정에 달려 있다. 이번 후속은 새 ablation이나 implementation을 요청하는 문서가 아니라, 이미 있는 dialogue metric을 논문에서 과도하게 읽지 않게 만드는 source-backed 해석 기준이다.
