# 자연 바닥·벽 질감 v1 — 오프라인 자료

`floor_light_textured_v1`, 기본 off. main 기준 `328b4e1d`에서 만든 별도 장면 버전이며 이전 실행과 합산하지 않는다. 사용자 원문/적용법/소비자 #505·#506·#507 및 교사 관문 연결점은 [렌더 프로필 문서](../../docs/render_profiles.md)에 있다. 시뮬레이션·카메라 렌더·원격 접속·모델 호출은 실행하지 않았다.

## 배경과 검증 범위

사용자가 지정한 selfmap `380277b8` 180초 진단의 로컬 `93521-stall-evidence-live.json`을 다시 읽었다. 마지막 기록 `t=133.8`에서 특징 36·매칭 4·inlier 0·`command_only`·rebuild 8, 첫 해당 정지 전이는 약 93 SIM초다. 이는 회수된 중간 증거이며 180초 전체 완료 결과가 아니다. 경로와 SHA는 `summary.json`에 보존한다. 제어기를 수정하거나 진단을 다시 실행하지 않았다.

기존 `floor_light_v1` 조명과 `1d981162` 벽 테이프의 벽 판독/자산 고정 방식을 재사용한다. 새 코드는 재질만 바꾸며 벽 plane을 추가하지 않는다. 고정 seed 20261015, 바닥 3072² PNG 1장, 네 지도에 필요한 서로 다른 벽 box 25종×6면=150장, 합계 151장과 manifest 5,165,851 bytes다. 생성 이미지는 합성 콘크리트/에폭시 마모이며 실물 질감/조도/마찰 측정이 아니다.

## 이미지 측정 결과

| 입력 | ORB 특징 (상한 800) | 멀리 떨어진 유사 descriptor 비율 | 반복 32px 패치 비율 | 고주파 NCC 최대 |
|---|---:|---:|---:|---:|
| 전체 바닥 PNG | 800 | 0/800 (0%) | 0% | 0.00839 |
| 바닥 640×480 원본 crop 4개 | 657, 675, 678, 700 | 개별 JSON 참조 | 개별 JSON 참조 | 개별 JSON 참조 |
| 수정된 벽 150면 | 모두 0 | descriptor 없음 | 개별 JSON 참조 | 최대 0.615 |
| 평탄 회색 512² 대조군 | 0 | 해당 없음 | 99.61% | 0 |
| 합성 32px 바둑판 512² 대조군 | 516 | 516/516 (100%) | 99.22% | 0.985 |

ORB는 `natural_floor_slam.Options.features=800`과 같은 상한, OpenCV 기본 FAST/피라미드다. 원본 전체 및 지정 crop에 적용했으며 실제 카메라/바닥 마스크/원근 투영을 적용한 결과가 아니다. descriptor 반복은 같은 이미지에서 거리 ≥64px인 점 중 Hamming ≤24 이웃이 있는 비율이다. 동일 위치의 여러 피라미드 검출은 제외한다. NCC는 512²로 축소하고 sigma=3 고주파 성분의 x/y 이동 32/64/128/256px 상관 최댓값이다. 이 유한 검사는 모든 반복성/오매칭 부재를 증명하지 않는다.

검토 전 벽은 ORB 0–352였지만 벽띠 검출에 영향을 줬다. 아래 수정으로 대비를 줄인 벽은 150/150면에서 ORB 0이다. 벽 특징 증가를 주장하지 않으며, 바닥 PNG와 crop 특징 수는 그대로다. texture source 자체를 화면 전체로 본 특징 수를 SLAM 성공으로 보고하지 않는다.

[색 범위 표](color-ranges.md)는 현재 코드의 89개 HSV 관련 소스를 탐색한 [목록](color-source-inventory.md), 별도 PR의 빔 끝 띠/상자 손잡이 원문·SHA를 담은 [외부 정의](color_external_sources.json)에 연결된다. 81개 HSV/보수적 상위집합/RGB 조건 모두 바닥 0/9,437,184, 벽 0/39,321,600 픽셀이다. 모든 채널이 같아 S=0이며 V는 바닥 97–184, 수정 벽 82–86이다. 어두운 띠(V≤60), 흰 화물(V≥225)도 원본에서는 피했다. 단순 범위 검사로 형태·주변 대비·그림자·JPEG 경계 누출 검증을 대신하지 않는다. 기존 검출 임계값은 수정하지 않았다.

## PR #511 검토 수정: 비색 인식과 XML 경로

검토 기준 `6a73c3aa`의 원본 자산은 Git에서 별도로 추출했다. 벽 PNG 전체의 내부 40×7 창 35,824,800개를 검사했을 때 `std≤3` 비율은 픽셀 전체 기준 76.44%, 열 strip 평균 기준 82.10%였다. 벽 150면을 정사각형 보간 후 대비 0.04배·평균 84·범위 82–86으로 줄였다. 수정 후 두 방식 모두 35,824,800/35,824,800창이 통과했다(최대 std 1.311/0.981). 바닥 PNG는 바꾸지 않았다. 검출기와 `floor_light_v1` 보정값도 바꾸지 않았다.

`scripts/audit_scene_texture_own_image.py`는 벽 면 3개×거리 0.75/1.5m×조명 0.75/1/1.25배(마지막은 세로 6% 기울기) 18조건을 분석한다. 원본/수정 질감, 기존 checker 근사, 평탄 벽 대조군의 네 팔이다. 기존 probe 카메라 기하로 PNG 평면을 샘플링하고 실제 `detect_boundaries(max_band_std=3)`와 `opencv_wall_observation`을 원본 PNG/품질90 JPEG에 적용했다. 원본 렌즈 왜곡을 거친 영상이 아니어서 observer의 undistort만 항등 변환으로 연결했다. 정답 경계는 채점에만 쓴다.

| 팔 (각 18장·1,728열) | 검출기 정답 열 PNG/JPEG | observer 정답 열 PNG/JPEG | observer 오검출 열 PNG/JPEG | 두 frame gate 통과 |
|---|---:|---:|---:|---:|
| 기존 checker 근사 | 1,728 / 1,605 | 1,728 / 1,605 | 0 / 123 | 각각 18/18 |
| 검토 전 질감 | 89 / 81 | 50 / 48 | 203 / 216 | 각각 18/18 |
| 수정 질감 | 1,728 / 1,728 | 1,728 / 1,728 | 0 / 0 | 각각 18/18 |
| 평탄 벽 대조군 | 1,728 / 1,728 | 1,728 / 1,728 | 0 / 0 | 각각 18/18 |

frame gate는 고정된 `own_image_gates_floor_light_v1.json`의 실제 값/해시로 JPEG를 판정했으며 검정·평탄 회색 음성 대조군은 각각 0/1 통과다. 검출기 정답 열은 올바른 후보가 하나라도 있는 열이고, observer는 실제 단일 후보·채도·경계 대비 규칙을 그대로 쓴다. [감사 요약](own-image-audit.json)과 팔별 frame JSON에 수치·원본 경로·해시를 기록했다. **핀홀 평면·단순 조명 근사이며 실제 카메라/물체/그림자/BRDF/cube 방향/런타임 codec 검증이나 새 프로필 보정은 아니다.** `wall_floor_lorigo`, `wall_floor_ulrich`, `vendor/lu_vp`도 미검증 소비자로 남긴다. GCP 정적 관문에서 기존 프로필 대비 정답/오검출 열·게이트 통과 n/N을 다시 비교하고, 필요하면 질감 전용 분기에서만 임계값을 보정한다.

XML은 `compiler.texturedir="sim/assets/floor_light_textured_v1"`와 파일명만 사용한다. `from_xml_string` 실행은 저장소 루트를 cwd로 사용하고, XML 파일로 내보내면 그 파일의 디렉터리를 기준으로 같은 상대 자산 구조를 함께 배치해야 한다. 기존 `assetdir`/`texturedir` 또는 파일 텍스처가 있는 모호한 장면은 거부한다. 자산은 별도 manifest/PNG 해시로 고정한다. 실제 `build_multi_robot_xml`→`build_zone_xml`의 네 지도에서 on/off 연결, 카메라·물리·페인트 보존, 검토 기준 off/`floor_light_v1` 해시 고정([기준](zone-xml-baseline.json)), 다른 checkout 자산 경로에서 XML 바이트 동일성을 검사한다. 모델 컴파일은 하지 않는다. AGENTS.md는 조건을 포함한 사용자 원문 전체와 조정자 해석·미확인을 분리했다.

## 재현과 검증

기존 `.venv-sim-worker-mac`의 Python 3.12 / OpenCV 5.0.0 / NumPy 2.5.2 / Pillow 12.3.0을 사용했다. 새 환경을 만들지 않았다. 각 JSON은 64 KiB 미만으로 나누었다.

```sh
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  scripts/generate_scene_textures.py --output /tmp/floortex-NEW
PYTHONPATH=. /Users/changmin/projects/ugrp/.venv-sim-worker-mac/bin/python \
  scripts/audit_scene_textures.py --output experiments/2026-10-15-scene-floor-texture/offline-audit.json
```

전체 PNG를 다른 디렉터리에 재생성해 151/151 파일 SHA 일치를 확인했다. PNG·manifest 해시 검증, 미지원 장면 거부, 네 지도 XML의 물리/카메라/물체 불변, 기본 프로필 해시, nearclip 실제 부모 기록, 미승인 대기열, 기존 자연 특징 SLAM 회귀를 검사했다. 실제 모델 컴파일/렌더 검사는 제외하며 GCP에서 검사한다. 최종 시험 수·원본 위치·해시는 `summary.json`에 기록한다.

검토 수정 라운드의 실행 기록은 `review-r1-summary.json`에 별도로 보존한다. 재생성은 PNG 151/151과 manifest까지 152/152 파일 바이트가 일치했다. 이전 `summary.json`은 검토 전 기록이다.

## PR #511 CI 수정: 고정 렌더 자산 보존

`976b4ef2`에서 `tests/test_zone_e2e_manifest.py`를 단독 실행해 P03의 `sim/render_profile.py` 자산 해시 불일치를 재현했다. 해당 파일을 `origin/main` 바이트(SHA-256 `782a531a5a89d23dce2974778e26b7ab1f0b6df8cd60f83df9404079cf7290d5`)로 복원하고 질감 정의·XML 적용·manifest·모델 audit을 `sim/render_profile_textured.py`로 분리했다. `sim/render_profile_selection.for_name`은 질감 이름을 명시한 경우에만 새 모듈을 불러온다. 질감 계획 생성기도 이 선택기를 사용한다. 기존 조합 핀/번들/registry는 갱신하지 않았다.

질감 프로필 해시와 대표 XML 바이트는 분리 전과 동일하다. 기존 `scripts/run_pair_stage_probes.py`도 소스 고정 대상이므로 그대로 보존한다. 이 CLI가 질감을 바로 지원한다는 앞선 안내는 정정했으며, 새 소비자는 선택기·실제 audit을 연결하고 새 소스/번들을 고정해야 한다. CI 수정의 원본 로그·해시·검증 범위는 `ci-fix-summary.json`에 별도로 기록한다. 이전 측정 기록은 덮어쓰지 않는다.

## GCP 진단 계획 (미승인·미실행)

`make_scene_texture_plan.py --source-sha <확정 40자리 SHA> --output <새 파일>`이 모든 `approved`·`ready*`·`execute`·`enabled`를 false로 작성한다. 로컬 대기열 이름은 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/vm3-queue/20261015-floortex-<SHA8>.json`이다. 자동 제출 명령/감시는 없다.

1. 소비자 PR가 프로필 선택과 실제 audit 연결을 끝내고 새 소스/번들을 고정한다. GCP 프로젝트 `ugrp-act-train-1014`만 사용하고 같은 머신 종류에서 두 팔을 잰다. 예산 정지, VM 8h 상한/20분 유휴 정지, 512 MiB 자료 예산과 여유 공간을 확인한다.
2. 네 지도(두 문/복도/H1/H2) 각각 고정 6시점에서 기존 프로필·새 프로필의 자기 카메라 640×480 총 48장을 얻는다. 물리 step0, 모델 호출0, 실제 카메라/FOV/로봇/물체/색 유지. setup 자세만 사용하고 위치 정답을 제어기에 주지 않는다. PNG·런타임 JPEG/sha, 컴파일된 물리 배열 동등성, 면 방향/줄무늬/이음매/축척을 확인한다.
3. 정답 바닥/벽 마스크는 평가에만 사용해 색 오검출 픽셀·연결 성분 n/N, 원래 물체/띠/손잡이/페인트/로봇 검출 유지 여부를 기준 프로필과 비교한다. `detect_boundaries`의 벽띠 std≤3 수용 n/N·정답/오검출 열, `opencv_wall_observation`의 정답/오검출 열, 고정 `own_image_gates`의 두 frame gate 통과 n/N과 dark/spread/std를 PNG·실제 런타임 JPEG에서 각각 기록한다. `wall_floor_lorigo`, `wall_floor_ulrich`, `vendor/lu_vp`는 별도로 검증한다. ORB 전체/실제 floor mask 통과 수를 모두 기록한다. 새 색 오검출 성분이나 기존 대상/정답 벽 열 손실·새 오검출 벽 열/프레임 허위 수용, 반복·매핑 결함이면 중단한다. 필요한 보정은 질감 전용 분기와 새 보정 기록으로만 허용한다.
4. 정적 관문 뒤 #506의 동일 새 코드·새로 예약한 같은 seed로 프로필만 바꾼 첫30 SIM초 비교. features/matches/inliers, visual/command_only 비율, rebuild·map_updated·stop_reason·wall/SIM을 비교한다. 속도 중앙 >3.5는 경고, >6 또는 미완료/HOST_ERROR는 차단. 결함 확인 시 해당 실행 즉시 정지한다.
5. 첫30은 원래 약93초 뒤 정지의 해소나 전체 지도 완성을 입증하지 않는다. 장기 진단·AMCL·단독 운반·교사 ≥40회 관문은 별도 승인/예산/소스 고정 뒤 새 장면에서 다시 잰다. 실패/HOST_ERROR도 원본과 함께 기록하며 이전 결과와 합치지 않는다.

참고 자료는 [렌더 프로필 문서](../../docs/render_profiles.md#참고-자료-2026-10-15-확인)에 열람 범위와 함께 정리했다.
