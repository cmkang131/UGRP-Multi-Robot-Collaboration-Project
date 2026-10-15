# reloc16 — 확정 v5 장면의 자기 RGB 위치 추정

진행 중. reloc15 `644289a755ee60df99e916224931c2dec80298eb` 위에 PR #527 `f0ad75304cca6a785ad473a7cf31ffb4ab61df9a`를 병합했다. main·reloc15 원본은 변경하지 않는다. 확정 장면은 `walls_floor_contrast_v5_indigo110_s80` + v1 바닥 + `no_mip_v1`. 새 후보는 기본 off, 이전 장면/호스트 결과와 합산하지 않는다.

## 수정 전 원본 분포

`rejection-before.json`은 gcp2의 scenetex5-r3-indigo110_s80 저장 원본 88자세(기존 경계 카메라 자격 56)×3인코딩을 원래 검출기로 다시 계산했다. PNG 총 5376컬럼: 반환4279, 색 지지741, 직선 합의301, 연결55. 색 지지741 세분은 바닥 한 행 클래스425, 벽 밴드127, 범위93, 색 교차 없음96이다. JPEG90은 바닥345/벽277, PIL82는 바닥351/벽436이다. 분포를 먼저 기록하고 가장 큰 한 행 지지·주황 시드 결함부터 고친다. 기존 RGB 비교판(실패 paint B/C와 정상 drive)을 파일로 직접 보았다. 정적 판은 동적 재생 검토를 대신하지 않는다.

## 예산과 경계

gcp2 CPU만, 자기 동시≤8·전체≤40, 실패 시드 selfmap93584/93583, carry93266/93315 먼저. 폐루프 최대3라운드. 한 실행 cap은 selfmap60/carry150 SIM초이며 시간 상한 종료는 cap_end로 구분한다. 렌더/분석은 gcp2만; Mac은 텍스트·요약·실패 몽타주·≤8MB 영상만 회수한다. 예산 raw8×0.5GiB + 분석/사본/최대3라운드 임시8GiB =20GiB, Mac회수≤64MiB; 시작 여유 gcp2328GiB/메모리123GiB, Mac37GiB. 모든 원본은 dev·영속디스크 보존, 별도 전체 백업 없음. 임대 reloc16.json 생성, warp1 임대 보존, 다른 임대가 있으면 VM정지 금지. 모델/학습0, weldOFF, 평가정답은 controller와 분리.

## 설계와 참고 자료

- 사용자 지정 reloc15 README/summary/rejection-table/carry-yaw/quality-admission-audit 및 `outputs/e2e18-admin/research/carryyaw.md`를 읽었다. 누적/증분 오차·단독 상자/공동 빔·gcp1/gcp2를 구분한다. reloc15의 0.221°→12.474° 반례는 gcp1 디스크에 접근하지 않으며 회수 요약만 사용한다.
- scene-tex5 README와 coverage-diagnosis: 주황 규칙은 로봇 인식기가 아니다. 학습된 별도 로봇 마스크라고 취급하지 않는다. 벽/바닥 색 지지는 자기 RGB와 고정 calibration만 사용한다.
- [OpenCV tracking API](https://docs.opencv.org/4.13.0/dc/d6b/group__video__track.html), 2026-10-16 원문: LK의 피라미드·마스크·ECC 양쪽 유효 영역을 구분한다. LK 벽 점은 바닥 계량 VO로 융합하지 않는다.
- [Liao et al., GlobustVP, CVPR2025](https://arxiv.org/html/2505.04788v1), 원문 §3–4: 이미지 선의 투영 평면과 Manhattan 방향 제약을 참고한다. 기존 구조에 색으로 확인한 벽–바닥 선의 수평 방향만 추가하며 SDP 전체를 이식했다고 주장하지 않는다. 축의 90°/180° 모호성과 명목 카메라 회전 오차를 유지한다.
- [Olson & Agarwal, RSS2012](https://www.roboticsproceedings.org/rss08/p40.pdf), 원문: 오관측 null 가설을 보존한다. 독립 노이즈가 검증되지 않은 절대/증분 covariance를 임의로 Kalman융합하지 않는다. 공간 재검증·다음 실제 RGB 확인 전에는 명령 예측을 유지한다.

실제 새 장면 폐루프 성능·배포 완료·실물 성공은 아직 주장하지 않는다.

R1 저장 RGB 후보(8a005c7d): 주황 시드 제거·이웃 지지 후 PNG 컬럼78/59.5→81/69.5, 오차.5/1.5·색검출88/88 유지. v1/native88/73.5보다 아직 낮아 폐루프에 내지 않았다. 새 진단은 실제 접점 누락 중111개가 어두운 벽의 V<p01,304개가 명목6m 범위 밖,64개가 후보/합의임을 분리했다. 새 V범위는 같은 원본88×3인코딩 wall V p00/p100=21/233(히스토그램 별첨); hue/S와Lab/chroma 경계는 유지한다. 계량 범위6m는 바꾸지 않는다. 강도 차분 i→i+1의 첫 바닥 행 i+1을 반환하도록 v2의 행 규약을 맞춘다(v1 paint_A=87, 평가 접점86.5, 이전v2=86); 선/GT로 누락 픽셀을 채우지 않는다.
