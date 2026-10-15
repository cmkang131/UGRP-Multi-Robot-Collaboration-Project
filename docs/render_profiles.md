# 렌더 프로필

`sim.render_profile.install(scene, name)`은 장면 XML에 선택한 프로필을 적용하고 이름·정의 해시·전후 XML 해시를 장면 manifest에 남긴다. 생략/`shadows_v1`은 원래 XML 바이트를 유지한다. `floor_light_v1`은 기존 밝은 바둑판이며 기본 동작을 바꾸지 않는다.

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
from sim.render_profile import install, verify_model
from sim.final_pair_highpose_nearclip import wrap, audit
profile = bundle.get('options', {}).get('render_profile', 'floor_light_v1')
scene = wrap(install(scene, profile))
# GCP에서 실제 모델을 만든 뒤, 요청값과 실제 바인딩 모두 검사/보존:
render_audit = verify_model(model, profile)
nearclip_audit = audit(model, base_profile=profile)
```

새 번들에는 `options.render_profile = "floor_light_textured_v1"`, `wall_texture = "off"`를 명시한다. `wrap`은 새 프로필을 지원하고 실제 부모 프로필을 기록한다. 기존 nearclip 값·기본 기록/해시는 유지한다. `verify_model`은 PNG 해시와 컴파일된 텍스처의 채널별 히스토그램·재질 연결을 점검한다. 히스토그램은 면 방향을 검증하지 않으므로 정적 영상 확인도 필요하다.

| 소비자 | 다음 소스 통합에서 바꿀 연결점 |
|---|---|
| 자기 지도 #506, AMCL 기록 #507 | 상속된 `sim/wall_parallax_strafe.py:make_scene`의 첫 `install`과 `sim/solo_cyan_v106.py:reset`의 하드코딩된 `verify_model(..., 'floor_light_v1')`를 요청 프로필로 연결. nearclip audit에도 같은 값을 전달. 소스/번들 해시 새로 고정 |
| 단독 운반 #505, ACT 빔/상자 교사 관문 | 해당 PR의 `sim/grasp_act_scene.py:make_scene`에서 `plan`에 고정한 프로필로 첫 `install`; 각 실행기의 실제 모델 audit 기록에 같은 값 사용 |
| 기존 pair stage 교사 probe | 이미 지원하는 `--render-profile floor_light_textured_v1` 사용. plan-only와 실제 실행은 구분 |

이 PR은 공통 프로필/API와 nearclip 호환을 제공한다. **#505/#506/#507의 기존 하드코딩된 실행기가 옵션 한 줄만으로 바뀌는 것은 아니다.** 각 소비자의 위 연결 변경·오프라인 검증·새 소스 고정 후 승인된 GCP 진단에 사용한다. 본 PR은 그 브랜치나 현재 대기 실행을 수정하지 않았다.

[오프라인 측정·재현 명령](../experiments/2026-10-15-scene-floor-texture/README.md)과 `scripts/make_scene_texture_plan.py`를 따른다. 대기열은 `approved=false` 및 모든 `ready*`/`execute`/`enabled=false`다.

## 참고 자료 (2026-10-15 확인)

- Rublee, Rabaud, Konolige, Bradski, *ORB: An efficient alternative to SIFT or SURF*, ICCV 2011, pp. 2564–2571, DOI [10.1109/ICCV.2011.6126544](https://doi.org/10.1109/ICCV.2011.6126544). [OpenCV 공식 ORB 설명](https://docs.opencv.org/4.13.0/d1/d89/tutorial_py_orb.html)에서 서지와 FAST/방향 보정 BRIEF·Hamming 사용을 확인했다. IEEE 원문은 접근 확인 화면에 막혀 읽지 못했다.
- [*Robust RGB-D SLAM Using Point and Line Features for Low Textured Scene*, Sensors 20(17), 4984 (2020)](https://www.mdpi.com/1424-8220/20/17/4984), DOI 10.3390/s20174984. 출판사/PMC 검색 본문의 실험 설명에서 ORB-SLAM2가 `fr3_str_ntex_far/near`에서 실패한 사례를 확인했다. 전체 페이지/PDF 열람은 차단되어 표의 수치를 인용하지 않았다. RGB-D 사례이며 이번 자기 RGB 장면의 성공 근거가 아니다.
- [MuJoCo 공식 XML reference: texture/material](https://mujoco.readthedocs.io/en/stable/XMLreference.html#asset-texture): PNG/cube 면·`texrepeat`·`texuniform` 규칙을 확인했다. GCP 실행 MuJoCo 버전에서의 실제 바인딩/영상은 별도 관문이다.
