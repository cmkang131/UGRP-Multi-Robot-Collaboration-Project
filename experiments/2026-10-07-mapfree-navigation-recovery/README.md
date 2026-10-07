# 공개 navigation 평가 어댑터 v2

구현 전 사전 등록과 변경하지 않은 성공 기준은 [public navigation §7](../2026-10-07-mapfree-public-navigation/README.md#7-평가-어댑터-v2-사전-등록-구현-전-2026-10-07),
커밋 `e194bb59`다. 이전 v1/실패 자료는 보존한다. 결과는 개발/과거 실패 진단/새 확인을 분리한다.
순수 2D 오프라인만 사용하며 MuJoCo·모델 호출·패키지 설치0. PR #409 DRAFT, 병합하지 않는다.

## 구현·새 시작점 등록 (실행 전)

사전 등록 `e194bb59` 및 첫 도크 HOST_SETUP_ERROR 보완 `b333019d` 뒤 구현했다.
[cohort.json](cohort.json)은 새 I/J×5701/5702 32쌍, 도크 원점/이동/거부24후보와 출처 해시를 담는다.
모든 배치의 선택점은 원 도크에서 동쪽 .10 m다. 실제 S2 reset에서 출발한 주행 결과가 아니다.
첫 실패의 빈 파일도 `cohort-host-error-empty.json`으로 보존했다. 기하 후보는 과제 결과로 선별하지 않았다.

`navigation=public_ros_v2`는 별도 actor/runner다. v1 파일·원 센서 모델·B v3는 변경하지 않았다.
원본 라이선스/바이트/포트 경계는 [SOURCES](../../third_party/mapfree_navigation_recovery/SOURCES.json)와
[설명](../../third_party/mapfree_navigation_recovery/README.md)에 있다. ROS 전체 동작과 동등하다고 주장하지 않는다.
Spin .5 rad/s, curvature 최소 반경 .24 m, 보정 후 명령 포화는 UGRP 속도/크기 어댑터다.
Nav2의 동작 순서/거리/대기/횟수는 그대로지만 원본 acceleration, ROS BT scheduler는 실행하지 않는다.
2 s 관측+1 s 행동이 회복 중에도 비용에 들어가며 spin/backup 제한은 modeled10 s다.

기존16 + 새8 =24 시험 통과: off bytes, 원본 해시, 회복 순서/상한, carrot 예측,
static/current obstacle 보존, valid setup, actor import 경계, 관문29/32 차단.
로컬 패키지 설치/새 venv0, CPU 시간 벤치마크가 아니므로 lock 미사용.

## 수정 전후: 같은 원인 재발, 규칙에 따라 중단

소스 `c2b5b12a`를 커밋·push한 뒤 **이미 본 실패10건만** 원 좌표 그대로 재생했다.
시작 겹침4건을 새 좌표로 바꿔 성공으로 세지 않았다. 새 generator의32쌍과 이 비교는 별개다.

| 원 실패 / 각2 seed | 원 v1 → v2 종료 | modeled 시간 s | B 가시/검출 | 충돌 예측 거부 tick |
|---|---|---:|---:|---:|
| s1/H | 시작 beam_1 겹침 → 동일 | 0 → 0 | 0 → 0 | 0 → 0 |
| s4/H | 시작 beam_1 겹침 → 동일 | 0 → 0 | 0 → 0 | 0 → 0 |
| s4/G | budget → recovery_exhausted | 600 → 161 | 0 → 0 | 1640 → 14 |
| s5/G | budget → recovery_exhausted | 600 → 131 | 170 → 14 | 1687 → 14 |
| s8/H | can_1 충돌 → 동일 | 2.7 → 2.7 | 0 → 0 | 0 → 0 |

**B 0/10 → 0/10.** 두 oracle seed는 중복 궤적이다. 정지 반복 tick 감소는 탐색 성공 향상이 아니다.
s4/G·s5/G 모두 clear2/spin2/wait1/backup1의6회를 소진했다. 회전2회와 후진1회는
관측 비용 지도 기반 사각 충돌 예측이 거부했다. 몸이 이미 실제 벽과 겹친 종료는 아니며,
글로벌 NavFn 경로가 있다는 것과 그 자리에서 사각 몸으로 추종/회복이 가능하다는 것은 다르다.
clear가 정적 벽을 지우지 않으므로 이 불일치를 해결하지 못했다. 900 s로 늘려도 131/161 s에
회복 상한으로 종료해 시간 예산 부족이 이번 정지의 직접 원인은 아니다.

s5의 3회 이상 B track 병진 최대는 **8.28e-14 → 2.66e-5 m**, 여전히 .05 m 기준 미달이다.
B 검출 문턱/시간 누적 조건은 완화하지 않았다. 14회 모두 oracle 참 검출이어도 확인되지 않는다.
s8의 .2107 m 앞 캔은 SEARCH/CLOSE 모두 영상 밖이라 물체 광선 입력이 없다. static map에는
동적 물체가 없고, 이 가려진 칸을 GT로 막지 않았다. 빈손 footprint 조건이며 운반 평가로 보고하지 않는다.

원 v1의 **22/32 결과는 그대로**다. 이번 실패 부분집합을 기존 성공22건과 합쳐 새22/32라고 쓰지 않는다.
**동일한 추종 정지·사각지대 접촉이 재발하여 사용자 중단 규칙이 발동했다.** 추가 수정/튜닝/실행을 멈췄다.
나머지 기존 A/C16 개발 및 **등록한 새 I/J32 확인은 미실행**, (a) 새 관문은 미평가,
(b) frontier oracle·(c) 현실 잡음도 미실행이다. 확인용 freeze 파일을 만들지 않아 실행기에서도 개봉할 수 없다.
기존5개 성공 기준과 ≥30/32 관문은 바뀌지 않았고 새 통과 판정은 없다.

[10건 개별 표](results/tables.md) · [원 수치 비교](results/failure-comparison.json) ·
[중단 판정](results/summary.json) · [원본/회귀 검증](results/verification.json).

## 재현·옵션·보존

| 선택 | 의미 |
|---|---|
| `navigation=off` | 기본, 기존 출력 bytes/객체 그대로 |
| `public_ros_v1` | 기존 공개 코어/600 s 평가 경로 보존 |
| `public_ros_v2` | 별도 recovery actor + 정적 층 보존 + RPP carrot/곡률 어댑터,900 s |
| `--cohort diagnostic` | 이미 본 실패10 원 좌표; 확인 결과로 사용할 수 없음 |
| `--cohort development` | 이미 본 A/C16, 이번 중단으로 미실행 |
| `--cohort confirmation --freeze …` | 새32, 정확한 소스/설정/manifest 고정 파일 필요; 이번 미개봉 |
| `--stage b/c --gate-a …` | 같은 소스·새32 raw의 a 통과 필요; diagnostic을 주면 거부 |

```sh
# 이미 수행한 진단 명령 기록. 이번에는 재실행하지 않음.
PYTHONPATH=outputs/self-map-plot-deps /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  experiments/2026-10-07-mapfree-navigation-recovery/code/run_recovery.py \
  --navigation public_ros_v2 --cohort diagnostic --stage a \
  --output outputs/mapfree-navigation-recovery-diagnostic-v2
```

원본 위치/크기/SHA256은 [artifacts.json](results/artifacts.json)에 보존한다. 로컬 raw 보존이며
원격 raw 백업이 아니다. 원 v1 봉인 source와 B v3 hash, 새 실행 source를 재대조했고,
diagnostic을 확인 관문으로 넘기면 `GATE_SOURCE_OR_COHORT_MISMATCH`로 차단된다.
새 코드8 + 기존16 시험24개 통과. MuJoCo·모델·렌더 호출0, 사용자 미추적4파일 변경0.
TensorBoard는 기존 사용자 결정대로 생략했다. PR #409 DRAFT·병합 없음.
