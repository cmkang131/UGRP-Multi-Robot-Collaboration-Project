# 직접 본 정적 범위

모든 비교판/경계선/검출 윤곽은 gcp2에서 저장 RGB로 만들고 Mac에는 이미지 파일만 회수했다. 화면 앱·브라우저·영상 앱·시뮬레이터 GUI는 열지 않았다.

- 이전 scenetex4 boundary-review: v1/light/skirt의 실제 접점과 첫 반환을 비교했다. skirt가 높은 띠를 반환하고 light가 로봇/하단을 반환하는 반례를 봤다.
- R1 boundary-review6개 drive 시점: v1/native·v1/no-mip·보라3개의 같은 자세를 봤다. 후보색은 확실히 바뀌지만 조명 아래 명목 hue가 유지된다고 가정하지 않았다.
- R1 failure-review: H1 drive 정상1, H1 paint_B 실패1, H2/two_doors paint_C 실패2를 같은 SIM0에서 봤다. C 앞선/가운데 흰 표시 근처 또는 B 앞선이 실제 벽보다 낮은 반환을 만들었다.
- R2 boundary-review: 같은 drive/B/C에서 어두운 남보라로 paint 앞선 오류는 줄고 빈 경계 컬럼이 늘어난 것을 봤다. 붉은 반환이 없는 틈을 보간한 것으로 읽지 않았다.
- R3 boundary-review: 같은 drive/B/C와 채도80/65에서 실제 접점을 따르는 부분과 빈 컬럼을 비교했다.
- R3 coverage-review: H1/H2/two_doors의 paint_A와 정상 H1 drive를 봤다. 접점이 보이는데 A 구역이 있는 프레임의 경계 반환이 거의/전부 사라졌다. 후속 픽셀 감사에서 색 지지96/96·주황 시드 제외96/96을 확인했다. 중립 바닥 분류가 문제라는 초기 추측은 반증됐다.
- R3 pil-counterexample: corridor/paint_A/r1의 v1/채도65 PNG·PIL82를 직접 봤다. 실제로는 벽만 보이는 시점인데 PIL82 후보의 아래쪽 두 작은 벽 영역에 B 패치 윤곽이 생겼다. 각67px가 평가상 벽이며 바닥0임을 별도 원장으로 확인했다.

이 자료는 시간순 동적 궤적이 아니라 **SIM0 정적 자세**와 미소 yaw 평가 쌍이다. 실패/성공의2Hz 전체·마지막10SIM초10Hz 동적 재생, 진동·동작 순서, 실패 고리 버퍼를 검증했다고 주장하지 않는다. 실제 실행기/물리 경로를 수정하지 않아 이 정적 어댑터에 동적 고리 버퍼를 새로 넣지 않았다.
