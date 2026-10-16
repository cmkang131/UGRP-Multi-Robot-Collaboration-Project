# search18 — 몸체 충돌 검사·실제 시작 노드·빈 공간 지우기 (기본 off 토글 3개)

2026-10-15 · PR #484 · `claude/e2e18-grasp-rootcause`. 기준 search17 `4fdf7f84`.
새 물리 측정·Mac 시뮬레이션·렌더·원격 접속·모델 호출 0회. 아래 수치는 저장 입력의 **판정(결정) 재생**이지 물리 결과가 아니다.
원인 분석: `outputs/e2e18-admin/analysis/beam-search17-4fdf7f84/report.md` (실패 4건 315709, 8311702, 8311709, 8311711).

## 토글 (모두 기본 off, `--search18-*`)

| 토글 | 변경 | 대상 |
|---|---|---|
| `search18_footprint_v1` | 원판 r=0.13 대신 실제 차체 0.185×0.160 m 직사각형, 위치오차 p90 65 mm 여유(정확한 유클리드 거리). 팔·집게 쓸림은 기존 `issued_sweep_reason` 검사를 유지(직사각형에 안 넣음) | 315709, 8311709 |
| `search18_start_plan_v1` | A* 시작 노드 = 실제 위치(격자 스냅 칸 아님, 연결선 검사), 재계획 실패 시 재검증한 마지막 유효 계획 유지 | 315709 16.4초 정지 |
| `search18_free_space_v1` | 상대 ghost가 자기 카메라 18도 원뿔·2 m 안, 가림 없음, 같은 프레임에 다른 랜드마크가 보이는데 상대가 안 보이면 0.3초 뒤 ghost 삭제. 시간 만료로는 풀지 않음 | 8311702, 8311711 |

## 재생 결과 (15 실행 = 재현 3 + 신규 12, 8408 로봇 틱, 기준 불일치 0)

성공 11건 중 판정이 나빠진 건수(1틱이라도): footprint **9/11**, start_plan **0/11**, free_space **0/11**, 세 개 묶음 **9/11**.

| 실패 시드 | footprint(65 mm) | start_plan | free_space |
|---|---|---|---|
| 315709 | 판정 변화 26틱, 경로없음 해소 2, 새 경로없음 16 | 변화 9틱, 경로없음 해소 5, 악화 0 | 변화 4틱 |
| 8311702 | 변화, 새 경로없음 22 | 변화 15틱(악화 0) | 상대 대기 91→22틱(약 10.0초 해제, 기준은 16.5초 시한 핸드오프) |
| 8311709 | **변화 0** (목표 자리가 65 mm 여유로도 막힘) | 변화 0 | 변화 0 |
| 8311711 | 새 경로없음 47 | 변화 17틱(악화 0) | r2 대기 120→100틱 |

판정 변화: 실패 4건 중 **묶음 3/4**(8311709 제외). footprint를 뺀 두 토글만으로도 3/4(315709·8311702·8311711), 성공 악화 0/11.
free_space의 1틱 반사실 지표 "악화"(8311702에서 36/38)는 지우기 대기 0.3초 카운터가 1틱 분기마다 0으로 돌아가는 측정 인공물이며, 지속 shadow 컨트롤러로 다시 쟀다. shadow는 기록된 명령만 받으므로 첫 명령 분기 이후 움직임은 평가할 수 없다.
성공 실행에서도 start_plan은 7–43틱, free_space는 315724에서 22틱 판정이 바뀌었다(악화 0). 실제 궤적 영향은 **미확인**.

### footprint가 안 되는 이유와 마진 스윕
실제 몸체 반폭 0.0925×0.080 m에 65 mm를 더하면 0.1575×0.145 m로, 대체하려는 원판 0.13 m보다 어느 방향에서나 크다. 성공 실행도 몸체와 물체 사이 15 mm 이내로 지나간다(15 mm 마진에서 펄스 거절 발생). 실패 4건의 틈은 5–16 mm다. 즉 "여유 ≥65 mm" 요구와 "성공 11건 악화 없음"은 같이 만족할 수 없다.
분석 전용 스윕(성공 11건 중 악화 건수 / 실패 경로없음 해소 합): 65 mm 9/11, 45 mm 9/11, 30 mm 9/11, 15 mm 8/11, **0 mm 0/11**(해소: 315709 5, 8311709 4, 8311702 3, 8311711 1). 마진을 줄이는 것은 사용자/조정자 결정 사항이라 코드 기본 65 mm 유지, 스윕은 `ANALYSIS_OVERRIDE`로만 가능(CLI 노출 없음).
이에 따라 GCP 진단 대기열은 start_plan+free_space만 켜고 footprint는 보류로 적었다.

## 확인 범위
- 시험: `tests/test_grasp_act_search18.py` 14개, 관련 기존 시험 169개 통과(admission, batch, goal_set, search15/17, visible_only, recovery).
- 원본/해시: `search18-replay-summary.json`, `outputs/e2e18-admin/analysis/search18/`.
- 미확인: 물리 성공 변화, 팔·집게 영역의 직사각형 포함 여부(미포함, 기존 sweep 검사 유지), 원격 시드 재고(로컬 15 시드 + 신규 8311712–8311723 로컬 충돌 0).

## 참고 자료
- Nav2 inflation layer (내접 반경 안은 치명, 바깥은 감쇠 비용; 확인): https://docs.nav2.org/configuration/packages/costmap-plugins/inflation.html
- Daniel, Nash, Koenig, Felner, "Theta*: Any-Angle Path Planning on Grids", JAIR 39:533–579, 2010 (확인): https://arxiv.org/abs/1401.3843 — 이번에는 Theta*를 구현하지 않고 실제 시작점 연결선만 A*에 적용함.
- Elfes, "Using Occupancy Grids for Mobile Robot Perception and Navigation", IEEE Computer 22(6):46–57, 1989 (서지 확인): https://faculty.iiit.ac.in/~mkrishna/ElfesOccupancyGrids.pdf
- Thrun, Burgard, Fox, Probabilistic Robotics, MIT Press 2005 (빈 공간 갱신): URL 미확인.
- ROS costmap_2d footprint 충돌 검사 문서: URL 미확인(Nav2 문서로 대체).
