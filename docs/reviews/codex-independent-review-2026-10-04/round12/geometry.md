# R12 — LookAroundGuard의 covariance frame·cap·fallback 검토

**현재 경로에서 world/base frame 혼동이나 cap을 두 번 빼는 오류는 찾지 못했다.** 실제 PSD own covariance에서 normal 방향 margin은 의도한 anisotropic 정책과 일치한다. 이는 collision safety 또는 Gaussian coverage의 실증 검증이 아니다. source는 #363 `de03fe87d08879abefaa7dac67c7ff313df5df89`이며 검토 파일별 SHA256은 `lookaround-covariance-results.json`에 있다.

## 실제 caller와 frame

`zone_pair_highpose_runtime.adopt_v98_frame_gate`는 각 own executor의 `PairArmGuard`를 `LookAroundGuard`로 바꾸고 `_sweep_steps`를 감싼다. wrapper는 `pose.report(now)`에서 hint를 만들고 원래 sweep 호출이 끝나거나 예외가 나면 `finally`에서 지운다(`zone_pair_highpose_lookaround.py:155–166,181–185`). pair command의 `PairGeometry` 자체를 이 anisotropic class로 바꾸는 기능은 아니다.

원래 `_sweep_steps`는 같은 now의 report로 `OwnPose`를 만들고 `SweepRecheck.check`를 호출한다(`zone_own_executor.py:729–755`). recheck는 현재 pose의 `transition_clear`를 **먼저** 조회한다. 따라서 초기 broad estimate도 이 query에 도달하며, 실패했을 때만 nominal/uncertainty로 stationary wait를 결정한다(`zone_own_sweep.py:38–48`). 아래의 covariance 대조는 이 query 의미에 관한 것이다. 특정 전체 sweep이 승인되거나 실제 로봇이 해당 pose에 있었다는 주장이 아니다.

HIGH의 motion class는 현재 `owncam_localizer`에서 estimate를 상속한다(`vision_pose_source_pair_v3.py:15,25–36`). `owncam_localizer.estimate:517–531`은 world particle x/y 차이의 weighted covariance를 구하고 `std_xy=sqrt(cov_xx+cov_yy)`를 계산한다. covariance는8자리로 반올림해 report로 전달되며 sigma는 반올림 전 값이다. `VisionPoseSource.report:273–290`은 이 cov와 sigma를 같은 estimate에서 가져온다.

`rect_distance_normal`은 world point를 rectangle local frame으로 회전해 closest offset을 얻고, 그 unit normal을 다시 **world frame**으로 회전한다. `sigma_toward`가 사용하는 covariance도 world x/y이므로 body yaw를 한 번 더 곱하면 오히려 잘못된다. n은 무차원, covariance는m², 그 제곱근과 margin은m다. 실제 current map은 축정렬 wall이며 끝점 근처에는 대각선 normal도 생긴다.

## cap을 포함한 정확한 식

`s=std_xy`, `C=.15m`, world unit normal을 n이라 놓으면, 현재 `PairArmGuard`의 position 항은 `min(s,C)`다. **실제로 PSD인 입력에서는** `LookAroundGuard._margin_toward`가 그 항을 한 번 빼고 다음으로 대체한다.

\[
m_{xy}=\min\left(s,C,\sqrt{2}\sqrt{n^T\Sigma n}\right).
\]

이는 코드의 `isotropic−iso+min(iso,sigma_toward(...))`를 정리한 식이다. PSD이면 `0≤nᵀΣn≤traceΣ`다. `traceΣ=s²`는 반올림 전 estimator와 이번 authored witness에서 정확하다. 실제 report는 covariance를 반올림하며 `cov_xy`가 `|sqrt(traceΣ)−s|≤.001+.01s`를 허용하므로 모든 전달 값에 정확한 등식을 요구하지 않는다. PSD 검사도 작은 determinant 오차를 허용하고, 구현은 제곱근 전에 `max(nᵀΣn,0)`을 적용한다. 따라서 허용된 모든 수치 입력의 식에는 이 clamp가 포함된다.

새 항은0 이상이고 기존 capped position 항보다 크지 않다. trace와 s가 정확히 일치하는 round covariance `Σ=aI`에서는 `sqrt(2)*sqrt(nᵀΣn)=sqrt(traceΣ)=s`이므로 capped/uncapped 모두 기존 항과 같다. base20mm, residual15mm, yaw margin은 바뀌지 않는다.

기존 테스트는 diagonal covariance, round estimate, 누락/불일치 covariance, moved query, normal의 subgradient를 이미 다룬다. 이번에는 그 테스트를 넓게 반복하지 않고 **off-diagonal covariance와 실제 wall corner normal의 결합**만 작은 exact-AST 대조로 추가했다. eigenvalues가 .16/.0009m², major direction `(1,1)`인 authored PSD를 사용한다.

| 실제 map의 query normal | projected variance | position 항 | base/residual/yaw 포함 margin |
|---|---:|---:|---:|
|west wall face `(1,0)`|.08045m²|.15m|.189m|
|divider upper-left `(-1,1)/√2`|.0009m²|.0424264m|.0814264m|
|divider upper-right `(1,1)/√2`|.16m²|.15m|.189m|

yaw sigma=.02rad, lever=.2m로 고정했으므로 yaw 항은.004m다. 동작 출력/허용 여부가 아니라 정확한 margin 함수의 세 실제 wall query 결과다. helper를 실행한 입력은 정답 좌표가 아니라 합성 own-estimate/query point이며 로봇·영상·물리 실행은 없다.

## 의도된 fallback과 보장 범위

- covariance가 없거나 유한값/PSD 검사·`sqrt(trace)`와 sigma의 허용 오차 검사를 통과하지 못하면 shared isotropic 검사로 돌아간다. sigma만 별도로 부풀린 provider를 작은 covariance로 다시 줄이는 경로는 막는다. 현재 production covariance는 대칭 weighted second moment에서 오므로 임의 비대칭 외부 tensor를 실제 입력처럼 가정하지 않았다.
- hint의 x/y/yaw/sigmas 다섯 값이 query pose와 같아야 적용한다. moved backoff pose와 nominal zero-sigma pose는 다른 값이므로 isotropic이다. hint는 호출 범위 밖으로 유지되지 않는다. report(now)의 두 조회 사이에 새 frame이나 command update를 실행하는 async callback은 이 현재 경로에 없다.
- rectangle 내부 또는 거의 boundary여서 normal을 정의하지 않는 경우 isotropic을 유지한다. wall 위를 통과하는지 판단하는 z 비교에도 기존 isotropic margin을 먼저 쓴다. 더 큰 margin의 height 조건으로 먼저 제외하는 것은 작은 directional margin 기준보다 보수적이며 새 vertical relaxation이 아니다.
- cap .15m는 기존 정책이다. 큰 covariance에서 이 cap을 적용한 값을 고정 k의 Gaussian quantile이라고 볼 수 없다. 예컨대 normal sigma=.4m인데 cap이.15m이면 그 비는.375다. uncertainty gate, wall별 위험 합산, model validity/empirical calibration까지 이 식이 보장하지 않는다. source의 chance-constraint 동기를 실제 물리 안전 또는 고정 coverage 보장으로 확대하지 않는다. cap을 없애거나 threshold를 바꾸자는 제안도 아니다.

현재 source 의미와 구현은 일치한다. 작은 off-diagonal 대조는 기존 frame/unit/fallback 계약을 지지하며 새 버그로 세지 않는다.

## 재현

Python3.12.14 표준라이브러리만 사용한다. pytest/OpenCV/NumPy 설치나 simulator가 필요 없다. pinned Git object가 있는 clone을 읽고 원문 함수 AST와 공개 static map으로 JSON을 stdout에 출력한다. 원본 결과를 보존해 새 임시 경로로 출력한다.

```sh
python /path/to/lookaround-covariance-repro.py --repo /path/to/ugrp-clone > /new-temp-directory/lookaround-covariance-results.json
```

관련 기존 테스트 `tests/test_highpose_look_around.py:155–233`는 source로 대조했다. pytest가 없는 이 환경에서 그 test suite를 실행했다고 보고하지 않는다.
