# egomap26 — 먼 벽 누락 / GMapping 삽입 생명주기 (사전 등록)

2026-10-08 사용자 요청. **오프라인만, 물리·모델·agent_lock acquire0**.
egomap25 on 재생/실패 판정 완료 후 시작한다. egomap23의 이미 본 DEV 녹화
`outputs/rbpf-motion-gate-v1/baseline`을 그대로 재생하며 새 확증 자료로 부르지 않는다.
코드/관문 커밋 후 한 번씩 off/on, 결과 후 문턱 변경 없음. GitHub500은 감독 지시에 따라
로컬 SHA로 계속 진행하고 작업 끝에 정상 push 재시도한다. PR405 DRAFT, TensorBoard 생략 유지.

## 수정 전 진단 / 표준 원문 대조

901 RGB 중 초기 준비10개를 제외한891개 모두 검출 선분이 있다. 이동 관문836개,
low_overlap47개, search_boundary1개, bootstrap1개, improved_proposal3개,
insufficient_match_points3개. 지도 삽입7개는 t3.3–36.1s뿐이다.
36.1s 뒤726개는 이동 관문679 + low_overlap46 + search_boundary1 = 삽입0.
120s 주변119.7/119.9/120.1/120.3s도 각각5/6/5/5선분이 있으나 전부 이동 관문이다.
정착/지도 range/중복 거부는0. 검출기 내부에도4m 필터가 있으므로 지도 range0을
검출기 거리 탈락0으로 오해하지 않는다. JPEG 재검출 감사는 별도 표로 기록한다.
경사각 자체를 거르는 분기는 없고 연결 열의 거리/방위 연속성과 최소4열을 검사한다.
다른 로봇 가림은 instance 정답 마스크가 없어 **미계수**; 소프트웨어 거부 사유와 구분한다.

원본 OpenSLAM GMapping 고정 SHA `c716f0192131029b31a49554f8c11353d29819a5`를 직접 읽었다.
원문 파일 URL/sha256은 [sources.json](results/sources.json), 다운로드는 raw의 `sources/`.

|항목|원본 코드|현재 어댑터|수정|
|---|---|---|---|
|누적 이동 관문|[cpp L355–385](https://github.com/ros-perception/openslam_gmapping/blob/c716f0192131029b31a49554f8c11353d29819a5/gridfastslam/gridslamprocessor.cpp#L355-L385)|`rbpf_motion_gate.py` 첫 scan/1m/.5rad|변경0|
|정합 실패 자세/likelihood|[hxx L16–31](https://github.com/ros-perception/openslam_gmapping/blob/c716f0192131029b31a49554f8c11353d29819a5/include/gmapping/gridfastslam/gridslamprocessor.hxx#L16-L31)|`improved_proposal`: 모션 proposal로 fallback, likelihood 가중|변경0|
|실패 뒤 삽입|[hxx L141–167](https://github.com/ros-perception/openslam_gmapping/blob/c716f0192131029b31a49554f8c11353d29819a5/include/gmapping/gridfastslam/gridslamprocessor.hxx#L141-L167): 재표본 유무 모두 registerScan|`self_map_rbpf.py:287` 정합 성공 입자만 삽입|새 옵션에서만 실패 입자도 현재 모션 표본 자세로 삽입|
|실패 뒤 이동량 리셋|[cpp L470–473](https://github.com/ros-perception/openslam_gmapping/blob/c716f0192131029b31a49554f8c11353d29819a5/gridfastslam/gridslamprocessor.cpp#L470-L473)|관문 통과 scan 후 리셋|이미 일치, 변경0|
|선택적 재표본|[hxx L79](https://github.com/ros-perception/openslam_gmapping/blob/c716f0192131029b31a49554f8c11353d29819a5/include/gmapping/gridfastslam/gridslamprocessor.hxx#L79)|Neff<N/2|변경0|

기존 Gaussian improved proposal·모션 잡음·정합 점수는 유지한다. OpenSLAM lidar 전체를
바이트 단위 이식했다는 주장이 아니라 **실패 scan 삽입 생명주기**를 원본과 일치시킨다.
egomap24의 사용자 지정 reject-skip은 원본과 다른 실험 옵션으로 보존하고 이번에는 끈다.
egomap25 yaw도 off. 여러 수정의 효과를 합산하지 않는다.

## 구현 전 고정 옵션 / 관문

|옵션|기본|on 의미|
|---|---|---|
|`rbpf_insertion=gmapping_range_v1`|off|motion gate를 통과한 유효 scan은 정합 실패해도 각 입자의 현재 모션 proposal 자세에서 삽입|
|`rbpf_update=gmapping_motion_v1`|기존 off|이번 off/on 비교 양쪽 on, 1m/.5rad 그대로|
|`wall_confidence=inverse_sensor_v1`|기존 off|이번 양쪽 on. 거리 의존 분산으로 hit/miss 증분을 낮추고 raytrace free carving|
|`rbpf_rejection` / `yaw_prior`|off|이번 모두 off, 새 삽입 정책과 reject-skip/yaw 정책의 암묵적 덮어쓰기는 금지|

`gmapping_range_v1`은 RBPF + motion gate + inverse_sensor_v1을 요구한다.
4m/정착/양의 깊이/자기 로봇/중복 필터는 유지한다. 4m 밖을 강제로 넣지 않는다.
기존 confidence는 `σr=(r²+h²)/(h fy)` (접점1px 전파),
`w_range=res²/(res²+σr²)`이고 입사각·경계 대비/선명도·예측 자세 공분산·정착 factor를 곱한다.
원거리 log-odds 가중은 이미 존재하지만 삽입이 막혀 적용할 기회가 없었다.
이를 재사용하고 새로운 센서 계수/거리 문턱은 도입하지 않는다.
[Thrun ch9 Table9.2 정정](https://robots.stanford.edu/probabilistic-robotics/corrections1/pg288.pdf)과
[Elfes 1989](https://doi.org/10.1109/2.30720)의 hit/free 역센서 누적 원리를 따르며,
상기 가중 식은 기존 구현의 분산 기반 tempering이지 책이 정한 수치나 보정된 벽 정답 확률이 아니다.

**소프트웨어 관문(구현 전 고정)**:
off의 기존 grid/poses/decisions/ledger JSON bytes 동일;
동일 명령의 관문 통과55개/보류836개 유지;
on의 유효 통과 scan55개 모두 삽입(36.1s 이후47개 포함);
단위 시험에서 거부 scan 뒤 누적 이동 리셋·정지 scan 보류·원거리 낮은 증분/free carving 확인.
지도 성능은 같은 영역의 P/R 분자·분모/전체 P/R/벽·경로RMSE/삽입수/거리별 표로 모두 공개한다.
P/R 향상을 통과 조건으로 사후 추가하지 않으며, 소프트웨어 관문 통과를 위치/지도 품질 통과로 부르지 않는다.
이번은 결과에 관계없이 물리0. GT·정적 지도는 봉인된 예측의 평가에만 읽는다.

## 투영 이론과 비교 정의

높이 h=.23m, pitch 편차 .13°,640×480,fy=622.1655px.
바닥 거리 r=h cot(α), `|dr/dα|=(r²+h²)/h`.
pitch 항은 이 Jacobian×.13°(rad),1px 항은 Jacobian/fy.
1px RSS는 독립 잡음이라고 가정한 민감도 비교값이며, 고정 bias를 확률오차로 보정했다는 뜻이 아니다.
양자화만의 표준편차는1px/√12. 표의 구간 중앙 거리 이론과 실제 구간 분포는 같지 않다.
평가용 실제 카메라와 명령 FK로 **동일 픽셀**을 바닥에 투영한 차이를 projection 오차로,
GT 차체 자세로 옮긴 검출점의 최근접 실제 벽 거리를 total_wall 오차로 각각 보고한다.
후자는 검출/대응 오류도 포함한다. 카메라 GT는 진단 스크립트에만 존재한다.

raw `/Users/changmin/projects/ugrp/outputs/rbpf-insertion-v1/`; ENOSPC=HOST_ERROR.
출력/입력 sha256 보존, 다른 worktree·PR406·사용자 미추적 파일 변경0.
