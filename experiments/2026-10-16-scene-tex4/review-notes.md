# 직접 본 범위와 진단 한계

Mac GUI/브라우저/동영상 앱은 열지 않았다. 모든 비교판은 gcp2의 저장 RGB에서 만들고 이미지 파일만 회수해 읽었다.

- scenetex3 round3.jpg: 주행·상자·가림의 동일 자세를 v1/v2/v3/벽 no-mip와 비교했다. v3 벽 무늬는 더 보이지만 경계 입력이 좋아졌다는 근거로 쓰지 않았다.
- preliminary.jpg: R1b H1 view0 box_palette/r1의 t=0을 5조건으로 봤다. dark/light가 백색으로 나와 geom RGBA override를 확인하고 자기 실행을 중단했다.
- round2-first-review.jpg: 같은 t=0에서 수정된 dark/light/skirt의 실제 적용 색과 바닥·화물 보존을 확인했다.
- round2/comparison.jpg: H1/H2 drive, high_beam_peer_occluded, box_palette/r1의 t=0 여섯 자세를 v1/v3/후보·화질과 비교했다. 가림 때 벽이 안 보이는 장면 한계를 그대로 기록했다.
- boundary-review.jpg: 두 문 지도 view1 drive/r2와 H1 view0 drive/r1의 t=0을 각각 v1, v3, light, skirt로 직접 봤다(총8장). 청록은 평가용 실제 벽–바닥 경계, 빨강은 기존 selfmap 첫 반환이다. v1은 주로 실제 경계를 따라갔다. H1 light는 로봇/하단의 다른 반환이 생겼고, skirt는 바닥 접점보다 걸레받이 위쪽을 골랐다. 두 문에서도 skirt가 위쪽 띠를 고르는 모습이 보였다.

정적 SIM0 평가라 시간순 동적 실패/성공 궤적은 없다. 저장된 다음 영상은 명령/물리 이동이 아니라 atan(1/fx)만큼 yaw를 바꾼 평가용 한 쌍이다. 실제 주행 영상2Hz/마지막10SIM초10Hz, 실패 고리 버퍼, 동적 진동/ACT/운반 성공을 검토했다고 주장하지 않는다. 물리 step·실행 제어 변경이 없으므로 새 기록 고리 버퍼도 이 정적 어댑터의 적용 대상이 아니다.

- round3/comparison.jpg: H1/H2의 같은6자세에서 v1/v3/flat/luma native·no-mip를 봤다. 벽의 약한 cool 톤과 바닥 보존을 확인했지만 육안 유사성을 특징·색 관문 통과로 취급하지 않았다.
