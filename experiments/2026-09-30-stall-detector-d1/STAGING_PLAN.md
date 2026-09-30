# D1 후속 staging/probe 계획 — 실행하지 않은 초안

이 문서는 기존 코드의 손잡이와 부족한 지원을 구분한다. **물리 실행 코드 추가 없음**.
분석 기준은 main `a8094cc14e098a55483f53a3c49bf6a0b116043d`이다.
확증 정의·실패 분모·예산은 [PREREG_DRAFT.md](PREREG_DRAFT.md)를 따른다.

## 기존 기능으로 할 수 있는 것

`scripts/run_pair_stage_probes.py::parser/build_cases/envelope_cases`와
`harness/pair_stage_probe.py::teacher_cases/_grid_offsets/offset_pose`는 다음을 제공한다.

- `--stage carry --sources teacher --legs`: 정적 route 구간별 교사 배치(축 0–2/6–7, 횡 3–5),
  단계별 실행. chain은 별도이며 `--chain-stop-leg 0/1`로 문 구간까지만 자를 수 있다.
- `--env-y`, `--env-yaw-deg`, `--env-x`: 실제 빔 배치와 고정 coarse sheet를 분리한 격자.
  `--env-bias-y-m`, `--env-bias-yaw-deg`, `--env-prior`: 시작 사전분포 오류를 조작한다.
  이는 staging 정보이며 D1이 읽을 정보가 아니다. `env-x`는 route[0]의 x로 leg translation이 적용된다.
- `--cells`는 기존 same/opp 오프셋 셀을 선택한다. `teacher_cases(rows=...)`는 로봇별 다른
  오프셋을 받을 수 있지만 임의 행을 지정하는 CLI는 없다. `--seeds`와 `--nominal-seeds`는 PF 등
  시드 축이며 같은 배치에 PF 시드만 바꿔 독립 정체 표본으로 세지 않는다.
- `--render-profile`: `sim/render_profile.py`의 `shadows_v1`, `floor_light_v1`,
  `noshadow_bright_v1` 같은 **영상만 바꾸는** 프로필. 물리·카메라 FOV/외관은 유지한다.
- `--policies b-v6h --door-relax adv`: `harness/zone_pair_door_relax.py::install`의 probe 전용
  가드 완화. `adv`도 무제한 해제는 아니며 잔여 veto를 로봇당 누적 **3 명령초**만 무시한다.
  `k1g`는 σ 배수 1, yaw 게이트 5°/4°이다. 등록된 제어기와 동등한 실행으로 보고하지 않는다.
- `--progress-relax p1/p2`도 probe 전용이다. D1 오프라인 채점에는 필요 여부를 봉인 전에 고정한다.
  p2를 안전 보장으로 쓰지 않는다. 기존 제어기 선중단이면 유도 실패이며 실제 정체로 세지 않는다.
- `--contact-track`: `run_case`의 `ProbeHost._contact_kinds` → `track_wall_contacts`,
  `close_wall_episodes`, `contact_outcome`. 벽(`zone_wall_*`)과 r1/r2/빔의 접촉·침투만 **평가**에 기록한다.
  로봇끼리/막대↔파트너 접촉의 완전한 추적기는 아니다. `--pf-track`의 PF/GT도 D1 입력에서 제외한다.
- `run_case`/`save_checkpoint`의 원본에는 자기 영상·발행 명령과 별도 `eval_only/trace.jsonl`이 있다.
  매 프레임 저장/시각은 `harness/zone_own_team_host.py::_capture_raw`에서 확인해야 한다.
  이번에는 원본 영상을 로딩하거나 기존 실험을 재실행하지 않았다.

## 정체 종류별 연결과 필요한 추가 지원

| 기전 | 기존 손잡이·기록 | 부족한 지원(후속 PR에서만 구현) |
|---|---|---|
| 벽 칸막이/뒤바퀴 접촉 | carry L1, env-y/yaw/bias, b-v6h.adv + contact-track. 양성 대조 `4194d34c-posAdv2R/2L`, `posAdvM`의 y ±0.30/0.34 또는 −0.20/−0.24, bias ∓0.25/0.29에서 r2 뒤바퀴↔divider가 막힘 | 새 배치·시드를 조작 성립용 dev에서 먼저 고정. 기존 raw/같은 배치는 확증 재사용 금지. 기존 손잡이로 시도할 수 있으나 새 case 성공은 아직 미확인 |
| 빔 끝↔문틀 | env-y/yaw로 빔 끝을 divider 끝에 향하게 배치; contact tracker가 beam-wall도 기록함 | 기존 양성 대조는 **바퀴 접촉**이다. 빔 접촉만 유도하는 배치/회전·높이 조작과 충돌 가능한 문틀 형상이 필요. 태그 상자는 시각 전용. 물리 형상을 추가하면 정적 지도와 장면을 함께 버전/해시화 |
| 한 로봇만 막힘 | teacher_cases의 r1/r2 개별 offsets, run_case의 placement_xyyaw 및 r3_xyyaw setup-only 경로 | 로봇 하나의 바퀴 앞에만 정적 장애물 배치하는 case schema/CLI·Scene adapter. 고정되지 않은 r3를 확실한 벽 대용으로 쓰지 않는다. 한쪽/양쪽 STALL·파트너 진행·빔 미끄럼을 eval-only로 채점 |
| 횡 미끄럼/마찰 급증 | carry --legs 3/4/5, 동일 정상 contact profile. 기존 lateral-scale 진단은 **PF/제어 가정 변경**이어서 물리 마찰 조작을 대신하지 못함 | 정적 바닥 패치별 마찰과 좌/우 바퀴 접촉 조건의 setup-only 지원, 실제 적용값 기록. 동적 friction spike를 쓸 경우 접촉/GT로 발동하지 않고 사전에 정한 SIM시각에만 조작. 어느 경우도 D1에 마찰값/발동 시각 전달 금지 |
| 시작부터 막힘 | env-x/y/yaw, teacher_cases 배치, 시작 사전분포를 분리 가능 | 비침투 정적 접촉 배치와 시작부터 자기 병진 명령을 보존하는 수집 지원. initial placement의 겹침/교사 안정화 실패는 HOST/STAGING 실패와 구분. 기준 0 또는 부족은 D1 누락이며 버리지 않음 |

문 완화 README §3의 **8/8 접촉**은 서로 다른 기전 8개가 아니다. 실제 접촉 물체는
`r2__wheel_rr/r2__wheel_rl`와 `zone_wall_divider_1/2`, 빔 접촉은 없었다.
침투 0.37–0.39 mm와 15°/5 mm hard-limit 미발동도 안전 증거가 아니다.
기존 수치는 배치 후보의 출처이며 이 task의 새 측정값이 아니다.

## 지원을 넣을 후보 파일·함수(지금 수정하지 않음)

| 파일/함수 | 후속 최소 지원 |
|---|---|
| `harness/pair_stage_probe.py::teacher_cases`, `_grid_offsets`, `setup_variant` | 기전 ID, 로봇별 obstacle/마찰/배치/속도 셀, 독립 물리 시드·예비 셀·기대 영향 로봇을 가진 setup-only 명세. GT 라벨을 detector payload와 분리 |
| `scripts/run_pair_stage_probes.py::parser`, `build_cases`, `envelope_cases` | 지원되는 조작과 속도/지속시간 CLI, dev/frozen cohort manifest, 실행 전 전체 SIM/디스크 budget 검사 |
| 같은 파일 `run_case`/`install_stage` | 자기 발행 명령만 이용하는 고정 병진 수집 구간(느림/기어감 포함), 물리 조작은 Scene/setup-only에서 적용. D1이 명령/중단을 바꾸지 않음 |
| 같은 파일 `track_wall_contacts`, `stage_diagnostics`, `finish_result` | beam-end/one-sided/friction 유도 성립·각 로봇의 GT 정체·추가 밀림·가드 선중단/HOST_ERROR의 평가 전용 열. 비벽 장애물 tracker를 추가할 경우 기존 범위와 구분 |
| `scripts/zone_pair_dev_runtime.py::make_scene`(표준 Scene 하위 클래스 factory), `sim/session_scenes.py::Scene.transform/setup/record`, `sim/zone_tagged_cargo_scene.py::TaggedCargoZoneScene` | 표준 Scene adapter에 장애물/마찰 패치 주입, 지도와 실제 충돌 형상 연결·소스/설정/적용값 해시. 별도 기본 시뮬레이터를 만들지 않음 |
| `harness/zone_own_team_host.py::_capture_raw` 주변의 기록 adapter | 자기 영상/발행 명령/시각만 추출한 오프라인 입력 manifest와 평가 파일 분리; 10 fps와 영상 누락 기록. host/controller 입력에 평가 열 추가 금지 |
| `configs/simulation_workflows.json`, `scripts/sim_cli.py`의 등록 경로 | 실행 지원을 만드는 후속 PR에서 표준 관리 workflow·번들/조작 버전·기록 검증 연결. 이번 PR은 실행 경로도 새 번호도 등록하지 않음 |

기존 제어기 상수에 monkey patch를 넣어 느린 제어기라고 주장하지 않는다. 고정 명령 probe 수집과
등록 제어기의 실제 leg 출력은 다른 조건으로 기록한다. 임의 속도·friction·장애물 전용 CLI는 **현재 없다**.

## 봉인과 후속 실행 순서

1. 별도 지원 PR에서 위 조작을 구현·검토하고, 물리 잠금을 가진 담당 작업이 **개발 자료**로
   조작 성립만 확인한다. D1 ratio/k/ROI/잡음 규칙을 새 dev 결과에 맞춰 고치면 새 탐색 버전으로 남긴다.
2. 바닥/조명/leg/speed의 60셀, 30정체·예비/진단 셀, 모든 시드·실제 지원·버전·예산을 고정한다.
   교사 staging은 GT를 써도 그 정보는 D1 및 학생 제어 입력에 전달하지 않는다.
3. 독립 사전 등록 검토 뒤 코드/설정/라벨/manifest 해시를 확증 전 고정한다.
   DRAFT PR 병합 여부와 확증 실행 승인은 별개이며 이번 작업에서는 병합하지 않는다.
4. 별도 실행 승인·잠금 확보 후 자기 worktree에서 표준 관리/세션 경로로 유한하게 실행한다.
   장면/카메라/FOV/로봇/빔 외관 유지, weld OFF, 모델 호출 0, 다른 작업 프로세스에 손대지 않는다.
5. 보존된 자기 입력으로 D1을 오프라인 계산한 뒤 GT를 평가에만 결합한다. 실패 전부·분모·해시·
   HOST_ERROR·일탈·TensorBoard 로딩/보기 검증을 보고한다. 경보를 제어기에 넣는 일은 다시 별도 등록한다.

## 참고 자료

- [병합 연구 추천 D1와 수용 표](../2026-09-30-stall-detection-research/README.md#3-추천-가장-작은-검출기와-사전-등록-기준).
- [문 완화 양성 대조와 정확한 geom](../2026-09-30-door-relax-envelope/README.md#3-접촉-추적기-양성-대조-코디네이터-요청).
- [stage runner](../../scripts/run_pair_stage_probes.py), [case 정의](../../harness/pair_stage_probe.py),
  [문 가드 변형](../../harness/zone_pair_door_relax.py), [렌더 프로필](../../sim/render_profile.py).
- [표준 관리](../../docs/simulation_management.md), [입력·자료 보존 지침](../../AGENTS.md).
