# s3next: 호스트 v3 마운트 수정 후 3대 재시험 사전 기록

2026-10-09 감독 지시. 기존 s14201은 보존하며 새 mixed DEV 스모크는 **1회**만 실행한다. main `58c41266` merge는 관련11시험 통과 뒤 `452f06db`로 push했다. #419의 공통 heading 기본 on 변경을 받은 뒤 새 소스를 고정한다. 현재 잠금 `codex/s2-heading`의 실행을 침범하지 않는다. 연구 실행 우선, agent_lock 획득, nice0, dev_light다.

## 수정 위치와 첫 렌더 계약

실제 수정은 **호스트 `sim/s3_camera_binding.py` → S2의 `bind_camera()` 재사용**이다. `sim/zone_s3_no_prior.py`는 world 생성 직후 세 controller에 이를 적용한다. 기존 `f965ad15`에는 이 호스트 옵션과 오프라인 합성 옵션이 모두 있었으나, 기존 v142는 기본 off로 봉인돼 있어서 물리 수정을 켠 번들이 아니었다. 새 재시험 번들은 호스트 `v3_persistent_v1`을 명시적으로 켠다.

`harness/zone_s3_recorded_camera.py`는 예전 영상의 마운트 오류를 분리하는 **진단 전용**이며 실행 보정이 아니다. 새 물리 호스트는 해당 옵션이 off가 아니면 world 구성 전에 거부한다. 제어기의 v3 외부 파라미터·K/D·카메라 외관·지도·문턱은 바꾸지 않는다.

첫 렌더 검사는 실제 공통 `_render_rgb_direct()`의 mount sync→renderer update→render 경로를 호출하고 S2와 S3의 local pos/quat, world pose, intrinsic, resolution 기록이 같은지 비교한다. 회귀는 정적 MuJoCo 모델+renderer double이며 물리 step0·실제 OpenGL 영상 시험은 아니다. S2 v141 s1065의 실제 첫 camera-pose 기록을 작은 fixture로 보존해 local pos/quat 바이트 값도 대조한다. 실제 스모크에서는 렌더 스레드의 같은 physics lock 안에서 `eval_only/<robot>/render_camera.jsonl`을 남기고 첫 프레임 및 모든 렌더의 local pos/quat를 S2 v3 상수와 대조한다. world pose는 로봇·관절 자세에 따라 달라지므로 서로 다른 시작의 세계좌표가 같다는 요구가 아니다. 이 기록과 측정 qpos는 평가 전용으로 제어기에 전달하지 않는다.

## 공통 렌더 경로 점검

| 장면/경로 | 실제 바인딩 | 같은 누락 여부와 확인 범위 |
|---|---|---|
| S2 v141 | `sim/s2_real_output.py` → `s2_realism_camera_binding.PhysicsBackend/bound_world` | v3 configure/sync 고정, 기준 경로 |
| S3 v142 원본 | XML v3만 적용, 공통 legacy sync 유지 | **누락 있음**, s14201 원인 |
| 새 S3 호스트 옵션 | `s3_camera_binding.attach` → 같은 S2 bind | 누락 보완, 렌더 시점 pose 회귀 및 실제 기록 추가 |
| S4 `codex/s4-llm-host` | `harness/s4_llm_host.py`는 주입된 S3 RobotLink만 사용, 자체 물리 launcher/renderer 없음 | 독립 장면 누락은 해당 없음; 원본 v142를 주입하면 같은 위험, 새 호스트 번들로 연결해야 함 |
| 자기 지도 수집 `claude/ego-wall-map` | `sim/active_wall_map.py` 생성 직후 `old.old.bind_camera`; `wall_parallax_strafe.py`의 S2 동일 함수 | 바인딩 누락 없음(정적 호출 경로 확인); 새 물리 재검증은 아님 |
| 자기 지도 S2 교환 `codex/ownmap-s2` | `scripts/replay_ownmap_s2.py`가 저장 S2 RGB를 읽는 오프라인 전용 | 자체 렌더 없음; 원본 S2 수집 경로의 바인딩을 승계, 신규 호스트 검증 아님 |

조회한 원격 SHA는 `scene-audit-sources.json`에 고정했다. 다른 작업 worktree는 수정하지 않았다.

## 0/3의 의미와 유지할 기준

아래는 **과거 s14201에 진단용 마운트 합성만 적용한 재생의 마지막43.55초**이며 앞으로 렌더할 수정 호스트의 결과가 아니다.

| 로봇 | XY 오차(m) | yaw 오차(도) | σxy(m), 기준≤0.05 | 연결모드 수 | 분리 판정 |
|---|---:|---:|---:|---:|---|
| r1 | 4.262512 | 179.602496 | 0.270649 | 6 | 실제 위치/방향 모두 틀림; 문턱을 풀어도 정확 성공이 아님 |
| r2 | 0.064795 | 0.257563 | 0.145810 | 54 | 점 추정은 eval 범위 안, σ 미통과; 추가 사후분포 검사 없이도 미수렴 |
| r3 | 0.073825 | 0.884851 | 0.080392 | 3 | 점 추정은 eval 범위 안, σ 미통과; 추가 사후분포 검사 없이도 미수렴 |

즉 다중모드 인증을 추가해서만0/3이 된 것이 아니다. r2/r3에서 보수적 불확실성이 남은 것은 확인했지만, 한 원본의 마지막 값만으로 3대 장면에 기준이 과도하다고 결론 내리지 않는다. σ≤0.05m, yaw σ≤5도, eval XY≤0.25m/yaw≤15도와 posterior 인증의 기존0.5m/1모드를 **변경하지 않는다**. 실제 호스트 수정 후에도 참 가설 소멸이 확인될 때만 AMCL 무작위 주입·우도 바닥값을 별도 사전 옵션으로 검토한다. 이번1회에는 추가하지 않는다.

## 재시험 조건과 중단

- 시작 prior 없음·own RGB/정적 지도/자기 명령만, top RGB·GT 제어·weld 금지.
- 혼합 주문은 r1+r2의 beam_1→B와 r3의 cyan_1→B. 원본과 같은 시작 배치를 사용하되 새 실행 번들/출력 폴더에 기록한다.
- #419 공통 heading 기본 on 소스를 merge해 세 로봇의 주행 경로에 적용된 범위를 검증하고 실행 source SHA를 고정한다. 공개되지 않은 구현을 복제하거나 heading off로 먼저 실행하지 않는다.
- dev_light 보수 가드는 기록만, 실제 낙하/기울기/GO 실패/집게 이탈/실행 오류는 정지한다. 기존 SIM1800초·wall10800초를 유지한다. 실행 전 raw 상한은3GiB로 등록한다(현재 여유13.23GiB, 원본43.27MB/45.25초로부터1800초 약1.72GB+평가 로그 예산0.5GiB; 실제 크기 보장은 아님). 10GiB 여유와 ENOSPC=HOST_ERROR를 유지하고 기존 raw는 지우지 않는다.
- 로봇별 수렴·오차·배송·실패, 문 양보/교착, 충돌, wall/SIM을 eval_only로 판정한다. 결과를 본 뒤 기준 변경/재실행하지 않는다. 같은 원인2회면 원인 분류와 표준 방법 조사 후 보고한다.
- 새 실행의 첫 RGB 마운트 값, 4배속 대표 영상, 원본 해시 및 TensorBoard를 남긴다.

참고: [S2 바인딩](../../../sim/s2_realism_camera_binding.py), [MuJoCo 카메라 좌표](https://mujoco.readthedocs.io/en/stable/APIreference/APItypes.html#mjdata), [Nav2 AMCL PF](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/pf/pf.c). 기존 s3diag 출처와 요인 비교는 [이전 진단](../s3diag/README.md)을 따른다.

예약: 새 번들 `zone-s3-host-heading-v144`, workflow `7.37.0`, seed14201, 첫 실행만 허용. 원격 main·열린 PR 최대143/7.36.0을 조회한 뒤 #416 본문과 #419 조정 코멘트에 예약했다. 최신 main의 공통 exact-speed 변경도 `21af8635`로 merge·13 PASS·push했으며 초기화/관측 동등성과 실제 성공은 구분한다.

실행기 `require_heading_source`는 등록된 공통 heading 기본 on 커밋이 없거나 실행 SHA의 조상이 아니면 world/출력 폴더 구성 전에 거부한다. source를 채우기 전에는 계획 조회만 가능하다. 누락 의존성 거부 시험1 PASS(43.03초); 실제 통합 검증은 merge 뒤 수행한다.

18:20 확인: #419 최신 `fddc2f67170fecd63da02ccbf9522e2fad7865e3`는 결과/이미지 기록 추가이며 제어 코드는 여전히 기본 off다. 공통 heading 기본 on 의존성은 미도착, 잠금은 비어 있지만 새 물리 실행0회로 유지한다. #416은 MERGEABLE이며 작업 트리는 깨끗하다. 담당의 추가 push 또는 감독의 연결 범위 답변 뒤 merge·통합검증·1회 실행을 이어간다.

### s3run: r1 선행 진단 완료

[보정된 동일 입력의 r1 단일 요인 재생](../s3run/README.md): 순서만 S2화하면4.263m 유지, seed만1065면10.30s/0.032m 정확 수렴. 초기 유한 표본과 재표본화 뒤 남은 근사 가설의 우세로 분류하며 정확 영역 입자 전멸은 아니다. 추가 회복·seed·문턱 변경 없이 호스트 v3/heading smoke를 관측하기로 실행 전에 기록했다. 이제 #419의 공통 기본 on 커밋을 기다린다.
