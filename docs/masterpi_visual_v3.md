# MasterPi 외관 모델 v3

2026-09-28. Hiwonder 공식 치수도, 조립 문서, 서보·카메라·초음파 사양으로 MasterPi 외관을 다시 만들었다. 치수와 출처 등급은 `sim/masterpi_geometry_v3.py`에 있다. 조사 기록, 물리 제안, 영향 목록, 실측 목록은 [실험 기록](../experiments/2026-09-28-masterpi-visual-v3/README.md)에 있다.

## 사용

```python
from sim.masterpi_visual_v3 import build_v3_xml, PROFILE_APPEARANCE_ONLY, PROFILE_DRAWING_LAYOUT, SONAR_MOUNT_V3
xml = build_v3_xml(profile=PROFILE_APPEARANCE_ONLY)   # v2 물리 그대로, 외관만 v3
xml = build_v3_xml(profile=PROFILE_DRAWING_LAYOUT)    # 팔 장착·충돌 proxy 치수도 제안(검토용)
```

- `profile`은 필수다. 기본값을 두지 않아 전환할 때 물리 변경 여부를 명시하게 했다.
- 반환 XML은 `build_v2_xml`과 body·joint·actuator 이름이 같다. `sim/multi_masterpi_production.py`의 복제 방식(이름 prefix)과도 호환된다.
- 시각 geom은 모두 `v3_` 접두사를 쓰고 `mass=0`, `contype=0`, `conaffinity=0`, `group=0`이다. 충돌 proxy는 투명(`rgba 0 0 0 0`)이다.
- 초음파 장착은 `SONAR_MOUNT_V3`와 사이트 `v3_ultrasonic_site`(zaxis = 전방)에 있다. 바닥 기준으로 송수신면은 88.0 mm 앞, 높이 61.7 mm다.
- robot_cam 자세와 내부 파라미터는 v2(REAL 적합)와 같다. 집게를 보이게 하려고 옮기지 않는다(AGENTS.md).

## 렌더

```bash
.venv-sim/bin/python scripts/render_masterpi_visual_v3.py --out outputs/masterpi-visual-v3 --reference-dir outputs/masterpi-visual-v3/reference
```

- `mj_forward`와 오프스크린 렌더만 쓴다. 물리 step은 쓰지 않는다.
- 공식 이미지는 저작권 때문에 커밋하지 않는다. URL은 실험 기록에 있다.

## 상태

- 연구 장면, 기본값, 실행 번들은 v2를 유지한다.
- v3 전환, 새 번들 ID, 시각 모델 재검증은 사용자 검토 뒤 별도 PR로 한다.
