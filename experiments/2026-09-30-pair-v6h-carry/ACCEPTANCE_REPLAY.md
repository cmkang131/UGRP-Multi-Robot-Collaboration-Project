# b-v6h1 인수 재생 — FAIL_HOST_ERROR (정책 동등성 미평가)

**판정: FAIL_HOST_ERROR. 지정한 lag-on 10건과 별도 lag-off sanity 1건을 시도했지만, 11건 모두 제어기 시작 전 `CGLError: invalid CoreGraphics connection`으로 종료됐다. 비교 가능한 사례는 0/10이므로 bit-for-bit PASS를 선언할 수 없다. 정책 불일치가 측정된 것은 아니다.**

실행 소스는 PR #292 head `2c863fda3fd2de2f0fc714c2367c3e81b440b530`으로 고정했다. branch `codex/v6h1-acceptance`, bundle `zone-pair-v83-carry-door-gain`, workflow `2.16.0`, 봉인 전 정책 `b-v6h1`. 등록 제어기·probe 코드·기존 봉인 파일은 수정하지 않았다. 이 기록은 인수 실행 시도의 결과이며 확증·E2E·실물·실모델 성공 근거가 아니다.

## 실행 조건과 비교 기준

사용자 지정 사례 선택으로 계획 §6의 lag-off 예시 대신 lag-on tS/tR/tX1b/tX1 원본을 사용했다. 시드·배치·beam·PF prior·coarse sheet·route·chain-stop-leg·render profile·평가 옵션을 plan.json에서 직접 보존했고 사후에도 원본 전체 해시와 입력 동등성을 확인했다. tS S07과 tX1 X01은 각 코호트의 최대 L1 끝 오차, tX1 X03 seed 913은 최소 L1 끝 오차다. tR은 작은 오차 hR2_01 및 최대 L1 오차 hR2_04 seed 913을 골랐다. tX1의 X06 HOST_ERROR 2건은 비교 기준에 넣지 않고 완료된 tX1b X06을 사용했다.

원본 실행은 `origin/claude/b-v6h-gain`의 `run_cohort.sh` / `run_all5.sh`를 `git show`로 읽었다. 원본 정책은 b-v6g 위의 probe-only b-v6h이며 k1g+p2f+pf gain fix+axial이다. 새 실행은 저장된 case를 b-v6h1로 바꾸고 probe 옵션(`door_relax`, `progress_relax`, `carry_gain_fix`, `carry_axial_lag`)을 제거한 뒤 현재 등록 worker 진입점으로 호출했다. `--policies b-v6h1` 계획과 같은 정책 선택이며 평가용 expected 값은 제어기로 전달하지 않았다.

```text
--stage chain --sources teacher --policies b-v6h1 --prior-std e2e
--chain-stop-leg 1 --render-profile floor_light_v1 --pf-track --contact-track
--workers 4 --omp-threads 1
```

| probe 옵션 | 등록 b-v6h1 필드 |
|---|---|
| k1g | loaded_k_xy=loaded_k_yaw=1.0; loaded_gate_yaw_deg=(5.0,4.0) |
| p2f | progress_arm_on_moved_fix=True |
| pf gain fix | carry_fwd_gain=0.9483378899463337 |
| axial | carry_axial_lag=True |

공통 조건은 SIM 시간, cargo_noslip_v1, floor_light_v1, 모델 호출 0, weld OFF, OMP/MKL/OPENBLAS 1, 최대 worker 4다. Python 3.12.13/MuJoCo 3.12.0/NumPy 2.5.2/OpenCV headless 5.0.0.93/Pillow 12.3.0 및 실행 Python 경로는 원본과 같다. 시작 여유 공간은 약 61 GiB였다.

## 사례별 비교

등록 SHA `없음`은 commands.json이 생성되지 않았다는 뜻이다. `미평가`는 해시 불일치나 최초 명령 차이가 측정됐다는 뜻이 아니다. 끝 오차는 mm이며 probe L0/L1 값만 존재한다. 전체 입력·원본/결과 경로·해시는 [acceptance_replay.json](acceptance_replay.json)에 있다.

| 코호트/사례/시드 | probe commands.json SHA-256 | 등록 SHA-256 | probe L0 / L1 끝 오차 (mm) | 등록 L0 / L1 | 동등성 |
|---|---|---|---:|---|---|
| tS / S01 / 911 | `70bcb8ce94ffb9396d79fb8412b1b6c99b75190985af01cd11741610d2655004` | 없음 | 56.509586742 / 50.784077900 | 미기록 / 미기록 | 미평가: HOST_ERROR |
| tS / S02 / 911 | `071532a4e2c59be92fc827815b6ba2f3c138f83ea657368e7dda65e75c331279` | 없음 | 40.981550939 / 34.658885423 | 미기록 / 미기록 | 미평가: HOST_ERROR |
| tS / S03 / 911 | `0b699a18311d11a01c53a00f6fb2e5f2ff9fbff430536b612a36c947a529b542` | 없음 | 25.388874329 / 19.643262787 | 미기록 / 미기록 | 미평가: HOST_ERROR |
| tS / S07 / 911 | `c0c5fcd8dfe2492f9d312ed7962b08456ec731516f42111aa20d4923648e2872` | 없음 | 57.882434959 / 72.123919081 | 미기록 / 미기록 | 미평가: HOST_ERROR |
| tR / hR2_01 / 911 | `5f9da3641faf4a83d3817fc772985aedaba59db13f7ca25a3f1a18e61467d76b` | 없음 | 12.897744522 / 33.173977214 | 미기록 / 미기록 | 미평가: HOST_ERROR |
| tR / hR2_04 / 913 | `cfd6df9a6e7eba01eb23b907b0a9446f75d6088196cc2c21cf39432b181fff74` | 없음 | 70.065722078 / 67.623138181 | 미기록 / 미기록 | 미평가: HOST_ERROR |
| tX1b / X06 / 911 | `d1ef368a7de5a6f85a187b710c7a0cf8422f3317290acf2c86422adacbb6a14a` | 없음 | 49.205753114 / 62.409179259 | 미기록 / 미기록 | 미평가: HOST_ERROR |
| tX1 / X01 / 911 | `2d2f77a4d529f860a5dc2ac4c98e53ece4df2cee7d2c2c152430db6c7227730c` | 없음 | 49.055252190 / 81.911474755 | 미기록 / 미기록 | 미평가: HOST_ERROR |
| tX1 / X03 / 913 | `c28c5a2e56636ed02e498ff1ae70f189e50c0d63b900798ea6cccb683c7329f8` | 없음 | 34.376950405 / 28.658383738 | 미기록 / 미기록 | 미평가: HOST_ERROR |
| tX1 / X00_F_hR2_04 / 911 | `2ae150658b670333f7357e2af48ec51059a6ae897372f938b564979ab798f98f` | 없음 | 51.040898481 / 55.709624211 | 미기록 / 미기록 | 미평가: HOST_ERROR |
| tX0 / X01 / 911 (lag-off sanity) | `f9d3bd1482ff99daa8a0e910522349cb1aa99bf161cc1c61d9686691173a0d0d` | 없음 | 69.175652130 / 124.338661973 | 미기록 / 미기록 | 미평가: HOST_ERROR |

최초로 다른 명령과 차이 크기는 **측정 불가**다. 원본 첫 명령은 t=0의 initial_servo_command지만 등록 명령 파일 자체가 없다. raw의 초기 `acceptance_receipts.json`은 없는 파일을 빈 dict로 비교해 t=0/null을 차이로 적었다. 이 값은 실제 제어기 divergence가 아니므로 본 문서와 최종 JSON에서 `first_divergence=null`, `comparable=false`, 동등성 필드 `null`로 바로잡았다. 초기 기록은 그대로 보존했다.

lag-off sanity는 프로세스 안에서 `dataclasses.replace(POLICIES["b-v6h1"], carry_axial_lag=False)` 한 필드만 바꾸는 test-only override로 시도했다. 등록 소스 파일이나 probe 패치는 바꾸지 않았다. 같은 CGL 오류 때문에 tX0-like 결과의 재현 여부도 미검증이다.

## 최초 실패 지점과 소스 대조

`scripts/run_pair_stage_probes.py:566` → `harness/zone_own_team_host.py:89` → `sim/multi_masterpi_production.py:762,822` → MuJoCo `Renderer` → `mujoco.cgl.CGLChoosePixelFormat`에서 `invalid CoreGraphics connection`이 발생했다. teacher staging, controller submission, leg 기록 이전이다. 환경의 CoreGraphics 연결이 실패한 것이 확인됐고 정확한 OS 권한 원인까지 확정하지 않았다. 물리·카메라를 끄거나 렌더 경로를 바꿔 동등성을 주장하지 않았다.

별도로 `ugrp_session.py`는 `/bin/ps` 실행이 sandbox에서 거부되어 실행기 시작을 완료하지 못했다(물리/잠금 시작 전). 이후 own Popen handle/process group을 추적하고 finally에서 정리·wait 후 release하는 raw wrapper로 실행했다. 첫 smoke 이후 wrapper가 HOST_ERROR를 중단 조건으로 처리하지 않아 나머지 선택 사례도 시도된 절차 이탈이 있다. 11건 전체를 보존했으며 오류 확인 후 물리를 다시 시도하지 않았다.

probe 모듈 네 개는 5bfd95f0/f5d83fdb 양쪽에서 읽기 전용 git show로 추출했다. 두 SHA 사이에 이 네 모듈 및 해당 worker 실행기 바이트 차이는 없다. diff와 module hash는 raw에 보존했다. 다음은 실제 정책 divergence의 확정 원인이 아니라, 유효한 재생에서 차이가 생길 경우 확인할 후보들이다.

| 대조 항목 | probe 코드 | 등록 코드 | 확인 내용 / 잠재 차이 |
|---|---|---|---|
| forward gain | `5bfd95f0:harness/zone_pair_carry_gain_fix.py:66-78` | `harness/owncam_carry_v6e.py:175-188` | 두 구현 모두 profile 재바인딩/plant-state 추첨 뒤 복사한 loaded gain[0][0]에 0.9483378899463337을 곱한다. 등록 구현은 provider 재사용 시 gain 설정도 검사한다. 물리 동등성은 아직 미평가다. |
| axial duration | `5bfd95f0:harness/zone_pair_carry_axial_lag.py:60-72` | `harness/zone_pair_executor.py:216-222; harness/owncam_carry_v6e.py:70-76` | probe는 전역 LAG_AXES를 넓히고 leg_duration wrapper에서 axial plant만 보정한다. 등록 구현은 인스턴스 axial flag와 복사한 axial calibration을 쓰며 lateral은 그대로다. 의도된 계산은 대응하지만 발행 명령 비교는 불가능했다. |
| sigma margin scope | `5bfd95f0:harness/zone_pair_door_relax.py:84-103` | `harness/zone_pair_geometry.py:26-31; harness/zone_own_guards.py:273-276` | probe의 전역 SweepGuard.margin은 모든 범위에서 1/1이다. 등록 구현은 loaded base motion만 1/1이고 접근·preclose·loaded/unloaded arm sweep은 2/2다. inter-leg regrasp에서 유효한 실행의 차이가 생길 수 있는 후보이며 현재 CGLError의 원인은 아니다. |
| yaw gate | `5bfd95f0:harness/zone_pair_door_relax.py:104-112` | `harness/zone_pair_guards.py:216-223; harness/zone_pair_executor.py:239; harness/zone_own_driver.py:37-42; harness/zone_own_sweep.py:17-42` | probe는 각 모듈의 GATE_LOADED 전역을 5/4도로 치환한다. 등록 구현은 인스턴스 profile을 guard·driver·sweep recheck에 전달한다. 향후 실제 재생 차이가 있으면 profile 전달 경로를 대조해야 한다. |
| p2f | `5bfd95f0:harness/zone_pair_progress_relax.py:58-112` | `harness/zone_pair_guards.py:171-196,603-606` | 두 구현 모두 첫 이동 발행 시각보다 엄격히 뒤의 fix에서 무장하며 접근 밖에서만 이동량을 센다. 등록 구현은 bool/infinity 시각도 거부하고 계수를 기록한다. probe는 NaN을 거부하지만 infinity를 허용한다. 저장된 정상 시각에서는 같은 규칙으로 예상되나 물리 확인은 없다. |

## 보관·잠금·검증

- raw: `/Users/changmin/projects/ugrp/outputs/v6h1-acceptance-2c863fda-20260930`
- raw cases.jsonl SHA-256: `c48e191393a11346008ea1d6e4b2ca919ca53969ebad295311d4757e4092d02a`
- plan.json SHA-256: `845d2e17a77f87b20757bf4e3de32860e66591588a15096fb65fbf8bcb3894a8`
- probe 원본은 수정하지 않았으며 commands.json/cases.jsonl/plan.json 전체 해시를 실행 전후 재확인했다.
- raw에 source fingerprint, 환경, driver/원본 실행 script, case 입력/result/오류 stack, power checks, probe module copies/diff, JUnit, 초기 부정확한 비교 receipt를 모두 보존했다. raw는 로컬 보관이며 원격 백업이 아니다. Git에는 본 문서와 JSON만 올린다. Google Drive는 프로젝트 예외에 따라 사용하지 않았다.
- agent_lock: driver PID 59794, owner codex, purpose `v6h1 acceptance replay (SIM time, no models)`, expected 30분. own worker 및 테스트 종료 후 release 완료; 사후 status=null. 다른 프로세스를 종료하지 않았다.
- 전원: 실행 중 저장된 11회 모두 AC Power; 시작 81%, 사후 확인 85%. battery power로 인한 중단 없음.
- 부하 평균(1/5/15분): 시작 [8.16748046875, 14.07177734375, 14.59716796875], 종료 [7.5185546875, 13.5458984375, 14.39599609375]. source_changed=False.
- `tests/test_zone_pair_v6h.py` + `tests/test_zone_pair_registered_source.py`: **88 passed**(15.66 s; 성능 측정 아님). raw `pytest.xml` / `pytest.log`. 정책 동등성을 입증하는 물리 테스트가 아니다.
- 기록 검증: 원본 해시·선택 사례 수·입력 일치·HOST_ERROR 및 누락 파일 상태·pytest 결과·TensorBoard 이벤트 수를 검사했다. `git diff --check`도 통과했다.

원본 코호트의 cases.jsonl 해시:

| 코호트 | 절대 raw 경로 | cases.jsonl SHA-256 |
|---|---|---|
| tS | `/Users/changmin/projects/ugrp/outputs/b-v6h-gain-5bfd95f0-tS` | `d2da3d87899a8f82a2be777eedc8a277809db13597cad19b803adf8c5c0fc07e` |
| tR | `/Users/changmin/projects/ugrp/outputs/b-v6h-gain-5bfd95f0-tR` | `8e1c2d82d76256a117a1fb712310c9b7c0c9044a3d56a1b9edddfecc39f740ea` |
| tX1b | `/Users/changmin/projects/ugrp/outputs/b-v6h-gain-5bfd95f0-tX1b` | `5619275fecf092957d3cb1fb3424cc8bce933bad7a45afd3ad703fbac9c6c324` |
| tX1 | `/Users/changmin/projects/ugrp/outputs/b-v6h-gain-f5d83fdb-tX1` | `c355d1ceff773e5d091703d7f9afea8f37f086dd53135e4a7a8b1b6a258ce4fb` |
| tX0 | `/Users/changmin/projects/ugrp/outputs/b-v6h-gain-5bfd95f0-tX0` | `a34f7be0d6d9c5766de680074baf694ea93b2d83e1295ed3d78f38da2e0dd9b8` |

## TensorBoard와 남은 작업

[native TensorBoard — acceptance 시도와 probe 기준 코호트](http://127.0.0.1:6006/?pinnedCards=%5B%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22evaluation%2Freported_success%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fpass%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fcomparable%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22offline%2Fhost_error%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fwall_s%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fcommands%22%7D%2C%7B%22plugin%22%3A%22scalars%22%2C%22tag%22%3A%22result%2Fmodel_calls%22%7D%5D&smoothing=0&runFilter=%5E0930-%28v6h1-acceptance-host-error%2F%7Cb-v6h-axial-lag%2FALL-%28tS%7CtR%7CtX1b%7CtX1%7CtX0%29%29#timeseries)
- 새 snapshot: `/Users/changmin/projects/ugrp/outputs/tensorboard/0930-v6h1-acceptance-host-error`; 11개 사례 + 2개 집계 = 13개 run, export 오류 0. 실패도 포함했다.
- EventAccumulator로 offline/pass=0, comparable=0, HOST_ERROR 11건, model_calls=0을 다시 읽었다. 기존 native 서버(6006)의 실제 logdir가 공용 outputs/tensorboard이며 scalar-tags API가 새 13개 run을 로딩한 것도 확인했다.
- 기존 탐색 tS/tR/tX1b/tX1/tX0 집계와 분리된 run filter 및 pinned link, HParams 표시 열을 outputs/tensorboard-view.json의 자기 키에만 추가했다. 다른 키·순서·형식을 보존했다. 서버 소유권을 ps로 확인할 수 없어 기존 서버에는 start/stop/설정 변경을 하지 않았다.
- 영상은 renderer 초기화 실패로 생성되지 않았고 등록할 새 비디오 0개다. SIM 시간과 command count는 유효한 원본이 없어 채우지 않았다. model response time은 호출 0건으로 없다.
- **화면 검증 미완료:** CUA에 browser surface가 없으며 Chrome 선택은 cgWindowNotFound로 실패했다. 강 외의 프로필은 사용하지 않았다. pinned 카드의 실제 표시와 HParams 열 적용은 확인하지 못했다.
- 인수 완료를 위해 CGL이 동작하는 허용된 Mac 실행 환경에서 같은 소스 SHA·선택 입력을 새 raw 경로로 재실행해야 한다. 10건 모두 commands.json SHA와 recorded leg 결과가 완전히 같아야 PASS다. 그 전까지 확증 코호트를 시작하는 근거로 쓰지 않는다.
- PR 생성/병합·봉인·main 갱신은 이 작업 범위에 없다. 조정자가 이 브랜치의 기록을 PR #292에 연결한다.
