# scenetex4 — 벽·바닥 대비 우선

판정 대기. scenetex3 NOT_READY 줄과 scenetex3b Codex 종료를 5분 간격 첫 재검사에서 확인했다.
사용자 2026-10-16: “이거는 방식을 바꿔야 할듯”, “벽과 바닥 색을 좀 더 구분되게 하던가”.

v1 바닥 PNG·바닥 XML을 고정한다. R1: 어두운 균일 벽, 밝은 균일 벽, 밝은 벽+8cm 걸레받이.
벽 ORB는 기록용이다. 기존 selfmap 경계 컬럼의 중앙값·p10, 정답 경계에 대한 오차 분포,
모든 자세의 바닥 ORB20/7·내부support·연속 match·LK를 v1과 비교한다. 새 여유 상수 없음.
동일한 88 자세 × PNG/JPEG90/PIL82 = 후보·화질별 264 RGB 프레임이다.
렌더 native/no_mip는 각각 분리하며 이전 v1/v3는 동일 gcp2 저장 RGB와 해시/자세를 확인해 비교한다.
물리 step·LLM·Mac 렌더·GUI 없음. 위치 오차·동적 VO·ACT·운반 성공 검증과 구분한다.

원인 수정 전 [거부표](rejection-table.json): scenetex3 주 거부는 특징 회귀57/88(native),47/88(wall filter).
걸레받이8cm와 벽 RGB는 재질 설계값이며 실측 건물 규격/새 관문 상수가 아니다.
S16은 기존 전색 페인트 S20 미만, 밝기 후보는 기존 검정/흰 표식의 사이를 의도한다.
실제 렌더/JPEG 침범은 이전 감사 도구로 재검사하며 검출기 범위를 바꾸지 않는다.

## 참고 자료 (2026-10-16 원문 확인)

- [OpenCV HSV inRange](https://docs.opencv.org/4.10.0/da/d97/tutorial_threshold_inRange.html): 기존 범위 고정, 색 분할은 평가 전용.
- [OpenCV 특징점](https://docs.opencv.org/4.12.0/dd/d1a/group__imgproc__feature.html): 실제 LK 입력의 Shi–Tomasi 특징을 따로 측정.
- [OpenCV LK](https://docs.opencv.org/4.7.0/dc/d6b/group__video__track.html): 저장 영상쌍에 기존 LK를 그대로 적용.
- 기존 height_free_wall.py의 uniform band + horizon + edge: 벽 질감의 증가가 이 신호를 해칠 수 있어 균일 벽을 대조한다.

## 실행 예산

gcp2 n4-highcpu-64, 영속 디스크343GiB·가용메모리122GiB 확인. R1 6arm×512MiB + 타 작업8GiB 예약.
Mac fetch-lite32MiB, 여유38GiB 이상. /home/ugrp/ugrp-sim/leases/scenetex4.json 사용.
다른 임대 beampair6/simalt5 존재. 첫 프로젝트/gcp1 접근·VM 정지·자격 증명 전송 없음.
