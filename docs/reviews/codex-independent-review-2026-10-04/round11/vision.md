# Fresh receipt와 현재 HIGH observer의 범위

현재 blocker의 관측 해석을 좁히는 두 검토다. 첫 절은 새 합성 receipt 증인, 두 번째는 default HIGH의 source-only 소유권 반증이며 어느 쪽도 실제 pose error를 측정하지 않았다.

# R11 — fresh fix는 최근 receipt이며 독립 정보량의 이름이 아니다

**현재 기록에서 `fix_age_s`와 `view_scans/repeat_scans`는 다른 질문에 답한다.** 전자는 마지막 informative scan의 capture 시각으로부터 지난 시간이고, 후자는 현행 own-command/posture 기반 view 분류의 누적 수다. 같은 view의 scan을 작게 반영하면서 매번 새 fix receipt를 발급하는 것은 현재 source가 명시한 동작이다. 이를 invalid freshness나 새 버그로 취급하지 않는다.

검토 SHA는 PR #363 `6727751b49ce11fb62234bb97274137f22850765`이며 de03 README 이후 이 source는 동일하다. 현재 공개 carry 실패 원인, 실제 sensor 독립성, posterior coverage를 재분석한 문서가 아니다. R10의 [수치 갱신/fix 분리](../round10/vision.md)에 이어, **fix가 발급된 경우에도** receipt 수와 새 정보 기여가 다름을 source 경로로 확인했다.

## source가 이미 선언한 분리

`zone_pair_highpose_pf_consistency.py:28–35`는 measurement 설정을 바꾸지 않아 informative-scan gate와 measured receipt/fix_age는 등록된 의미를 유지하고, scan이 particle weights를 이동시키는 정도만 바꾼다고 명시한다. `zone_final_pair_scan.quality`는 per-feature compatibility와 scan 전 belief support, direct `vl.column_loglik`의 local curvature를 계산한다. 이 direct 계산은 PF의 wrapped `scan_loglik`에 적용되는 column/repeat 감쇠와 다르다.

실제 경로는 `view_apply → 기존 quality/apply_scan wrapper → 원본 RobustPF scan → tempered_loglik`이다. quality를 통과하면 그 capture 시각은 last_fix_t가 된다. current default rho0.5에서 repeat k의 수치 가중치는 a_k가 작아지지만, **현재 quality 조건을 만족하는 scan이라는 판정**은 그 작은 a_k와 같은 수치가 아니다. source는 독립 관측마다만 fix clock을 갱신한다고 약속하지 않는다.

`posterior_support`는 현 scan 이전 belief에 의존하므로 모든 실제 반복에서 반드시 같은 quality가 된다는 주장은 하지 않는다. 아래 대조는 이를 통과하는 명시적 하나의 경우다.

## 현재 원본 함수로 확인한 최소 대조

`fix-receipt-repetition-repro.py` (Mac 전달본 증거)는 R10의 hash 고정 source bundle과 helper를 읽고, 같은 authored full-rank6열을10.00–17.15s에0.05s 간격으로144회 적용한다. helper 정의만 읽으므로 R10 결과를 덮어쓰지 않는다. own pose/load/command는 고정이며 prediction은 time-only stub다. 원본 quality·interval likelihood·RobustPF update·consistency wrapper를 사용하고 `scan_loglik` 호출 안의 실제 alpha를 비변형 observer로 기록한다. 실제 RGB, 지도, 물리 이동, LLM 또는 held-out 실행은 없다.

| 적용 k | 실제 scan 내부 alpha | quality curvature | informative receipt | facade fix_age | view 수 / repeat 수 |
|---:|---:|---:|---|---:|---:|
| 1 | 1 | 258.823874 | True | 0s | 1 / 0 |
| 2 | 0.333333333 | 258.823874 | True | 0s | 1 / 1 |
| 10 | 0.018181818 | 258.823874 | True | 0s | 1 / 9 |
| 100 | 0.000198020 | 258.823874 | True | 0s | 1 / 99 |
| 144 | 0.0000957854 | 258.823874 | True | 0s | 1 / 143 |

실제 호출에서 기록한144개 alpha 합은1.98620689655다. 이6열 fixture의 별도 column factor는4/6이다. 이 합은 **코드의 누적 likelihood exponent**이며 실제 독립 관측 개수나 calibrated information gain으로 측정한 값이 아니다.144개 receipt가144개의 독립 정보를 뜻하지 않는다는 구현상 대조만 제공한다. R9의 equicorrelation 이론을 실제 PF의 exact posterior 보장으로 승격하지 않는다.

마지막 t17.20에 usable column0인 negative control을 넣으면 scan_updates는144에 머물고 새 receipt는 발급되지 않으며 실제 facade fix_age는0.05s가 된다. 따라서 timestamp가 무조건 매 frame 갱신되는 dummy counter인 것도 아니다. 지원되는 scan의 현재 receipt와 지원되지 않은 frame을 제대로 구분한다. 이 fixture에서는 resampling이 발생하지 않아 결과를 resampling draw 차이로 설명할 필요도 없다.

## 현재 진단에 적용할 범위

1. **최근 fix인데 σ가 높다는 상태는 모순이 아니다.** 최근 scan이 등록된 기하·compatibility 기준을 통과했다는 것과 posterior가 gate의 low 경계를 넘을 만큼 좁아졌다는 것은 다른 조건이다. 어느 실제 실패에서 이 조합이 있었는지는 그 tick의 report가 있어야 안다.
2. **fix freshness만으로 “계속 새 관측으로 충분히 교정됐다”는 설명을 인증하지 않는다.** 그 주장에는 receipt 시각뿐 아니라 current view 분류, repeat k/weight, scan 전후 추정 변화가 필요하다. 이 값들도 실제 오차나 관측 독립성의 직접 측정은 아니다.
3. **new view도 독립성 증명은 아니다.** 현재 view key는 own issued pose/load/command와 PF command odometry로 정한다. 새 명령 자체가 실제 이동을 측정하지 않으며, 다른 perspective도 공유 calibration/model bias를 없애지 않는다. 이 note는 새 threshold나 독립성 certification gate를 제안하지 않는다.
4. **scan 밖에서 읽은 `state.alpha`는 최신 적용 alpha가 아닐 수 있다.** `view_apply`의 finally는 alpha를1로 복원한다. 그래서 이 fixture는 실제 scan 호출 내부 값을 기록했다. 저장된 최종 state에서 alpha1을 보고 “모든 반복이 full weight였다”고 읽으면 안 된다. 알려진 rho와 k로 계산한 값은 computed exponent라고 표시해야 한다.

현재 provider는 counters를 집계 저장하지만 이 fixture의 매 scan 표가 기존 실제 artifact에 남아 있다고 가정하지 않는다. R10 [진단표](../round10/research.md)의 동일-tick 관측/scan/fix 구별에 **receipt recency와 marginal weighting의 차이**를 추가해 읽으면 충분하다. threshold 완화, partial/full fix 재정의, 추가 물리 실행은 여기서 요구하지 않는다.

## 재현과 경계

`round11/`과 `round10/scan-receipt-repro.py`, `round10/scan-receipt-source/` 상대 구조를 유지해 임시 폴더에 복사하고 `python round11/fix-receipt-repetition-repro.py`를 실행한다. 배포본에서 두 script가 각각 `round11/evidence/`, `round10/evidence/`에 있을 때도 helper를 찾는다. base fixture SHA256과 원본 source manifest를 검사하며 결과는 복사된 script 옆에 쓴다. Python3.12.14와 NumPy2.3.5에서 통과했다. source method 구현은 변경하지 않았다.

수치 출력은 `fix-receipt-repetition-results.json` (Mac 전달본 증거)에 있다. 이 대조는 동일 authored row/정적 latent/time-only motion이라는 좁은 구성이다. 실제 camera error의 상관, 실제 view당 pose 식별성, 현재 carry의 σ 변화량과 실패 원인은 측정하지 않았다. 논문 실험을 새로 했거나 기존 calibration/held-out 결과를 검증했다는 의미도 아니다.

---

# R10 후속 — 현재 HIGH observer의 robot/case 소유권 경계

대상: #363 `6727751b49ce11fb62234bb97274137f22850765` source (후속 `de03fe87d08879abefaa7dac67c7ff313df5df89`는 README만 변경). **이 현재 호출 경로에서는 observer 결과가 다른 robot/case로 넘어가는 결함을 찾지 못했다.** 소스의 객체 생성·직접 호출·close 경로를 대조했으며 새 image/worker/render/physics 실행은 하지 않았다.

| 의심 | 실제 source 경로 | 확인 범위 |
|---|---|---|
| 두 robot이 같은 mutable observer/PF를 공유하는가 | `zone_final_pair_runtime.py:24–38`은 robot마다 provider factory를 새로 호출하고 각 rid에 보관한다. HIGH runtime은 이 factory를 `vision_pose_source_highpose.build_provider`로 고정한다(`zone_pair_highpose_runtime.py:458–463`). | 기본 caller는 같은 object를 재사용하지 않는다. test injection으로 일부러 같은 provider를 반환시키는 임의 factory는 현재 경로가 아니다. |
| r1 RGB가 r2 observer로 routing되는가 | Runtime `on_frames`는 `frames[rid]`를 `actors[rid]`에 준다. executor가 robot/camera/frame identity를 검사한 뒤 자신의 pose provider에 보낸다(`zone_own_executor.py:217–230`). Backend는 각 `ports[rid].capture()`의 obs에서 JPEG를 decode해 같은 rid tuple을 만든다(`sim/final_pair_v3.py:161–188`). | 현재 trusted backend의 obs/RGB pairing을 확인했다. arbitrary 외부 caller가 RGB array만 다른 내용으로 바꾸는 악의적 조합까지 인증한 것은 아니다. |
| 늦은 completion callback이 reset 후 다른 camera state와 섞이는가 | HIGH는 `OpenCVObserver`를 쓰며 `observe`가 `observations(..., self.camera(), ...)`를 직접 반환한다(`opencv_wall_observation.py:63–87`). Future, pool, completion callback, worker subprocess는 없다. | 현재 경로에 존재하지 않는 async completion race를 새 결함으로 세지 않는다. fixed SIM delay queue의 old-frame/reset 처리는 별도 timestamp appendix에서 검증했다. |
| camera closure가 마지막 robot의 PF를 참조하는가 | `HighPoseSource.__init__`마다 local `pf`와 `column_model_for`를 만든다. observer callback은 그 instance의 `self.servo`와 그 local PF를 사용한다(`vision_pose_source_highpose.py:45–59,84–85`). | loop-variable late binding이 아니다. module은 공유해도 PF/servo/observer reference는 instance별이다. |
| calibration/geometry object가 robot 간 mutation을 전파하는가 | `student_calibration`은 deep copy, PF params/static도 deep copy다. camera record는 own load/issued servo key로 찾는다. `measured_column_model`은 매 호출 새 ColumnModel과 새 `_traces`를 만든다. | 알고리즘 상태 소유권을 확인했다. 같은 공통 모델 calibration이 실제 두 camera에 정확하다는 물리 검증은 아니다. |
| 다음 case에 이전 provider state가 남는가 | case runner가 reset/preroll 이후 새 Runtime을 생성한다(`run_pair_highpose.py:217–226`). case finally에서 runtime과 backend 모두 close를 시도한다(260–276). Runtime close는 한 provider close가 실패해도 나머지를 시도한다(`zone_final_pair_runtime.py:88–96`). | 기본 case별 lifecycle에 global provider cache/reuse가 없다. arbitrary 외부 worker injection/hot-swap은 이 결론의 대상이 아니다. |
| observer failure 후에도 결과를 계속 쓰는가 | OpenCV의 처리 오류는 WorkerFailure로 바뀌고 provider는 failure를 기록·worker.close·FailClosedLoc 상태를 유지한다. 이후 frame은 worker를 호출하지 않는다(`vision_pose_source_p03.py:229–250,264–270`). close 이후 observer는 거부한다. | 현재 기본 observer의 실패 경로를 읽었다. 모든 OS/process crash 시나리오의 실행 검증은 아니다. |

camera calibration routing의 구체적인 기준은 `zone_final_pair_contract.camera_record`의 load/posture key와 유한한 rigid transform 검사, HIGH의 issued HIGH settle 조건이다. static calibration을 world에서 매 frame 읽어오는 경로가 아니다. 이 소유권 점검은 prior R7의 pinhole/plane 계산 검토를 반복하거나 새로운 실제 mount 교정을 수행한 것으로 세지 않는다.

`VisionWorkerClient`라는 별도 learned subprocess 구현도 저장소에 존재한다. 그러나 현재 HIGH default factory는 이를 만들지 않는다. 그 client의 seq/hash/pipe timeout 성질을 current HIGH의 async 위험으로 옮겨 설명하지 않는다. LLM image routing 및 기존 ImageRoute.planned 수정은 이 검토 범위가 아니다.

추가 fake callback tests는 만들지 않았다. 실제 경로가 동기·instance별 소유권으로 구성되어 있어 존재하지 않는 callback 순서를 시험해도 현재 blocker에 대한 증거를 더하지 않기 때문이다. 이후 transport/worker pooling을 도입하면 acquisition timestamp, own-rid association, request identity, cancellation generation을 그 새 실제 caller에서 다시 검토해야 한다.

파일별 SHA256과 원래 경로는 `high-observer-ownership-manifest.json`에 있다. 이 문서는 확인한 가설의 제한된 반박이지 전체 camera pipeline의 정확도·무결성 인증이 아니다.
