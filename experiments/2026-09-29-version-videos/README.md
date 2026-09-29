# 버전별 대표 영상: 짝 운반 stage probe 재생성 도구와 첫 백필 (2026-09-29, Claude)

**stage probe, not E2E success.** 여기의 영상은 PR #260 하네스로 단계 하나만 돌린 저장된 case를 다시 그린 것이다. 물리·시뮬레이션은 이 작업에서 돌리지 않았고(agent_lock 불필요), 모델 호출 0회다. 영상은 제출·보고용 후보이며 연구 결과가 아니다. 색인과 선택 규칙은 [docs/version_videos.md](../../docs/version_videos.md)에 있다.

Refs #221. 실험 ID `2026-09-29-version-videos`. 도구 `scripts/render_pair_probe_video.py`, 테스트 `tests/test_render_pair_probe_video.py`, 재생성 `build_videos.sh`.

## 영상이 무엇이고 무엇이 아닌가

- **위에서 본 그림은 정답 위치를 그린 것이다(평가용, 로봇 입력 아님).** 공용 top 카메라 프레임은 probe가 저장하지 않으므로 카메라 영상이 아니다. 빔(0.60 m)과 로봇 r1/r2의 정답 위치를 `eval_only/trace.jsonl`(20 Hz)에서 그렸다. 영상 안 제목과 아래 자막에 같은 말을 적었다. 로봇 몸체 크기는 도식이다.
- **아래 곡선은 로봇이 스스로 추정한 yaw 불확실도 σ다.** `--pf-track` 실행은 `trace.jsonl`의 `pf.<로봇>.std_yaw_rad`(약 0.25 s 간격)를 쓴다. pf가 없는 행은 건너뛴다(보간하지 않는다). pf가 전혀 없는 옛 실행(v6c, v6d)은 `robots.json`의 로봇 보고 `report.std_yaw_rad`(카메라 프레임 5 Hz)로 대신하고 영상 안에 σ 출처를 적었다. 두 값이 같다는 것은 v6e yaw 실행 한 case에서 확인했다(프레임 4개에서 보고 σ와 가장 가까운 PF 행의 σ가 반올림 자릿수까지 일치).
- **게이트 선**은 `harness.zone_own_guards.GATE_LOADED.high_yaw_rad`(3° = 52.4 mrad, 체류 0.6 s)를 import해서 그린다. 도구 안에 숫자를 복사하지 않았고 테스트가 이를 확인한다. 정렬(align) 영상은 종료 원인이 이 σ 게이트가 아니므로 `--gate none`으로 선을 뺐다.
- **손목 카메라(`--wrist`)** 는 각 로봇의 저장 프레임(`frames/<로봇>/NNNNN.jpg`)이다. 프레임 번호와 sim 시간의 대응은 `robots.json`의 `frames[].frame`/`t`로 정확히 맞춘다. 이 기록이 없으면 첫 trace 시각 + 번호 × 0.2 s로 근사하고 영상에 `*`와 문구로 표시한다(이번 영상은 모두 정확 대응). 손목 영상은 종전에 만든 "손목 + r3" 영상과 다르다. 그 영상의 r3는 대기 중인 세 번째 로봇의 카메라였고 top 시점이 아니었으므로 쓰지 않았다.
- 판정 글자(예 `POSE_UNCERTAIN (r1 @ 28.6 s)`)는 각 case `result.json`의 `row`에서 읽어 실행이 끝나는 프레임에 표시한다.
- 재생 속도는 `dt × fps`(기본 0.25 s × 8 fps = 2배)이며 자막에 적혀 있다.

## 만든 영상

파일은 [videos/](videos/)에 있다(모두 1280×720 H.264, 파일당 1 MiB 미만, 합계 약 0.3 MiB).

| 영상 | 내용 | 크기 | sha256 |
|---|---|---:|---|
| `carry_L1_latm-opp_s911_v6e-base_vs_v6e-yaw_topdown.mp4` | 운반 leg 1, lat−/opp, seed 911: b-v6e-base(실패) vs b-v6e yaw 수정(통과) | 91,808 | `d7dc208fd9f7e24da71118a3bbad948bfdf0b86be3ab2b972e7858996420e7ad` |
| `carry_L1_latm-opp_s911_v6e-base_vs_v6e-yaw_topdown_wrist.mp4` | 위 영상 + 로봇 4대분 손목 카메라 | 117,085 | `f94a8563ed0c2037a13b6ea4792ab9cfcc535b2b3416040fa918c1f6842e905d` |
| `carry_L1_nominal_s911_v6c_topdown.mp4` | 운반 leg 1, nominal, seed 911: b-v6c(실패) | 33,061 | `56063b7e28a5c02f6163df035d229bef13155742cdb6f624a9d60a3f0f4ffcc0` |
| `align_yawp-opp_s911_v6c_vs_v6d_topdown.mp4` | 정렬 yaw+/opp, seed 911: b-v6c(실패) vs b-v6d(통과) | 66,533 | `efc276c57eb6007ae646cd8094cd90264608ee866bf44df7678fa920395d0ab2` |

같은 명령을 두 번 돌려 sha256이 같았다(ffmpeg 8.1.1, matplotlib 3.11.2, numpy 2.4.4, Pillow 12.2.0, Python 3.13.5, macOS). 다른 도구 버전에서는 바이트가 다를 수 있다.

## 영상에서 보이는 사실

### b-v6e-base vs b-v6e yaw 수정 (`carry_L1_latm-opp_s911…`)

- 이전(b-v6e-base) 실행은 σ가 게이트 52.4 mrad에 닿는 시점(약 28.6–29 s)에 끝난다. `result.json`의 첫 실패는 r1 28.6 s `POSE_UNCERTAIN`, 원인 `SELF_POSE_UNCERTAIN`(yaw), σ_yaw 최댓값은 r1 52.6·r2 51.9 mrad, trace는 29.1 s까지다.
- yaw 수정 실행은 leg 1을 끝까지 가서 31.3 s에 두 로봇이 `probe_exit_carry`로 나간다(PASS). 그때 σ는 r1 약 40.5, r2 약 39.8 mrad로, 게이트까지 약 12 mrad가 남는다.
- 두 곡선은 약 8 s까지 같고 그 뒤 벌어진다. 수정은 **σ가 늘어나는 속도를 늦춘다. σ 증가를 없애지는 않는다**(수정 곡선도 31 s까지 계속 오른다). 이 속도라면 더 긴 leg에서는 게이트에 닿을 수 있다(영상이 보인 것은 이 leg까지다).
- **한 케이스다.** L1 nominal에 가까운 셀 하나(seed 911, lat−/opp)이고 성공의 일반화가 아니다. 같은 cal 실행의 L1 다른 4건(nominal 3 seed, yaw+/same)도 이전 0/5 실패(σ_yaw 최댓값 51.0–52.6 mrad), 수정 5/5 통과이고 L2도 5건씩 같다(같은 두 cal 실행의 cases.jsonl, 읽기만 함). 그러나 PF seed는 독립 반복이 아니며 이 40건 cal은 **아직 진행 중**이라 전체 판정은 나오지 않았다.
- 영상에 안 보이는 `result.json` 값: 종료 시점 추정-정답 yaw 차는 이전 r1 −14·r2 −121 mrad, 수정 r1 −62·r2 −100 mrad다. σ가 작다고 추정이 정확한 것은 아니다. PF 정직성(NEES) 판정은 cal 전체 결과를 따른다.

### b-v6c 운반 (`carry_L1_nominal_s911_v6c…`)

- b-v6c는 운반 명령을 낸 6.1 s 뒤 2.7 s 만인 8.8 s(r2 `POSE_UNCERTAIN`, 첫 실패)에 σ가 게이트 선에 닿는다. 원인 `SELF_POSE_UNCERTAIN`, σ_yaw 최댓값 r1 52.0·r2 52.4 mrad(`result.json`). σ는 명령을 내기 전(약 3.7 s, teacher가 자세를 만드는 구간)부터 오르기 시작한다. 이 leg의 33건이 모두 같은 원인이라는 것은 v6c-carry 기록의 결과이며 이 영상 한 건이 보이는 것은 아니다.

### b-v6c vs b-v6d 정렬 (`align_yawp-opp_s911…`)

- v6d는 정렬 단계만 바꾼 정책이다. 이 영상은 **정렬 단계**이며 운반 영상이 아니다(v6d의 운반 raw는 없다).
- 같은 셀(yaw+/opp, seed 911)에서 b-v6c는 20.5 s 뒤(stage 시간) `ALIGN_RELOOK_NO_FIX`로 끝나고 b-v6d는 36.1 s에 통과한다. 두 σ 곡선(로봇 보고)은 모두 게이트보다 한참 아래(최대 약 21 mrad)라 **σ가 원인이 아니다.** 위에서 본 그림에서는 두 실행의 차이가 거의 보이지 않는다. 위치 그림만으로는 차이가 잘 드러나지 않아 제출 영상으로는 약하다.

## 원자료와 해시

경로는 기본 체크아웃 `/Users/changmin/projects/ugrp/outputs/`(Git 밖, 로컬 보관, 원격 백업 아님) 아래이며 `<run>/cases/<case>/`이다.

| 영상에 쓴 것 | run · case | 소스 SHA(manifest) · probe · 실행 상태 | result.json sha256 | trace.jsonl sha256 | robots.json sha256 |
|---|---|---|---|---|---|
| b-v6e-base | `pair-stage-probes-d08818ef-cal2` · `carry_b-v6e_teacher_lat-_opp_s911_pE2E_L1_Vcal` | `d08818ef` (source_dirty true) · 0.6.0 · completed | `45a03092b7e8914eb049736b114fb8c3f0f2926d2cf4fbf1c46c1c49f11c32cc` | `76070c990336a551de83cef192f039eddec468b854719b69ab57611ef80a7b35` | `4b766c4320782ba34c607102f41a75040e2d2d3266dc3074216c97e368c99d06` |
| b-v6e yaw 수정 | `pair-stage-probes-f2186414-yawcal` · 같은 case 이름 | `f2186414` (source_dirty true) · 0.7.0 · **manifest state `running`**(다른 에이전트가 실행 중, 읽기만 했다. 이 case의 result.json은 완결) | `483ad3f03357363233ab1df5bd9864c924f06aa079eb2c39ba82c2817cfd7f39` | `797b348d88896e7c53a65dd4b7e264745b818ed024571ce29cf45f994eb1aca7` | `f403ff9d0ca3c06edfff20b40d82c79036c6f93b5672acf1bcc2197c977dc799` |
| b-v6c 운반 | `pair-stage-probes-b604499d-carryL1367` · `carry_b-v6c_teacher_nominal_s911_pE2E_L1` | `b604499d` (clean) · 0.4.1 · completed | `c01a5da5a242cb484225c3402aa9677a6c23c973e2a33ffce68ad4c8c989e32b` | `c5f413834f49ff27f4a555996423a74a94d33ecaa8bd57d26c7fdbd4c1de6874` | `a80b8ccda500ff978c530374fcf4911ee2a27ce1120a50da0438f6ad2ec512a6` |
| b-v6c 정렬 | `pair-stage-probes-b5234b7a-v6c-align` · `align_b-v6c_teacher_yaw+_opp_s911_pE2E` | `b5234b7a` (clean) · 0.3.0 · completed | `de3424811abc2e166609626a568309342810def0baa47d49398305a4327e481d` | `35d76e9515c029892ea96f884ce8def0dedfc1a87bf7499873ab0618b25adf02` | `eddf3e3ccdba82452d7b9f8c8ea01405f107727277fb40a33633f2b6b316085f` |
| b-v6d 정렬 | `pair-stage-probes-052e3eba-v6d-venv-align-0` · `align_b-v6d_teacher_yaw+_opp_s911_pE2E` | `052e3eba` (source_dirty true, 사유는 v6d README) · 0.4.0 · completed | `28151fbbe5db1528a4b2052bff5dd0a0a881bfd539636831df02e14be084a0a9` | `7031855a46af4ec585ecb3063c58a2990e7da583b12f0fa1bf3af053b1d5d139` | `06e1e72a61bafcac008114666ca6621a83d53588ec336405c0d7a9223013ad04` |

- 위 두 v6e 행의 raw `pair_policy`는 둘 다 문자열 `b-v6e`이지만 뜻이 다르다. 이전 실행의 `b-v6e`는 지금 `b-v6e-base`이고, yaw 수정 실행의 `b-v6e`는 새 정책이다(`claude/pair-v6e-carry` 브랜치 README의 이름 변경 주의). 그 브랜치는 아직 main에 없어 이 PR은 그 README를 고치지 않았다.
- v6c·v6d raw의 `execution_bundle_id_on_main`은 `zone-pair-v76-fixclock-grasp-entry`(v76), 두 v6e 실행은 `zone-pair-v80-align-widehue-finemotion`(v80)이다. 실행 번들 등록은 별개의 절차다.

## 재생성

```
OUT=/Users/changmin/projects/ugrp/outputs bash experiments/2026-09-29-version-videos/build_videos.sh [출력 폴더]
```

한 case만 그릴 때(matplotlib·ffmpeg 필요, 저장소 루트에서):

```
python3 scripts/render_pair_probe_video.py --case <case 폴더> --label "이름" [--case <두 번째> --label "이름"] \
  --output <out.mp4> [--wrist] [--gate loaded|unloaded|none] [--fps 8] [--dt 0.25]
```

## 한계

- **정답 위치 그림이다.** top 카메라 영상이 아니다. 실제 카메라로 본 장면이 필요하면 별도 렌더(평가 전용 top 프로필)가 필요하며 이 도구가 하지 않는다.
- σ 곡선은 PF가 추정한 불확실도이지 실제 오차가 아니다.
- yaw 수정 실행이 진행 중이라 그 raw는 나중에 더 채워질 수 있다. 위 해시는 이 case 파일의 해시이며 실행 폴더 전체의 봉인이 아니다.
- 이 PR이 실행한 것: 영상 렌더와 관련 테스트(`tests/test_render_pair_probe_video.py` 11건)뿐이다. 전체 CI는 돌리지 않았다.

## 참고 자료

- 저장소 내부: `harness/zone_own_guards.py`(`GATE_LOADED`), `harness/ultrasonic_carry.py`(`BEAM_LENGTH_M`), `harness/pair_stage_probe.py`·`scripts/run_pair_stage_probes.py`(`--pf-track`, case 디렉터리 구조), `experiments/2026-09-29-pair-v6c-carry/README.md`, `experiments/2026-09-29-pair-v6d-align/README.md`.
- 외부: matplotlib(Agg 캔버스에서 RGBA를 읽는 `buffer_rgba`)와 ffmpeg 표준 입력 rawvideo 파이프. 새로운 방법을 조사해 채택한 것은 없다.
