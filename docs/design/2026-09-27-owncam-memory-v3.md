# 자기 카메라 관측 기억 memory_v3 — 개발 후보

2026-09-27, issue #217. 기준 worktree HEAD `367b40da`의 v2와 기록은 보존한다.
이 문서는 단위 시나리오로 확인한 구현 설계다. 코호트·물리 성공·속도 개선을 뜻하지 않는다.

## 변경

| 파일 | 역할 |
|---|---|
| `harness/owncam_pose_guard_v3.py` | 명령 누적 이동·자기 추정 궤적, likelihood/innovation 일관성, 보고 공분산 보강 |
| `harness/owncam_memory_v3.py` | 존재 확률 트랙, far 회피, 시야 기반 부재·빈 바닥 증거, 별도 동료 주장 |
| `harness/owncam_drive_mem_v3.py` | 주행 중 새 회피 영역 반영, 도착 재관측과 유한 재시도 |
| `harness/m1_owncam_memory_v3.py` | 파지·배치 재확인, 탐색 사각지대의 두 번째 관측점 순회 |
| `scripts/run_m1_owncam_memory_v3.py` | off / memory_v2 / memory_v3 선택, DRAFT 실행 거부, 입력 소스 해시 기록 |

기존 기하·상자 KF·대응·기본 스킬을 상속/호출하고 v2 파일은 변경하지 않는다.
표준 workflow는 `zone-m1-owncam-memory-v3-run`이다. 새 의존성은 없다.

- **고정 신선도:** 잠정 개발값은 8 SIM s와 0.12 m다. 직선 변위뿐 아니라 명령 적분 거리와 자기 추정 누적 경로 중 큰 값도 제한한다. 왕복으로 원위치에 돌아와도 신선해지지 않는다. 이 거리는 실제 이동의 측정값이 아니다.
- **과신:** PF 재설정 전 특징당 log-likelihood와 예측→관측 갱신의 정규화 혁신을 검사한다. 일관된 새 프레임 2개가 필요하고, 불일치/만료 때 xy 0.12 m·yaw 8°의 불확실성 하한을 공분산에 반영한다. 이미 보강된 보고서를 다시 읽어도 중복 팽창하지 않는다. 짧은 look은 현재 dwell의 두 근거가 있어야 조기 종료한다. PF 입자 자체는 수정하지 않는다. 정규화 혁신의 χ² 문턱은 진단 근사이며 보정된 확률 보장이 아니다.
- **far 회피:** near 확정 전부터 p ≥ 0.20인 트랙을 반경 `0.03 + 2σ`의 회피 사각형으로 반영한다. v2의 5 cm 추가 여유 상한을 쓰지 않는다. 반복 far 프레임으로 거리 불확실성이 부당하게 작아지지 않게 하한을 둔다. far 목표 관측점도 이 영역과 로봇 여유 밖에 둔다.
- **존재:** `p ← p exp(−λΔt)` 후 검출은 `p(1−P_M)/(p(1−P_M)+(1−p)P_F)`, 보였어야 할 미검출은 `pP_M/(pP_M+(1−p)(1−P_F))`로 갱신한다. λ=0.005/s, near `(P_M,P_F)=(0.25,0.10)`, far `(0.60,0.25)`, absent ≤0.10, confirmed ≥0.95가 개발 초기값이다. 0.4초보다 가까운 프레임은 독립 증거로 누적하지 않는다. confirmed에는 near 2회·자세 일관성·σ≤0.05 m도 필요하다.
- **부재:** 2σ 영역과 상자 크기가 신뢰 가능한 거리·FOV 안에 있어야 한다. 정적 벽과 자기 영상에서 검출한 전경 상자의 가림을 검사한다. 시야 밖·먼 거리·불확실한 위치·짐에 가림·모호 대응은 miss 갱신 없이 시간 생존 사전분포만 적용한다. 검출하지 못한 가림까지 증명하는 깊이 센서는 없으므로 이 보수적 가시성 모형도 dev에서 감사해야 한다.
- **행동 직전:** 도착은 새 look, 파지 제어 진입은 새 자기 목표 관측+자세 확인, 배치는 새 자기 슬롯 빈칸 관측+자세 확인을 요구한다. unknown은 배치 허가가 아니다. 도착 재확인은 최대 2회, 조작 게이트는 최대 3회 뒤 미확인 종료한다. 파지 진입 이후의 시각 lock·부착 검사는 기존 스킬이 수행한다. 재확인 실패가 누적되어도 스킬로 우회하지 않는다.
- **탐색:** 기존 관측점에서 못 찾으면 서쪽 0.45 m의 두 번째 순회를 한 번만 한다. 알려진 바닥이라는 이유로 이 순회의 pan을 생략하지 않는다. 정적 카메라 기하에서 0.27 m 앞의 사각 영역이 0.72 m 앞에서는 보이는 것을 검사했다. 실제 검출·도달은 미검증이다.
- **들은 주장:** 자유 한국어 문자열과 정형 내용에 똑같이 `(sender, observed_at)` 참조를 붙여 `peer_claims`에 보관한다. 관측 시각 기준 TTL 12 s, 같은 참조 재수신은 나이나 확신을 늘리지 않는다. 자기 KF·존재 확률·조작 허가에는 합치지 않는다. 메시지 생성/전송·평가 파서는 이번 구현에 없다.

## 검증과 다음 단계

`tests/test_owncam_memory_v3.py`는 s161/s166의 **실패 기제**와 과신·miss·사각지대를 합성 입력으로 재현한다. 실제 seed 궤적 재생이 아니다. CI의 `TEST_PATTERNS`에 등록했다. [검증 기록](../../experiments/2026-09-27-zone-owncam-memory-v3/README.md)을 따른다.

현재 제어기 연결은 **interim tag provider**다. 기억 핵심은 provider와 분리되어 있으나 PR #227의 비전 위치 추정·진단 scalar 어댑터는 아직 연결하지 않았다. 하중 상태의 슬롯 가시성, 보수적 회피에 의한 경로 차단, 재확인 거부에 따른 성공률은 개발 실행에서 확인해야 한다. 개발값을 test로 조정하지 않는다. [DRAFT 사전등록](../../experiments/2026-09-27-zone-owncam-memory-v3/prereg_DRAFT.json)은 새 dev/test seeds·예산·게이트를 제안하며 coordinator가 최종 등록한다.

## 참고 자료

- PR #230, [로봇 기억 문헌 조사](https://github.com/kcm0127-dotcom/ugrp/blob/3174c2f8882bf3dfbfb211be64f3f02023d762d8/docs/design/2026-09-26-memory-literature.md), 특히 4.2·4.4·4.5절. 해당 원격 참조를 `git show`로 읽었다. coordinator의 #217 결정에 따라 양 조건 모두 발신자·관측 시각 참조만 사용한다.
- Rosen·Mason·Leonard, *Towards Lifelong Feature-Based Mapping in Semi-Static Environments*, ICRA 2016, [DOI](https://doi.org/10.1109/ICRA.2016.7487237). 지수 생존 Bernoulli 모형은 PR #230의 유도를 독립 구현했으며 LGPL 코드는 복사하지 않았다.
- Wong·Lozano-Pérez·Kaelbling, *Not seeing is also believing*, ICRA 2014, [MIT](http://hdl.handle.net/1721.1/100724); Liu 외, *DynaMem*, [arXiv](https://arxiv.org/abs/2411.04999). PR #230에서 정리한 ‘부재 증거와 증거 부재 구분’ 설계를 참고했다.
- [v2 결과·실패 분석](../../experiments/2026-09-26-zone-owncam-memory/README.md), `harness/owncam_memory_kf.py`의 기존 MIT KF/대응 구현, `harness/owncam_localizer.py`의 기존 PF 진단값. 새 성능 근거로 합산하지 않는다.
