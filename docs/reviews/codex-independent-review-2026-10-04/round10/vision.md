# Scan receipt와 relative edge의 진단 범위

두 원본 감사는 새 코드 결함이 아닌 현재 측정·판정 의미를 확인한다. 각 절의 fixture와 한계를 구분해 읽는다.

# R10 — PF 가중치 갱신과 새 absolute fix를 분리해서 읽기

검토 source: #363 `6727751b49ce11fb62234bb97274137f22850765` (후속 `de03fe87`의 source 동일). **현재 선언과 일치하는 동작을 확인한 진단 문서이며 새 버그는 아니다.** 현재 POSE_UNCERTAIN의 실제 원인을 조사한 raw replay/physics 실행도 아니다.

`zone_final_pair_scan.py:1–5`는 scan count나 좁은 posterior만으로 새 absolute fix가 되지 않는다고 명시한다. 같은 파일의 `install`은 **quality를 계산한 뒤 원래 likelihood update를 실행**하고, informative가 아니면 마지막 fix timestamp를 이전 값으로 되돌린다. particle weights를 되돌리는 코드는 없다. 따라서 아래 네 질문을 따로 확인해야 한다.

| 지표 | 실제로 뜻하는 것 | 자동으로 뜻하지 않는 것 |
|---|---|---|
| provider frame / worker call | frame을 받았음 / observer를 호출함 | PF update, 새 fix, 정확도 |
| PF `scan_updates` | initialized·settled·min_columns gate를 지나 scan likelihood 적용 경로를 실행함 | informative receipt 발급 |
| current `v3_scan_quality.informative` | 이번 scan의 compatibility/support/local curvature가 receipt 기준을 만족함 | 실제 pose error/coverage 보장 |
| `v3_last_fix_quality`, `last_scan_t` | 마지막 informative scan의 quality와 capture 시각 | 현재 frame도 informative임 |

frozen `vision_loc.py:746–763`는 적용 후 scan count와 temporary `last_scan_t`를 갱신한다. `zone_final_pair_scan.py:32–49`는 `measured`를 informative receipt 의미로 다시 제한하고 timestamp를 rollback한다. `VisionPoseSource.on_frame`(`vision_pose_source_p03.py:254–262`)의 provider `counts.measured`는 이 제한 이후 값을 센다. 이 count들과 PF `scan_updates`를 같다고 비교하면 다른 사건을 섞게 된다.

## 정확한 wrapper를 실행한 최소 증인

`scan-receipt-repro.py`는 원본 VIS3 `interval_prob/column_loglik`, recovery curvature/quality, v3 quality wrapper, v98 consistency wrapper, RobustVisionLocalizer의 scan update, 현재 v3 resampler, FailClosedLoc freshness facade를 실행한다. map geometry 대신 authored linear expected-row model과 27개의 작은 Cartesian particle grid를 사용한다. pose prediction은 time-only stub이며 RGB·실제 지도·물리 모델을 실행하지 않는다.

measurement는 현재 기본/선택값(min_columns6, sigma2.5px, frozen effective_columns8, settle0.2초), v98 target cap4/rho0.5를 사용한다. normalizer는 실제 v3 함수를 호출하고 이 좁은 fixture에서는 ESS가 절반보다 높아 resampling draw가 발생하지 않는다. 표의 covariance는 endpoint가 계산한 weighted second moment다. production `owncam_localizer.estimate`의 `1−Σw²` 보정 covariance와 동일한 값이라고 주장하지 않으며, 실제 PoseReport σ를 재현한 수치가 아니다. 관측 row는 모두200이며 true physical pose 또는 센서 정확도 labels를 입력하지 않는다.

| 합성 단계 | 이번 quality | PF update 수(누적) | 새 informative fix | ESS 변화 | x 분산 변화(m²) |
|---|---|---:|---|---:|---:|
| 이전 fix 없음, x만 보는 rank1 model의6열 | accepted=True, informative=False, curvature0 | 1 | 없음 | 27→24.400864 | .001666667→.001282034 |
| 독립 시작, 3축 local full-rank model의6열 | informative=True, curvature258.824 | 1 | t10 | 27→26.139616 | .001666667→.001543890 |
| 그 뒤 t10.5의 rank1 weak scan | informative=False, curvature0 | 2 | 없음, 기존 t10 보존 | 26.139616→25.269178 | .001543890→.001414802 |
| 그 뒤 t11, usable column0 | quality=None, scan 미적용 | 2 | 없음, 기존 t10 보존 | 변화 없음 | 변화 없음 |

rank1 model은 일부 방향의 likelihood는 구별하지만 다른 두 방향의 local curvature가0이 되도록 명시적으로 만든다. `accepted=True`는 입력 likelihood가 유효해 quality를 계산할 수 있다는 뜻이고 `informative=True`와 다르다. weak scan에서 가중치·ESS·x분산은 바뀌므로 “fix가 없으면 PF가 영상을 전혀 사용하지 않았다”는 설명은 source와 맞지 않는다. 반대로 posterior가 좁아졌다는 것만으로 full-pose fix나 정확도가 입증되지 않는다.

모델의 rank를 바꾸는 것은 quality 동작을 격리하기 위한 작성한 test endpoint다. 실제 scene에서 해당 local Jacobian이나 오차 변화가 발생했다는 주장으로 사용하지 않는다. likelihood 업데이트가 항상 covariance를 줄이는 것도 아니다. 이 표는 이를 줄이는 하나의 재현 가능한 합성 경우다.

## stale quality와 fresh timestamp를 혼동하지 않기

weak-after-fix에서 current `v3_scan_quality.informative=False`여도 `v3_last_fix_quality.informative=True, t=10`은 남는다. `PairVisionPoseSource.report`(`vision_pose_source_pair_v3.py:140–144`)의 `observation_quality.informative`는 마지막 성공 quality에서 온다. 현재 frame의 성공으로 읽으면 안 된다. `last_fix_t`와 age를 같이 봐야 한다.

한 가지 의심도 실제 caller로 반박했다. v3 wrapper가 timestamp를 복구할 때 내부 `update_obs` 반환 dictionary의 `since_scan_s`는0으로 남을 수 있다. 그러나 current provider는 그 dictionary를 외부 pose report로 직접 반환하지 않는다. `FailClosedLoc.estimate`(`vision_pose_source_p03.py:67–76`)가 복구된 `pf.last_scan_t`에서 다시 계산하므로, 이 fixture에서도 외부 facade age는 t10.5에0.5초, t11에1초다. 이를 현재 외부 freshness 버그로 세지 않았다.

## 지금의 uncertainty fault tree에 쓰는 범위

기존 허용 trace를 읽을 때 frame 수·worker calls·PF scan updates·informative fix 수를 분리하고, 마지막 quality의 `t`와 freshness를 같이 놓는다. scan updates는 늘지만 fix age가 커지면 compatibility/support/curvature 중 어느 gate인지 살핀다. scan updates 자체가 늘지 않으면 initialized/settled/min columns 경로부터 확인한다. 이 구분이 실제 POSE_UNCERTAIN 원인을 확정하지는 않으며 covariance growth, partial geometry, old receipt, model bias를 한 이름으로 합치지 않게 한다.

이 결과는 uncertainty threshold를 완화하거나 partial scan을 full fix로 승격하라는 제안이 아니다. 정책 입력에 ground truth를 추가할 필요도 없다. 현재 기록에 필요한 field가 저장되지 않았다면 source에서 계산 가능하다는 사실과 이미 남아 있는 trace에서 확인 가능하다는 사실을 따로 적는다.

## 재현

`scan-receipt-repro.py`와 `scan-receipt-source/`를 새 임시 폴더에 복사하고 그곳에서 `python scan-receipt-repro.py`를 실행한다. source SHA256을 검사하고 결과는 임시 폴더의 `scan-receipt-results.json`에 쓴다. Python3.12.14, NumPy2.3.5에서 검증했으며 표준 라이브러리 외에는 NumPy만 필요하다. exact AST class/function 본문을 private namespace로 불러와 heavy image/map imports를 실행하지 않았다. frozen `vision_pf.py` hash는 최신 Git object와도 일치함을 확인했다. source 구현은 바꾸지 않았다.

---

# R10 — robust edge의 support 수와 yaw 정밀도는 같은 값이 아니다

검토 source: PR #363 `6727751b49ce11fb62234bb97274137f22850765`. 이후 `de03fe87d08879abefaa7dac67c7ff313df5df89`는 README만 변경해 이 source 경로는 동일하다. **새 코드버그로 집계하지 않는 진단/설계 한계**다. source는 angular uncertainty의 정량 보장을 선언하지 않으므로 count/RMS acceptance를 위반했다고 표현하지 않는다.

## 현재 fallback을 실제로 선택하는 최소 대조

640×480 synthetic RGB에 45개의 visible sample column을 만든다. 27개는 row200 부근의 목표 lower band, 나머지18개는 first qualifying run이 row80에서 끝나는 upper band이다. 읽히는 run은 최소40px이며 ROI 끝299와 겹치지 않는다. 나머지45개 sampled column은 배경이다. 이는 R8 crop 문제나 공개 recorded timeout의 재분석이 아니다.

두 조건에서 목표27개의 count와 row 값은 같다. x 위치만 `140+4j`와 `140+12j`(j=0…26)로 다르다. flat reference row200에서 `round(linspace(-1,1,27))`의 **작성한 boundary perturbation**을 더한다. 실제 camera noise를 측정한 값이 아니며 이 27개 열이 독립이라는 가정도 넣지 않는다.

| 원본 코드 결과 | Clustered support | Spread support |
|---|---:|---:|
| shared OLS | None | None |
| robust fallback | consensus, 27 inliers | consensus, 27 inliers |
| visible candidate 열 수 | 45 | 45 |
| inlier span | 104 px | 312 px |
| Sxx = Σ(x−mean x)² | 26,208 px² | 235,872 px² |
| 최종 inlier RMS | 0.274482 px | 0.274482 px |
| baseline 대비 slope 변화 | 0.0213675 px/px | 0.00712251 px/px |
| 유지 gain1.1067로 계산한 tracker 변화 | 0.0193074 rad | 0.00643580 rad |
| 0.03rad step guard / availability | 통과 / True | 통과 / True |

원본 `HighBeamEdgeTracker`의 default settle3초/ref2/smooth3/min_dt0.5초를 그대로 쓴다. 첫 두 flat sample로 reference를 만들고 perturbed sample 두 개를 넣으면 median이 바뀌면서 위 increment를 실제 반환한다. current `HighPoseSource`가 이 tracker increment를 `apply_relative_yaw`로 전달하는 경로는 `harness/vision_pose_source_highpose.py:80,94–104`다. 이 fixture는 해당 provider 전체나 PF를 실행하지 않았다.

두 meaningful negative control도 통과했다: flat image를 유지하면 양쪽 모두 reference가 available인 상태에서 누적 yaw 변화가0이고, target26+outlier18(44 visible)로 줄이면 shared/robust 모두 거부한다. 후자는 `max(MIN_COLUMNS20, .6×90×.5=27, .6×44=26.4)`의 실제 acceptance를 확인한다. threshold를 완화하지 않았다.

## 숫자의 의미와 한계

여기 “baseline horizontal”은 합성 fixture 작성 시 정한 기준이다. real ground-truth pose나 영상 labels를 controller에 주입하지 않는다. 실제 원래 알고리즘은 authored RGB/own issued pose/loaded 입력만 읽는다. 이 표는 **동일한 2px peak-to-peak boundary 변화에 대한 sensitivity**를 보인다. 실제 물리 beam이 flat인데19mrad 오차가 발생했다는 관측 결과가 아니다.

gain1.1067은 해당 SHA의 `experiments/2026-10-03-pair-carry-highpose/README.md:93–94`에 적힌 유지값이며 원본 test에서도 tracker 인자로 사용된다. 이 리뷰는 raw calibration을 열거나 그 값의 정확도를 재검증하지 않았다. 같은 공개 설명은 HIGH에서 gain의 식별 범위가 약함을 이미 인정한다. 이 표는 그 gain을 고정한 단위 환산이며 실제 yaw error bound가 아니다. 어떤 gain r을 쓰더라도 두 sensitivity의3배 비율은 유지된다.

`zone_pair_highpose_edge.py:78–109`는 count와 RMS로 line을 받아들인다. source의 shared-first 계약과 fallback acceptance를 이 witness는 모두 지킨다. 동일 count/RMS는 x의 분포까지 같다는 뜻이 아니다. 가정상 독립·등분산 vertical error σ², fixed x, 정확한 line model일 때만 OLS slope variance가 σ²/Sxx이므로 여기서는 variance9배/standard deviation3배 차이로 연결할 수 있다. 실제 first-run segmentation bias나 calibration gain error에 이 IID 공식을 그대로 적용하지 않는다.

## 최소한의 유용한 다음 진단

이미 존재하는 edge fit debug rows에 **accepted inlier의 x-span 또는 Sxx**를 함께 남기면, count가 같아도 leverage가 달라진 구간을 자기 영상만으로 구분할 수 있다. 이것은 진단 제안이며 새로운 최소 span threshold, 성공/실패 gate, uncertainty guarantee를 의무화하는 제안은 아니다. 실제 허용 trace에서 support geometry 변화가 없는 경우 이 가설의 우선순위를 낮출 수 있다.

현재 공개 POSE_UNCERTAIN나 실제 운반 실패의 원인을 이 합성 대조로 단정하지 않는다. 얻은 정보는 “consensus 성공·27열·작은 RMS”만으로 동일한 yaw 정밀도를 주장할 수 없다는 구체적인 경계다.

## 재현

`edge-support-repro.py`와 `edge-support-source/`를 새 임시 폴더에 복사한 뒤 그 폴더에서 `python edge-support-repro.py`를 실행한다. 원본 결과를 덮어쓰지 않는다. Python3.12.14, NumPy2.3.5, Pillow12.3.0에서 검증했다. source hash manifest를 시작에 검사하며 결과는 복사된 script 옆 `edge-support-results.json`에 저장된다. OpenCV/MuJoCo/torch/pytest, 네트워크, raw 영상·held-out 데이터는 필요 없다. source 구현은 바꾸지 않았고 private dependency binding만 했다.
