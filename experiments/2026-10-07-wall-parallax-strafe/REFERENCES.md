# 근거와 적용 범위

- Forster, Pizzoli & Scaramuzza, RSS 2014, *Appearance-based Active, Monocular, Dense Reconstruction for Micro Aerial Vehicles*.
  https://www.roboticsproceedings.org/rss10/p29.pdf
  관측 위치를 선택할 때 깊이·자세·외관/텍스처에 따른 정보 이득을 고려한다.
  균일한 벽은 이동해도 영상상 대응 정보가 부족할 수 있다고 명시한다.
  이 작업은 NBV 최적화 구현이 아니라 사전 작성한 횡이동 취득 진단이다.
  광축 근처 점의 pinhole 근사 d≈f*b_perp/Z에서, 시선에 수직인 이동은 같은 길이의
  광축 방향 이동보다 깊이 관측에 유리하다. 실제 횡이동·대응 품질·오도메트리 정확도는 보장하지 않는다.
- *Active Perception with A Monocular Camera for Multiscopic Vision* (2020).
  https://arxiv.org/abs/2001.08212
  능동 카메라 위치 변경으로 다중 시점/시차를 얻는 공개 논문. 본 실험은 팔 이동 대신
  고정된 팔 명령과 메카넘 횡이동을 사용한다. 해당 논문의 성능을 승계하지 않는다.
- OpenCV LK/GFTT/DLT, ORB-SLAM2 시차·재투영 검사 및 코드 라이선스는
  [동결 검출기 근거](../2026-10-07-wall-parallax/REFERENCES.md)를 그대로 따른다.
- 물리/카메라/포트는 PR #406의 지정 SHA를 Git object로 읽기 전용 복사한다.
  제3자 FUJI roller 자산은 원본 LICENSE/source.json을 함께 보존한다.
