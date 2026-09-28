# PR #240 표식 무관 자세 계약 — 2026-09-28

구현 기준 HEAD `f510901719afc419863344385514304f3d3a905a` 위의 미커밋 변경이다.
물리 step·실제 모델 추론·Git 커밋은 하지 않는다. `tags_temporary` 실행은 조작 기능을 점검하는
임시 비계이며 연구 결과가 아니다. 표식 0개 공동 운반은 vision 제공자로 별도 검증해야 한다.

근거는 [이슈 #221 코디네이터 수정](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/issues/221#issuecomment-5857460817)이다.
dev11·dev12 보류, 1e-4초 시간 비교 수정 유지, 임계값 불변을 따른다.
저장소 ID `1359726870`은 새 주소 `cmkang131/UGRP-Multi-Robot-Collaboration-Project`와 일치했다.
샌드박스가 공용 `.git/FETCH_HEAD` 쓰기와 CLI 네트워크를 거부했다. 커넥터로 main과 열린 PR
#239–#245를 읽고 모든 열린 head SHA가 기존 origin ref와 일치하는 것을 확인했다.
마지막 확인에서 갱신된 #245의 `0acdaf0d543e6535d61ff80f2c49d031beee04d7`도
번들 v66/dispatch v63을 사용하여 v67과 충돌하지 않았다.
origin URL·기본 체크아웃·브랜치·Git 이력은 변경하지 않았다.

## 공통 계약

- `PoseReport.last_fix_t`: 실제 수용한 자기 관측의 **원시 촬영 SIM 시각**. 별도 반올림된
  `t_est - age`로 재구성하지 않는다. prior, 예측, 명령, 관측 전달 시각은 fix가 아니다.
- `fix_age_s`: 제공자 보고 시각 기준 관측 나이. 기존 임시 제공자의 1 ms 반올림을 유지한다.
  sweep 시작/미래/6초 공백은 원시 `last_fix_t`로 비교한다.
- `fix_source`: `tags_temporary`, `vision_zero_tag_v1` 등의 출처. 실행기는 출처별 분기 없이
  같은 판정을 쓴다. `std_xy_m/std_yaw_rad`, 초기화 상태, 관측 품질과 기존 freshness 조건을 함께 전달한다.
- `observation_quality`: 수용 여부·관측 특징 수 또는 vision informative columns·PF 진단.
  진단값이며 새 신뢰도 임계값이나 정확도 증명이 아니다. 실제 수용된 fix에도 σ gate를 그대로 적용한다.
- `expected_observability(pose, pan, static_map) -> float`: 안전한 LOOK_P20 pan 후보의 제공자별
  비음수 점수. 자기 추정·고정 카메라·정적 지도만 쓴다. 양의 점수도 관측/위치 확정을 뜻하지 않는다.
- `begin_relocalization(now, servo)`: 제공자 소유의 재관측 준비. 실행기가 필터 클래스를 선택하거나
  vision을 임시 필터로 바꾸지 않는다. delayed adapter는 기존 미전달 입력을 폐기하고 새 입력 지연을 유지한다.

제어의 tag 명칭은 fix 명칭으로 바뀐다. 로그의 reason/check/key 이름 변경은 의도된 스키마 변경이다.
임시 제공자의 기존 `since_tag_s`, localizer의 `last_tag_t`는 동결 소비자 호환을 위해 제공자 내부에만
남긴다. 실행기는 이 별칭이나 `last_valid_obs.tag_ids`를 판단에 쓰지 않는다.

## 제공자와 제어 경계

| 경로 | 이번 변경 / 보존 범위 |
|---|---|
| `owncam_pose_source`, `owncam_localizer` | 수용 raw 시각·기존 age를 새 필드로 발행. 기존 pan 투영 면적 산식·8 px 조건·정렬 tie-break·PF reset RNG 순서를 보존 |
| `vision_pose_source` | #237 worker/PF의 `last_scan_t`를 raw fix로 연결. setup prior나 prediction은 fix를 갱신하지 않음. worker 실패는 미초기화·fix 없음 |
| vision 예상 관측성 | 동결 VIS3 정적 wall/door ray casting + 보정 camera column model로 화면 안 바닥/상단 경계 수를 계산. 벽 모서리·문틈·정적 가림을 기존 모델로 처리. 학습된 정보량 점수나 실환경 검증은 아님 |
| vision 재관측 | 현재 posterior·σ를 유지하며 이전 fix receipt만 무효화. 움직인 로봇을 episode-start dock prior로 재설정하지 않음 |
| `zone_pair_align/grasp/guards/admission` | fresh fix·age·σ와 제공자 점수만 사용. raw 시각, strict align 경계, 파지 inclusive 경계, 여유/타임아웃 불변 |
| `zone_own_driver/executor/status` | 진행 감시·look 완료·상태 age를 공통 필드로 전환. frozen loop의 tag trigger는 같은 3초 fix trigger로 override |
| `zone_study_pose_delay` | neutral score/reset forwarding. raw capture는 지연된 제공자에서 나오며 전달 시각으로 바꾸지 않음 |
| `zone_own_team_host` | 정적 Scene 생성/검증을 `sim/zone_own_scene_provider.py`로 이동. Scene 구성·물리는 동일 |
| 동결 M2/loop | 원본 바이트 유지. 활성 경로의 `_needs_look`, `_look_step`, `_event`, `_relocalize`, `observe`를 공통 계약으로 override. 동결 태그 판정 후크가 활성화되지 않는지 검사 |

정적 검사 `tests/test_pose_provider_boundary.py`는 **모든** `harness/zone_pair*.py`,
`harness/zone_own*.py`, `harness/owncam_time.py`의 식별자·속성·문자열 키·import·keyword를 검사한다.
`stage` 같은 단어는 제외하지만 `last_tag_t`, `since_tag_s`, `tag_gap`, `TagDetector`, 동적 키 접근은 잡는다.
허용 목록은 `tests/fixtures/pose_provider_v5c/allowlist.json`의 제공자·평가·SHA 고정 과거 경로뿐이다.
과거 경로를 허용하는 것과 활성 제어가 그 판정을 실행하는 것은 구분하여 MRO 후크를 검사한다.
M1/M2 과거 실험 소스, 평가/진단, 기존 JPEG/manifest/사전등록은 수정하지 않는다.

## 버전과 사전등록

main 및 열린 PR head 전체에서 `RUNNABLE_ID`와 `EXECUTION_BUNDLE_ID`를 확인했다.
RGB dispatch 최대 v63, 공동 연구 번들 최대 v66(#245)이므로 새 번들은
`zone-study-integration-v67-landmark-agnostic`이다. pair executor `zone_pair_executor_v7_dev`,
grasp `zone_pair_grasp_relook_v3`, pair dev workflow `0.5.0`, integration workflow `2.1.0`이다.
STATUS v5는 그대로 유지한다. v65의 정확한 source 바이트는 테스트 fixture와 기존 Git HEAD에 보존한다.

[prereg_v5d.json](prereg_v5d.json)은 미실행 v5c의 dev11/907·dev12/908을 재등록한다.
v5c 원본 SHA를 `supersedes`에 묶고 최신 제공자/실행기/driver/delay/scene source hash를 기록한다.
criteria, stage_rules, planned_setdown, limits, timing, safety_coverage, environment, inputs, runs는 v5c와 같다.
`cargo_noslip_v1`, weld OFF, fix 5 cm/3°, loaded HIGH 7 cm, clearance 35 mm,
relook 6초·.055 m·2.5° 및 예산은 바뀌지 않는다. `execution_source_sha=null`, 물리 성공은 미검증이다.
코디네이터의 실행 보류에 따라 v5d의 `--execute`는 prepare-only 오류로 거절된다.
새 소스 리뷰·고정과 실행 보류 해제는 후속 사항이다.

## 검증과 한계

최종 회귀·prepare 영수증과 재현 명령은 [landmark_v5d_validation.json](landmark_v5d_validation.json)에 기록했다.

- 비물리 회귀 **893 passed + 104 subtests**, 122.33초. 물리 step이 필요한 기존 테스트 2개는
  제외했다. 초기 검증에서는 해당 호출이 guard에 걸려 실제 step 전에 차단되었다.
- 최종 guard의 물리 step 시도·실제 vision worker 시도·네트워크 시도는 모두 0이다.
  `OMP_NUM_THREADS=1`, `--basetemp=./.pytest_tmp`로 실행했고 임시 디렉터리를 삭제했다.
- [저장 입력 재생](landmark_v5d_replay.json)은 dev09/10 판정 **10/10**, pan 후보 점수·순서
  **70/70**이 이전 소스와 정확히 일치했다. 기존 고σ 거절 1건도 그대로다.
- 실행기 26개 파일의 정적 검사에서 직접 표식 참조는 0개다. 기존 사전등록 8개는 HEAD와 바이트가 같다.
- dev11·dev12 prepare **2/2**가 `prepared_not_executed`를 반환했다. 영수증은
  [dev11](landmark_v5d_prepare/dev11_manifest.json), [dev12](landmark_v5d_prepare/dev12_manifest.json)에
  보존했다. `applied`/`physical_success`는 null이고 모델 호출은 0이다.
- 새 prereg SHA-256은 `93ff696a2b73100c9307824bed12c6a4a1c65665f4573dbf1783f522cd589cd0`,
  grasp 계약 SHA-256은 `1c2f9335584432485927b16bb4269b66189863add1a4cc32ba9cbf876f209c79`다.

변경 전 핵심 회귀는 184 passed였다. dev09/10 재생은 저장된 자기 입력/판단에 대한 조건부 재생이며
새 물리 실행의 결과·성공률이 아니다. 태그 임시 제공자의 판단/후보 점수가 같아도 vision의 완주·정확도는
증명하지 않는다. 이번 작업은 코드/계약 회귀뿐이므로 새 물리·학습 결과나 TensorBoard 실험 snapshot은 없다.
기존 raw·TensorBoard snapshot은 그대로 보존한다. UGRP의 예외에 따라 Google Drive를 사용하지 않는다.
