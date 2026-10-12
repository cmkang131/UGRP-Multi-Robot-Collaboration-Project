# ownmaps2a: S2 자기 지도 교체 오프라인 검증

상태: 결과 개봉 전 사전 등록. 부모 `e532f52e3df512e5fac8cef7654dc2ba06fa61b1`, 작업 `codex/ownmap-s2`.
물리 실행·렌더·학습·모델 호출 0, agent_lock 사용 안 함. 고정된 자기 RGB와 발행 명령만 재생한다.

## 고정 비교와 관문

`registration.json`을 먼저 커밋하고 이후 실행 소스도 시험 통과 뒤 커밋한다. 새 튜닝 없음.
7개 기존 S2 기록마다 아래 순서의 자기 지도 하나를 교체한다. 여섯 지도는 seed 순서로 배정하며
결과를 보고 고르지 않는다. 지도별/버전별 행을 보존하고 독립 물리 시행으로 세지 않는다.

| S2 기록 | 자기 지도 seed |
|---|---|
| v139 / 1059 | 49001 |
| v139 / 1060 | 49002 |
| v139 / 1061 | 49003 |
| v140 / 1060 | 49004 |
| v140 / 1062 | 49005 |
| v140 / 1063 | 49006 |
| v140 / 1064 | 49001 |

각 pair는 받은 정적 지도(off)와 own_grid_v1(on), 같은 원본·seed·명령·기존 PF/운동/센서 상수.
active observation은 기록된 명령만 재생하며 새 행동을 선택하지 않는다. 실제 운반 성패를 재평가하지 않는다.
기준 재생은 기존 저장 pose 7필드와 최대 차이 1e-9 이내이어야 한다. 실패하면 재현 불일치로 남긴다.

- 수렴: 기존 v139 정의(초기화된 released report의 std_xy <= 0.05m) 최초 시각, 정답과 무관하게 선언.
- 올바른 수렴: 최초 선언의 평가 XY 오차 <= 0.25m, yaw <= 15도. 오수렴은 각 조건 초과를 별도 표시.
- RMSE: 각 조건의 최초 수렴 후 전체 released report를 평가. 수렴하지 않으면 null/실패, 0으로 채우지 않는다.
- NEES XY: 가역인 보고 공분산에서 chi2(2,95%)=5.9914645471 초과 수/분모.
  단일 mode + 보고/선택 mode 공분산 일치 분모도 별도 보존한다. 다봉 분포 NEES는 기술통계.
- 무경고 >25cm: 원본 drive 결정 시각에서 기존 경고 규칙(std_xy>.05, yaw_std>5도,
  last_fix 없음 또는 best-cluster uncertain)을 재계산한다. 재생 중 drive를 호출하지 않는다.
- 채택 관문: 기준 재생 7/7 일치, 기준 올바른 수렴 최소 1건, 자기 지도 올바른 수렴 수 >=
  ceil(0.8 * 기준 올바른 수렴 수), 기준이 올바른 각 pair의 자기 지도도 올바른 수렴 및
  수렴후 RMSE <= 기준의 2배, 자기 지도 오수렴 수와 무경고>25cm 수가 기준보다 늘지 않음.
  NEES 초과율도 기준 이하. 모두 만족해야 pass, 누락·HOST_ERROR는 실패/미검증이며 분모에서 빼지 않는다.

## 입력·평가 분리

자기 지도 입력은 `online-maps.jsonl` 마지막 grid, `frontend-grid.json`과 일치 확인,
`remembered-goal.json`뿐이다. pose/particles/선택된 입자 위치는 초기 위치 prior로 쓰지 않는다.
점유 log odds >0 occupied, <0 observed free, 0 및 미관측 unknown; 이 임계값은 기존 자기 지도 구현 그대로.
likelihood field는 기존 1cm raster 및 2m truncation, 시작은 관측 free cell과 전체 yaw의 균등 분포.
지도 프레임은 own start chassis 그대로이며 제어 경로는 eval_only와 GT 정렬을 열지 않는다.

기존 goal의 `partial_extent=true` 사각형은 관측 범위이지 확인된 실제 바닥 경계가 아니다.
구역 범위는 보존하되 임의의 네 변을 floor-line likelihood에 넣지 않는다. 확인된 경계선이 없으면
floor edge/door/slot을 없음으로 둔다. 기존 S2 센서 상수·운동 모델·KLD/AMCL 규칙은 고정한다.
정답은 별도 평가 스크립트에서 자기 지도 생성 실행의 첫 GT chassis pose로 고정 SE(2) 변환하여
재생 estimate/covariance를 world로 옮길 때만 사용한다. 궤적 최적 정렬/ICP/scale fit 금지.

실패 원인은 같은 봉인 결과를 평가하여 (1) 관측 벽의 GT 벽까지 거리, (2) GT 벽의 자기 지도까지
coverage, (3) 원본 RGB floor/door 관측 중 지도 대응 항목 누락을 분리한다. 추가 평가 전용
sensor oracle은 GT 위치에서 own field / GT 벽 중 관측지지 부분 / 전체 GT 벽 및 바닥 단서
likelihood를 비교한다. GT 혼합은 evaluator 내부 진단만이며 성공률·주 관문에 합산하지 않는다.
이 진단은 인과적 완주 개선의 증거가 아니다. 결과 후 수정/튜닝/추가 물리 실행 없음.

자원: replay 한 프로세스, 기존 Mac venv, 원본 이미지 재복사 없음, 주 출력은 primary outputs의 새 폴더.
7 pairs 전체 기록, 최초 map 변환/재생 오류도 보존. ENOSPC=HOST_ERROR. 인프라 오류만 원인을 기록한
수정 버전으로 재실행 가능하며 원 시도/해시 보존. 소스 수정 시 실행 프로세스 종료 뒤 새 SHA.

## 참고 자료

- [Nav2 AMCL 원본 likelihood field](https://api.nav2.org/nav2-rolling/html/likelihood__field__model_8cpp_source.html):
  nearest occupied cell, off-map 최대 거리, 1+sum(pz^3)을 기존 S2 구현으로 재사용.
- [Nav2 AMCL 구성](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/):
  기존 noise/센서/KLD/운동 임계값 유지, 불완전 지도에 맞춘 새 튜닝 없음.
- [VLG-Loc, Aoki et al. 2025 v2](https://arxiv.org/abs/2512.12793v2):
  기하가 빈약한 지도에서 semantic correspondence를 MCL에 결합하는 최신 방향을 확인했다.
  본 과제는 VLM/새 학습 없이 기존 색 landmark만 다룬다. 논문 성능을 본 실험 근거로 옮기지 않는다.
- `git show claude/ego-wall-map:harness/self_map_relocalize.py`의 GridField/균등 free-cell 샘플링을 읽기만 참고.
  별도 branch 파일은 수정하지 않는다. 새 지도 입력만 예외이며 기존 S2 소스/기본값은 보존한다.
