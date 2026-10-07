# 출처와 적용 범위

- **사용자 결정(2026-10-07, 이 작업 지시)**: 2–3cm 세로 테이프,20–30cm 불규칙 간격,
  2–4cm 불규칙 조각, 반복 패턴 금지. 배치 RNG/색 값은 실측이 아닌 재현용 설계다.
  일치하는 실물 경기장 사진이 없다는 [egomap15 감사](../2026-10-07-wall-parallax-strafe/RESULTS.md)를 유지한다.
- [MuJoCo3.3.5 XML reference: texture](https://mujoco.readthedocs.io/en/3.3.5/XMLreference.html#asset-texture):
  2D texture는 primitive의 local XY에서 +Z로 투영, finite plane에 적합. PNG는 직사각형 가능.
  이 때문에 긴 직육면체에 cube map을 임의 반복하지 않고 수직4면에 각각 한 장씩 매핑한다.
- [material texrepeat/texuniform](https://mujoco.readthedocs.io/en/3.3.5/XMLreference.html#asset-material):
  `texrepeat="1 1"`, `texuniform="false"`로 해당 면에 한 번 매핑. emission/specular/reflectance0.
- [geom](https://mujoco.readthedocs.io/en/3.3.5/XMLreference.html#body-geom):
  `contype/conaffinity=0` 시각용 평면을 정적 worldbody에 추가. 원 충돌 벽/접촉/질량은 유지.
  높이/방향/가로 길이는 실행 전 고정 scene에서 읽는 환경 제작 정보이며 detector 입력이 아니다.
- [Forster et al., SVO, RSS2014](https://www.roboticsproceedings.org/rss10/p29.pdf):
  영상 특징/텍스처의 중요성에 대한 기존 방법 근거. 이번은 SVO/모델 학습 구현이 아니라
  동결 OpenCV LK/DLT parallax_v1의 자료 변화 실험이다. 무늬만으로 성공한다는 근거는 아니다.
- 시차/active perception의 기존 공개 코드·논문은
  [egomap14](../2026-10-07-wall-parallax/REFERENCES.md),
  [egomap15](../2026-10-07-wall-parallax-strafe/REFERENCES.md)를 그대로 계승한다.

문헌은2026-10-07 공식 문서/논문을 확인했다. 새 외부 라이브러리/venv 설치0.
