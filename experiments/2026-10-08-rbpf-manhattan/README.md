# egomap25 — Manhattan 방향 관측 (오프라인 사전 등록)

2026-10-08 사용자 요청. egomap23 동일 녹화, egomap24 selective resampling **on** 고정,
새 `yaw_prior=manhattan_v1`만 off/on. 물리·모델·agent_lock acquire0, 재튜닝 없음.
정적 지도/GT/다른 로봇 관측은 추정에 금지. 같은 녹화의 DEV 진단이며 새 확증 자료가 아니다.

## 표준 방법과 적용 범위

[Košecká & Zhang, Video Compass, ECCV2002](https://cs.gmu.edu/~kosecka/Publications/eccv02.pdf)의
직교 주방향으로 상대 카메라 방향을 관측한다는 원리를 따른다. 검색 인덱스의 저자 PDF
초록은 확인했으나 GMU 원문은 리다이렉트/인증서 오류로 본문을 가져오지 못했다.
따라서 그 논문의 전체 3D 소실점 EM을 그대로 복제했다고 주장하지 않는다.
사용자 지정 입력인 **기존 바닥 투영 벽 선분의 2D 방향**으로 제한하고, 다음 공개 표준식을 쓴다.

- [pycircstat descriptive.py](https://github.com/circstat/pycircstat/blob/bcfe6aa02b99ac590e6a79091f550c9ad79592e5/pycircstat/descriptive.py#L197-L227):
  `axial_correction=4`, 선분 길이 L로 가중한 `Z=Σ L exp(4iα)/ΣL`, `α=arg(Z)/4`.
  L333–343 complex mean, L455–487 circular std. 뒤집힌 선분·직교 선분을 같은 축으로 취급.
- 관측 분산 `R=(-2 log|Z|)/16 + (2°)^2`. 선분 간 산포를 관측 분산으로 쓰며
  선분 수로 나눠 상관된 검출을 독립 표본처럼 과대 계산하지 않는다. 2°는 기존
  `CSMOptions.covariance_floor_yaw_deg`를 그대로 사용(논문 기본값이 아니라 기존 센서 바닥값).
  길이0/비유한 값/수치적으로 Z=0이면 정보 없음. 새 성능 기반 길이·집중도 문턱 없음.
- [FilterPy KalmanFilter.update](https://github.com/rlabbe/filterpy/blob/master/filterpy/kalman/kalman_filter.py#L531-L557)의
  스칼라 Gaussian 관측 조건화: H=[0,0,1], S=HPHᵀ+R, K=PHᵀ/S,
  μ←μ+Kν, Joseph covariance. 실제 확인한 고정 SHA/라이선스는 [sources.json](results/sources.json).
  90° 간격의 동등한 관측 모드들을 prior 확률로 가중·표본화하고, 그 marginal likelihood로
  각 입자 weight를 갱신한다(가장 가까운 축을 정답처럼 고정하지 않음).

pycircstat/FilterPy 원문 코드를 열어 수식·라이선스 확인, 식 재구현만 하며 의존성 추가0.
첫 유효 자기 관측 **이후** 각 입자 pose와 관측 불확실성에서 Manhattan 축 φ를 표본화하여
입자별 고정 잠재변수로 보존한다. 초기 세계 축을0으로 주입하지 않으며 GT 시작 yaw는 평가만.
재표본 시 φ도 같은 부모 인덱스로 복사한다. 첫 관측을 자기 자신에 재가중하지 않는다.
후속 yaw 관측은 `θ=φ−α (mod π/2)`이며 Gaussian 모드 조건화를 RBPF 제안의 prior에 넣는다.
90° 모호성·초기 축 오차·비Manhattan 벽·잘못된 검출은 남는 한계다.

## 갱신 규칙 / 고정 관문

- egomap23 motion gate(첫 scan 또는 명령 거리1m/회전.5rad), egomap24 잡음과
  `<N/2` 선택적 재표본, settle/4m/peer/중복 검사는 그대로.
- motion gate가 통과한 유효 scan에서만 yaw 조건화 후 기존 CSM을 실행한다.
  CSM 거부는 **CSM likelihood/삽입/재표본 생략**을 계속 뜻한다.
  별도로 유효한 Manhattan 방향 관측은 overlap이 없어도 yaw를 보정할 수 있다.
  yaw만을 위한 추가 재표본 호출은 하지 않는다. CSM 수락 때만 기존 Neff 조건을 쓴다.
- 같은 벽에서 방향과 CSM 공간 likelihood를 얻는 상관은 완전히 모델링하지 못하는
  Gaussian 근사다. 실제 오차/σ 검사를 유지하고 posterior 보정 완료라고 주장하지 않는다.
- off는 기존 객체/메서드/출력 bytes 그대로. yaw on도 모션 평균/검출/graph/지도 임계값은 변경0.

입력 `/Users/changmin/projects/ugrp/outputs/rbpf-motion-gate-v1/baseline/`의 own contacts/commands.
추정 결과를 저장·SHA 봉인한 뒤에만 GT를 읽는다. off는 egomap24 **on** 예측 bytes와 비교.
동일891시각의 yaw 오차(전체 각도와 mod90 둘 다), 종료 XY 오차 e/σXY 및 e/(2σ),
경로RMSE, 영역 P/R(분자·분모), 전체지도 지표, 실제 이동/footprint union/가시 벽 표본/삽입수를 보고한다.
σXY는 최대 XY covariance 고윳값의 제곱근. 영역 가시성은 기존 FOV·4m·벽-only 가림(물체 가림 미반영).

**다음 물리 제안 관문: 종료 e≤2σXY AND 영역 precision(on)>precision(off).**
2σ는 운영 관문으로 2D 95% 영역이라는 뜻이 아니다. 영역 셀이 없으면 P 미정/실패.
끝 오차만 좋아 보이는 경우를 피하도록 yaw 추이와 전체891시각의 2σ 초과 수도 공개한다.
관문을 통과해도 이번 작업은 제안만, 물리0. 결과 후 문턱/잡음/seed/표본을 변경하지 않는다.

raw `outputs/rbpf-manhattan-v1/` (기본 checkout 절대 경로), ENOSPC=HOST_ERROR.
시험→커밋된 소스 고정→off/on 한 번씩→결과. PR405 DRAFT, 강제 push/reset/삭제 없음.
다른 worktree·PR406·사용자 미추적4파일 보존. TensorBoard 생략 요청 유지.

구현 전 수치 명세: periodic Gaussian 합은 prior 예측 표준편차 ±8σ 이상(최소 좌우2모드)을 포함하여 절단한다. 성능 관문이 아닌 계산용 꼬리 근사이며, 집중도가 없을 때의 1e−12 검사도 수치 영점 검사다.
