# 렌더 프로필

`sim.render_profile.install(scene, name)`은 기존 프로필의 이름·정의 해시·전후 XML 해시를 장면 manifest에 남긴다. 이 파일은 P03 고정 자산이므로 main과 바이트 동일하게 유지한다. 새 소비자는 `sim.render_profile_selection.for_name(name)`으로 모듈을 선택한다. `floor_light_textured_v1` 또는 `walls_floor_textured_v2`를 요청할 때만 별도 `sim.render_profile_textured`를 불러오며 기존 registry를 수정하지 않는다. 생략/`shadows_v1`은 원래 XML 바이트를 유지한다. `floor_light_v1`은 기존 밝은 바둑판이며 기본 동작을 바꾸지 않는다.

## 벽·바닥 구분 자연 질감: walls_floor_textured_v2 (기본 off)

2026-10-15 사용자: “벽에도 넣고, 벽 / 바닥 색 다르게 해. 쉽게 구분할 수 있도록. 그렇게 시뮬 바꾼 뒤에 그 상황에 효율적일 수 있는 알고리즘으로 다시 설계 ㄱ(첨부터 다시는 말고, 이거에 맞는 방식으로 하면 좋을듯)”, “일단, 시뮬 환경 먼저 세팅하고 / 그 환경에 맞춰서 다 병렬처리로 진행하면 좋을듯”. 별도 장면 버전이며 기존 v1·다른 호스트 결과와 합산하지 않는다.

낮은 채도의 푸른 회색 벽과 밝은 따뜻한 회색 바닥에 독립적인 얼룩·마모·입자를 넣었다. 반복 타일·인공 마커·AprilTag는 없다. 기존 조명, 충돌 형상·마찰·카메라/FOV·로봇·화물·색 표식은 유지한다. 바닥3072² PNG 한 장, 벽1024² cube면150장을 SHA로 고정했다. 최종 비교 E의 자산 manifest는 `9afa87ec4a04eb230f284b031e4bb57d0ca8ff1a2c6c967b29a9b7da3c3ee396`, 프로필 해시는 `edf3a92a41422a10151b9cb95ec7925998f6790485e28b1920d03ce4576cd9a8`이다.

| PNG 원본 | 벽 | 바닥 |
|---|---|---|
| 실제 HSV 범위 (OpenCV) | H108–114 / S8–10 / V98–134 | H15–18 / S8–10 / V146–180 |
| ORB (nfeatures=800) | 최소0·중앙0·최대483, 양수47/150면 | 640×480 창4개: 793/767/772/793 |
| 먼 descriptor 유사 비율 | descriptor가 있는47면 중 중앙0·최대2.51%; 103면은 미측정 | 창4개 모두0 |
| byte 동일32×32 패치 | 150면 모두0 | 0 |

명목 V간격12, Lab L범위 벽103–139/바닥153–185(OpenCV uint8)다. 기존 포괄 페인트 S≥20, 상대 검정 상한 V=.38×255=96.9, 흰 표식 V>180을 피했다. PNG의 **108개 고정/상위집합 HSV·RGB·PIL 범위는 겹침0**이다. 문맥/지지 마스크·조명/압축 후 픽셀에는 이0건을 확대하지 않는다. [전체 표·한계](../experiments/2026-10-15-scene-tex2/png-audit-e/color-ranges.md)를 따른다.

GCP 검토에서 얇은 벽의 `texuniform=true` 방사형 늘어짐과 ±X면의 잘못된 PNG 축을 발견해 v2만 고쳤다. `texuniform=false`이며 ±X면은 PNG폭Z/높이Y, ±Y면은 X/Z, ±Z면은 X/Y다. [MuJoCo3.12.0 렌더 코드](https://github.com/google-deepmind/mujoco/blob/3.12.0/src/render/classic/render_gl3.c#L225), [Khronos cube-map 규격](https://registry.khronos.org/OpenGL/extensions/ARB/ARB_texture_cube_map.txt)에 근거한다. 기존 v1의 코드·자산·해시는 유지한다. 정사각 cube PNG의 비율과 실제 벽면 화면은 달라 각각 측정했으며, 원본의0 ORB도 그대로 보존했다.

**최종 정적 관문 판정은 NOT_READY다.** 소스 `1e9594a9fececf1c5fa4387ed7ac9f08a8459629`로 gcp2 네 지도264/264프레임, 물리/카메라 동일성12/12와 원본 해시를 확인했다. 벽 내부 ORB는 전체 v2 PNG/JPEG 각각11/88프레임에만 있고, 운반 가림16/16에서는 벽이 보이지 않아0이다. PNG 상자종류 검출은 두 기준과88/88 일치했지만 JPEG는 밝은 바닥 기준76/88, 이전 질감 기준82/88이다. 새 질감이 운반 회전 추정을 해결하거나 기존 검출기와 완전 호환된다고 보지 않는다.

`harness.scene_tex2_perception`은 명시적 v2 전용 PNG 명목 보정 후보다. 기존 벽띠 std≤3을 전역 수정하지 않는다. 새 분산 상한은 PNG 휘도·B−R 범위의 범위²/4로 계산하고 벽→바닥 구간 전이를 요구한다. 실제 주행16프레임에서 PNG/JPEG 각각 컬럼 후보4개만 남았고 위치 정확도는 미검증이어서 **미승인** 상태다. 프로필 전용 [후보 설정](../configs/calibration/scene_tex2_camera_candidate.json)은 색 검출의 lossless 원본 경로와 벽 판독 비활성 상태를 기록하며 자동으로 소비자를 변경하지 않는다. 기존 보정의 v3 유효성·기존 실행기의 연결·새 조건 위치 추정은 별도 검증이 필요하다.

```python
from sim.render_profile_selection import for_name
name = 'walls_floor_textured_v2'
scene = for_name(name).install(scene, name)
# 기존 HIGH 경로에서는 같은 nearclip wrapper와 verify_model을 사용한다.
```

이 선택기 연결은 고정 실행기를 자동 변경하지 않는다. 소비자의 첫 install/실제 모델 audit에 요청 프로필을 연결하고 새 소스·번들을 고정해야 한다. [실험·원본·funnel·재현](../experiments/2026-10-15-scene-tex2/README.md)을 따른다. Mac에서는 PNG/XML/순수 테스트만 했고 렌더·물리·GUI는 사용하지 않았다.

## 자연 질감: floor_light_textured_v1 (기본 off)

2026-10-15 사용자: “특징점 부족하면, 맵에 머 질감같은 거 넣어도 됨. 너무 매끈해서 그런 거면. 현실은 그렇게 미끄럽지 않으니까”. 이에 따라 회색 콘크리트/에폭시의 얼룩·마모·긁힘을 고정 seed `20261015`로 생성했다. 실물 표면을 측정하거나 복제한 것은 아니다. 이 변경은 시각 재질만 바꾸며 **마찰계수를 바꾸지 않는다**.

- `floor_light_v1` 조명을 재사용한다. 16×16 m 바닥 전체에 PNG 1장을 한 번 매핑하며 바둑판을 없앤다.
- `sim.wall_texture.walls_from_xml`의 벽 판독을 재사용한다. 테이프나 마커를 넣지 않는다. 기존 box 벽에 서로 다른 여섯 면의 cube 재질을 입히고 `texuniform=true`로 각 면에 한 번 매핑한다. 충돌·광선 검사 대상 geom의 개수와 형상을 유지한다. 벽의 PNG는 실제 면 비율로 생성 후 cube용 정사각형으로 바꾸며, 실제 면 방향·연결·축척은 GCP 영상 검토가 남았다.
- 카메라 위치/FOV, 로봇 외관, 빔 끝 띠, 상자/손잡이, 구역 페인트, 물리·접촉은 유지한다. RGB 채널을 같게 해 S=0으로 만들었다. [색 범위 표](../experiments/2026-10-15-scene-floor-texture/color-ranges.md)의 81개 범위에서 원본 픽셀 침범은 모두 0이다. 조명·압축 이후의 오검출/검출 손실은 아직 검증하지 않았다.
- 자산은 `sim/assets/floor_light_textured_v1/manifest.json`과 PNG SHA-256으로 고정한다. manifest 해시가 프로필 해시에 들어가고 적용 때 manifest/사용 PNG를 검사한다. 누락·변조·미지원 벽 치수·다른 벽 무늬와의 중복 적용은 거부한다. 지원 지도는 `maps/zones_final_v3/`의 두 문, 복도, hardmaps H1/H2 네 지도다.
- PR #511 검토 수정에서 벽의 밝기 범위를 82–86으로 낮췄다. PNG 창의 벽띠 균일성과 원근·조명·JPEG 근사의 실제 벽 검출/기존 frame gate를 [별도 감사](../experiments/2026-10-15-scene-floor-texture/README.md#pr-511-검토-수정-비색-인식과-xml-경로)로 기록한다. 바닥은 동일하며 벽 ORB는 150면 모두 0이다. 실제 카메라 호환성과 새 프로필 보정은 미검증이며 GCP 정적 관문에서 다시 잰다. 기본 검출기·보정값은 유지한다.
- 텍스처 XML 경로는 `compiler.texturedir="sim/assets/floor_light_textured_v1"`와 파일명이다. 문자열 장면을 읽을 때 저장소 루트를 cwd로 사용한다. XML을 파일로 내보내면 XML 디렉터리를 기준으로 같은 상대 자산 구조를 함께 배치한다. XML 해시는 checkout 절대경로를 포함하지 않고 자산 해시는 별도로 기록한다.
- **켠 실행은 새 장면 버전**이다. 이전 프로필/시드 결과와 합산하지 않는다. 학습 자료·교사 관문·학생 평가도 이 장면 버전으로 별도 수집/측정한다. 인공 마커와 색 인식 범위 침범은 금지한다.

## 켜는 방법과 소비자 연결

장면을 처음 구성하는 곳의 기존 `install(scene, 'floor_light_v1')`를 다음처럼 선택 가능하게 바꾼다. 기존 프로필을 설치한 인스턴스에 다른 프로필을 다시 설치하면 실패한다.

```python
from sim.render_profile_selection import for_name
from sim.final_pair_highpose_nearclip import wrap, audit
profile = bundle.get('options', {}).get('render_profile', 'floor_light_v1')
render_profile = for_name(profile)
scene = wrap(render_profile.install(scene, profile))
# GCP에서 실제 모델을 만든 뒤, 요청값과 실제 바인딩 모두 검사/보존:
render_audit = render_profile.verify_model(model, profile)
nearclip_audit = audit(model, base_profile=profile)
```

새 번들에는 `options.render_profile = "floor_light_textured_v1"`, `wall_texture = "off"`를 명시한다. `wrap`은 새 프로필을 지원하고 실제 부모 프로필을 기록한다. 기존 nearclip 값·기본 기록/해시는 유지한다. `verify_model`은 PNG 해시와 컴파일된 텍스처의 채널별 히스토그램·재질 연결을 점검한다. 히스토그램은 면 방향을 검증하지 않으므로 정적 영상 확인도 필요하다.

| 소비자 | 다음 소스 통합에서 바꿀 연결점 |
|---|---|
| 자기 지도 #506, AMCL 기록 #507 | 상속된 `sim/wall_parallax_strafe.py:make_scene`의 첫 `install`과 `sim/solo_cyan_v106.py:reset`의 하드코딩된 `verify_model(..., 'floor_light_v1')`를 요청 프로필로 연결. nearclip audit에도 같은 값을 전달. 소스/번들 해시 새로 고정 |
| 단독 운반 #505, ACT 빔/상자 교사 관문 | 해당 PR의 `sim/grasp_act_scene.py:make_scene`에서 `plan`에 고정한 프로필로 첫 `install`; 각 실행기의 실제 모델 audit 기록에 같은 값 사용 |
| 기존 pair stage 교사 probe | `scripts/run_pair_stage_probes.py`도 기존 소스 고정 대상이므로 수정하지 않는다. 이 실행기의 기존 CLI에는 질감 프로필이 등록되지 않는다. 질감을 쓸 새 소비자 어댑터에서 위 선택기·적용·audit을 연결하고 새 번들/소스를 고정해야 한다 |

이 PR은 별도 질감 프로필/API·지연 선택기와 nearclip 호환을 제공한다. 질감 계획 생성기는 새 선택기로 프로필을 기록한다. 기존 P03 조합 핀·실행 번들·고정 실행기는 그대로 보존한다. **#505/#506/#507의 기존 하드코딩된 실행기가 옵션 한 줄만으로 바뀌는 것은 아니다.** 각 소비자의 위 연결 변경·오프라인 검증·새 소스 고정 후 승인된 GCP 진단에 사용한다. 본 PR은 그 브랜치나 현재 대기 실행을 수정하지 않았다.

[오프라인 측정·재현 명령](../experiments/2026-10-15-scene-floor-texture/README.md)과 `scripts/make_scene_texture_plan.py`를 따른다. 대기열은 `approved=false` 및 모든 `ready*`/`execute`/`enabled=false`다.

## 참고 자료 (2026-10-15 확인)

- Rublee, Rabaud, Konolige, Bradski, *ORB: An efficient alternative to SIFT or SURF*, ICCV 2011, pp. 2564–2571, DOI [10.1109/ICCV.2011.6126544](https://doi.org/10.1109/ICCV.2011.6126544). [OpenCV 공식 ORB 설명](https://docs.opencv.org/4.13.0/d1/d89/tutorial_py_orb.html)에서 서지와 FAST/방향 보정 BRIEF·Hamming 사용을 확인했다. IEEE 원문은 접근 확인 화면에 막혀 읽지 못했다.
- [*Robust RGB-D SLAM Using Point and Line Features for Low Textured Scene*, Sensors 20(17), 4984 (2020)](https://www.mdpi.com/1424-8220/20/17/4984), DOI 10.3390/s20174984. 출판사/PMC 검색 본문의 실험 설명에서 ORB-SLAM2가 `fr3_str_ntex_far/near`에서 실패한 사례를 확인했다. 전체 페이지/PDF 열람은 차단되어 표의 수치를 인용하지 않았다. RGB-D 사례이며 이번 자기 RGB 장면의 성공 근거가 아니다.
- [MuJoCo 공식 XML reference: texture/material](https://mujoco.readthedocs.io/en/stable/XMLreference.html#asset-texture): PNG/cube 면·`texrepeat`·`texuniform` 규칙을 확인했다. GCP 실행 MuJoCo 버전에서의 실제 바인딩/영상은 별도 관문이다.
