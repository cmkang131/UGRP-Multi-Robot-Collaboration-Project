# scenetex2 — 벽·바닥 자연 질감 v2

**최종 판정: NOT_READY.** 기본 off 새 장면 `walls_floor_textured_v2`를 구현하고 gcp2에서 네 지도264/264 정적 프레임을 측정했다. 물리·카메라 동일성12/12와 원본 무결성은 확인했지만, 운반 중 벽이 보이지 않고 주행 특징·JPEG 검출 호환성도 충분하지 않아 연구 실행에 채택하지 않는다. [요약](summary.json), [누적 관문표](rejection-table.json), [미실행 대기열/완료 기록](gcp2-static-request.json).

## 사용자 원문과 변경 범위

2026-10-15: “벽에도 넣고, 벽 / 바닥 색 다르게 해. 쉽게 구분할 수 있도록. 그렇게 시뮬 바꾼 뒤에 그 상황에 효율적일 수 있는 알고리즘으로 다시 설계 ㄱ(첨부터 다시는 말고, 이거에 맞는 방식으로 하면 좋을듯)”, “일단, 시뮬 환경 먼저 세팅하고 / 그 환경에 맞춰서 다 병렬처리로 진행하면 좋을듯”. 이전 같은 날: “특징점 부족하면, 맵에 머 질감같은 거 넣어도 됨 … 현실은 그렇게 미끄럽지 않으니까”.

푸른 저채도 벽과 밝고 따뜻한 회색 바닥에 독립적인 얼룩·마모·입자를 넣었다. 반복 타일·인공 마커·AprilTag는 없다. 바닥3072² PNG1장, 벽1024² cube면150장이다. 마찰·충돌·조명·카메라/FOV·로봇·화물·색 표식을 바꾸지 않는다. 물리/카메라 컴파일 배열도 두 기준 프로필과 비교했다. 교사·학생·지도 실행기는 자동 변경하지 않는다.

최종 후보 E 소스는 `1e9594a9fececf1c5fa4387ed7ac9f08a8459629`이다. 자산 manifest SHA256은 `9afa87ec4a04eb230f284b031e4bb57d0ca8ff1a2c6c967b29a9b7da3c3ee396`, 프로필은 `edf3a92a41422a10151b9cb95ec7925998f6790485e28b1920d03ce4576cd9a8`이다. 기존 v1·B/C/D/E·다른 호스트 결과는 합산하지 않는다. 생성기 seed는2026101502, 출처·전체 PNG SHA는 자산 manifest에 있다.

## PNG 오프라인 측정

| 항목 | 최종 E |
|---|---|
| 벽 HSV | H108–114, S8–10, V98–134 |
| 바닥 HSV | H15–18, S8–10, V146–180 |
| 벽 ORB 최소/중앙/최대 | 0/0/483, 양수47/150면 |
| 바닥640×480 ORB | 793/767/772/793 |
| 먼 유사 descriptor | 유효47면 중앙0·최대2.51%; 나머지103면 descriptor 없음 |
| byte 동일32×32 패치 | 벽150면·바닥 모두0 |
| highpass NCC 최대 | 0.8551; 정사각 cube의 비율 영향도 있어 반복 없음의 증거로 쓰지 않음 |
| 벽–바닥 분리 | V간격12, Lab L구간103–139 / 153–185(OpenCV uint8) |
| 고정/상위집합 대상 색 범위 | 108개, 바닥9,437,184·벽157,286,400 픽셀 침범0 |

[전체 측정](png-audit-e/offline-audit.json), [HSV/RGB/PIL 전체 표](png-audit-e/color-ranges.md), [색 소스 전수 탐색](png-audit-e/color-source-inventory.md), [직접 비교·문맥 조건·48소스 SHA](color_external_sources.json)를 함께 읽는다. 기존81개 목록에 누락된 흰 표식·직접 비교·동적 dictionary 범위를 보충했다. 원거리 유사는 기존 정의인 거리≥64px·Hamming≤24, ORB상한800을 유지했다. 새 특징 개수·각도·성공 수용 기준은 넣지 않았다.

포괄 페인트 S≥20, 상대 검정의 상한 V=.38×255=96.9, 흰 표식 V>180 사이에서 저작 색을 골랐다. 실제 조명 허용 오차로 이 구간을 확대하지 않는다. 문맥/지지 마스크는 색 후보와 다르므로 전체 침범0을 주장하지 않는다. 실제 화면의 PNG/JPEG는 그림자·알파·보간·압축 뒤 범위 침범이 있으며 [상위 분포](camera-e-colour-overlap-top10.json)에 보존했다. 겹치는 범위의 픽셀 합은 고유 픽셀 수나 최종 오검출 수가 아니다.

## gcp2 실제 자기 카메라 측정

기존 `floor_light_v1`, `floor_light_textured_v1`, v2를 네 지도·벽을 보는0.75/1.5m·r1/r2·주행/HIGH/빔+상대 가림으로 비교했다. 상자4색·빔 끝2색·구역A/B/C 양성 시점도 추가했다. 실제 v3 카메라·fisheye·nearclip을 유지했다. 구역 C는 서쪽 시점이 divider에 가려 남쪽1.5m 시점으로 보완했다. 청록/파랑 끝은 이 checkout에 교사 토글이 없어 pinned 원본 RGBA를 기존 band geom에 평가 setup으로 입혔다. 교사 소비자 통합을 증명하지 않는다.

| 최종 E v2 | PNG | JPEG90 |
|---|---|---|
| 전체 프레임 | 88 | 88 |
| 벽 ORB 최소/중앙/최대 | 0/1/126 | 0/1.5/136 |
| 바닥 ORB 최소/중앙/최대 | 0/8/34 | 0/10/33 |
| 전체 벽 관측 funnel | 88→60가시→48ORB양수→11내부support | 88→60가시→60ORB양수→11내부support |
| 주행16 벽 내부support 양수 | 3/16 | 3/16 |
| 운반 가림16 벽 가시/특징 | 0/16·0 | 0/16·0 |
| 벽/바닥 분할 micro IoU, 전체 | .8659/.8639 | .8556/.8608 |
| 벽/바닥 분할 micro IoU, 주행 | .9495/.7353 | .9409/.7406 |
| 상자 종류별 개수 일치, 기존 밝은 바닥 대비 | 88/88 | 76/88 |
| 상자 종류별 개수 일치, 이전 질감 대비 | 88/88 | 82/88 |

ORB 중심이 벽에 있어도 descriptor가 물체·경계에 걸칠 수 있다. 회전된 descriptor 사각형을 감싸는 반지름 `KeyPoint.size×sqrt(2)/2`가 벽 mask 안에 온전히 들어갈 때만 내부support로 센다. 이 양수 여부는 관측 존재의 진단이며 충분한 추정 품질의 관문이 아니다.

JPEG의 구체 반례는 `zone_wide_two_doors_final_v3/view0/box_palette/r1`: 이전 질감은 cyan/red/green/yellow 각1개, v2는 red를 놓쳐3색이다. H1/H2에서는 반대로 red가 늘어나는 차이도 있어 모든 변화가 검출 손실인 것은 아니다. full dictionary에는 수치·debug가 포함되므로 [의미적 개수 비교](camera-e-semantic-counts-0.json)와 구분했다. 원본 및 두 기준별 전체 표는 GCP compat 디렉터리에 있다.

상자4색·끝2색은 각각6/8시점, 구역A/B/C는6/8·5/8·4/8에서 실제 보였다. 미노출은 미검증이다. PNG의 청록/파랑 띠 지원 픽셀은 두 기준과 동일했다. 구역 범위 지원은 기록했지만 완전한 구역 경계 검출기나 컬러 끝 교사 경로를 검증한 것은 아니다. 검정 띠용 legacy beam 검출은 별도 성분 비교다.

[프로필 전용 후보 설정](../../configs/calibration/scene_tex2_camera_candidate.json)은 색 검출에 lossless 원본을 택할 근거와 미승인 벽 설정을 기록한다. `harness.scene_tex2_perception`의 분산 상한은 PNG 휘도·B−R의 범위²/4로 유도했고 벽→바닥 명목 구간 전이를 요구한다. 기존 std≤3·전역 검출기·보정값을 수정하지 않았다. E 주행16프레임에서 PNG/JPEG 각각 컬럼 후보4개만 남았고 v3 위치 정확도는 미검증이므로 연결하지 않는다.

## 직접 본 증거와 검증 경계

GCP ffmpeg으로 만든 [주행/가림24장](review/camera-montage.jpg), [네 지도·두 거리 주행24장](review/drive-all-views.jpg), [상자·끝 띠·구역15장](review/colour-montage.jpg)을 파일로 직접 확인했다. 이전 방사형/가로 늘어짐이 사라졌지만 넓은 벽은 낮은 대비 얼룩이 많고, H2의 두 번째 주행 시점에서만 r1 내부 특징29개가 보였다. HIGH 가림은 빔이 중앙을 채워 벽 자체가 없었다. C 남쪽 시점에서는 원래 보라 구역이 보였다. [명령·원본 SHA](review/SHA256SUMS.json)를 보존한다.

모든 프레임의 SIM시간0, `mj_forward`만 사용했다. 제어기·모델 호출·물리 step·weld는0이다. 실제 운반·SLAM·yaw 추정·ACT 성공을 잰 것이 아니다. reloc15의 “실제0.221°를12.474°로 오수용”은 사용자 제공 동기이며 이번에 원본 영상을 재분석하거나 재현하지 않았다. 동적 실패/성공 영상을 검토했다고 주장하지 않는다. Mac은 PNG/XML/순수 시험만 했고 GUI·카메라 렌더·물리를 사용하지 않았다.

## 원본·무결성·운영 종료

최종 원본은 `/home/ugrp/ugrp-sim/runs/scenetex2-1e9594a9-static-e`에 보존했다. [검증 기록](gcp-static-e-preservation.json): 5,324파일42,951,931bytes 전체 SHA 일치, 압축267기록40,878,655bytes 복원 SHA 일치. 분석·compatibility·digest의 오류는 모두0이다. 대형 JSON은64KiB 초과 시 zstd 무손실 저장 또는 작은 part로 나눴다. Mac은 요약·작은 원장·해시·대표 몽타주만 회수해 검사했고 전체 원본은 회수하지 않았다. 각 실행 RUN_META와 메타데이터 해시를 보존했다.

`gcp2setup: PASS` 뒤 기존VM만 시작했다. 계정 `changmin5781@gmail.com`, 프로젝트 `ugrp-sim-b-1014`, VM `ugrp-sim-gcp2`, zone `asia-northeast3-a`다. 새VM·모델 키·에이전트 자격 증명을 배포하지 않았다. 첫 프로젝트의 예산정지와 사용자 지정 후속 프로젝트를 구분했다. 새 프로젝트 budget-stop 발동은 관찰되지 않았다. 완료 뒤 실행/임대0을 확인하고 VM의 **TERMINATED**를 확인했다([수명주기](vm-lifecycle.json)). 자료는 로컬 프로젝트/GCP 영속 디스크에 보존하며 Drive는 사용하지 않는다.

Mac 표적3파일 시험은 **55 passed in9.32s**다. 자산·기존 v1해시·XML 물리 불변·명시적 프로필·순수 관문 계획을 검사했다. 독립 [읽기 전용 소스 검토](source-review-e.json)에서 확정P0/P1은 없었지만 카메라 채택 판정을 대신하지 않는다.

## 비교 후보와 실패 보존

| 후보/소스 | 범위·결과 | 결정 |
|---|---|---|
| v1 PR511 | 벽 대비를82–86으로 낮춰 기존 균일 벽띠를 유지; PNG150면 ORB0 | [직전 분포](prior-rejection-table.json) |
| A | 불규칙 얼룩, 먼 descriptor 최대25.10%·동일 패치 최대14.84% | 원본 로컬 보존 |
| B / 7c45215e | 미세 입자·S16·512면·texuniform=true, 144정적 프레임 | 방사형 매핑·JPEG 침범, [거부표](camera-b-rejection-table.json) |
| C / f6acdbd5 | S8·texuniform=false, 264프레임 | ±X면 축 늘어짐, 내부support PNG9/88; [거부표](camera-c-rejection-table.json) |
| D / 89b50131 | ±X축수정·큰 마모, 264프레임 | 내부support0/88, 미채택; [거부표](camera-d-rejection-table.json) |
| E / 1e9594a9 | 축수정·미세마모·1024면, 주행pilot48과 최종264 각각 보존 | 위 최종 정적 결과; NOT_READY |

최초 `3f5feb73`는 H1/H2 provider allow-list 오류로 MODEL_HOST_ERROR·프레임0이었다. 기존 `zone_heldout_scene.install` 준비 어댑터로 수정했고 allow-list는 넓히지 않았다. [실패 기록](host-error-static-a.json)을 보존했으며 이후 완료 수에 섞지 않는다. 원본 경로는 [요약](summary.json)의 remote_runs에 있다. E의 주행pilot48은 최종264와 중복이므로 합산하지 않는다. D의64px/m·31–188mm는 최소8px에 걸리지 않는 면의 명목값이다.

## 재현

Mac의 기존 환경에서 PNG/XML/순수 시험만 한다.

```sh
python -m scripts.generate_scene_tex2 --output <new-assets>
python -m scripts.audit_scene_tex2 --output <new-png-audit>
python -m pytest -q tests/test_scene_tex2.py tests/test_natural_scene_texture.py tests/test_scene_tex2_probe.py
```

GCP는 정확한 소스를 먼저 고정하고 공통 bare를 직접 reference한 새 사본에서 실행한다. 공통 bare/다른 원본을 지우거나 gc/prune하지 않는다. 기존 실행기처럼 소유 세션을 종료한다.

```sh
MUJOCO_GL=osmesa python scripts/ugrp_session.py run <own-session> -- python -m scripts.probe_scene_tex2 --execute --source-sha 1e9594a9fececf1c5fa4387ed7ac9f08a8459629 --setup-proof <copied-gcp2setup-PASS> --output <new-persistent-run>
python scripts/summarize_scene_tex2_probe.py --input <run> --output <new-analysis>
python experiments/2026-10-15-scene-tex2/analyze_camera_compatibility.py --input <run> --output <new-compat> --reader-script scripts/summarize_scene_tex2_probe.py
python experiments/2026-10-15-scene-tex2/digest_camera_results.py --input <run> --output <new-digest> --reader-script scripts/summarize_scene_tex2_probe.py
python experiments/2026-10-15-scene-tex2/verify_saved_raw.py --input <run> --output <new-preservation.json>
```

분석은 Linux/GCP에서만 실행한다. 실제 실행 명령·스크립트 해시·소스 파일 해시는 각 GCP summary에 있다. `--poses drive`는 별도48프레임 진단, `--poses paint_C`는24프레임이다. 전체264의 재현에는 옵션을 생략한다. 정적 판정이며 새30SIM초·10Hz실패 고리 기록은 적용할 동적 실행을 하지 않았다.

## 참고 자료 (2026-10-15/16 확인)

- [MuJoCo3.12.0 공식 렌더 코드](https://github.com/google-deepmind/mujoco/blob/3.12.0/src/render/classic/render_gl3.c#L225): cube TexGen의 texuniform 실제 치수 배율 확인. 문서만으로 영상 검증을 대신하지 않았다.
- [Khronos ARB_texture_cube_map 규격](https://registry.khronos.org/OpenGL/extensions/ARB/ARB_texture_cube_map.txt): ±X면 s=∓Z/t=−Y, ±Y면 X/Z, ±Z면 X/Y로 PNG 비율 수정.
- [MuJoCo 공식 XML texture/material](https://mujoco.readthedocs.io/en/stable/XMLreference.html#asset-texture): 개별 cube면 PNG와 물체/skybox 축 차이 확인.
- [OpenCV 공식 ORB 설명](https://docs.opencv.org/4.13.0/d1/d89/tutorial_py_orb.html): FAST/Harris·방향 보정 BRIEF·Hamming. 이번 비교는 기존 ORB 설정을 유지한다.
- [OpenCV 공식 camera geometry](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html): 실제 카메라/왜곡 모델과 보정의 검증 경계를 구분했다.
- [PR511 기존 질감 검토](../2026-10-15-scene-floor-texture/README.md), `harness/e2e_rgb_gate.py`, 고정 `experiments/2026-09-26-markerless-probe/markerless_probe.py`, [전체 색 소스](color_external_sources.json).
