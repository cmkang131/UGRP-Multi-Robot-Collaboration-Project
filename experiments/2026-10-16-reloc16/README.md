# reloc16 — 확정 v5 장면 자기 RGB 위치 추정

**NOT_READY. 최대 3라운드를 마쳤고 후속 물리 큐는 내지 않는다.** [PR #532](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/532), `claude/reloc16`, base `claude/map-selfmap` / reloc15 `644289a755ee60df99e916224931c2dec80298eb`. PR #527 `f0ad75304cca6a785ad473a7cf31ffb4ab61df9a`의 장면·경계 facade를 병합했다. 확정 장면은 `walls_floor_contrast_v5_indigo110_s80` + v1 바닥 + `no_mip_v1`; 장면/FOV/물리는 재설계하지 않았다.

## 변경과 정적 관문

- `scene_colour_transition_v2`(기본 off): 주황 A를 로봇 마스크로 오인해 직선 시드를 지우던 규칙을 제거했다. H1/view0/paint_A/r1 반환0→PNG96/JPEG90 96/PIL82 94컬럼([case](paint-A-case.json)). 가장 큰 색 지지741 중 바닥 한 행425·벽 밴드127을 먼저 고쳐, 상속한 3행/10px 밴드 지지와 원본 wall V p00/p100=21/233을 사용한다. 6m 범위·1.5px 원본 p95·이웃 연결은 유지했다.
- 새 장면의 벽 LK를 별도 RGB 클래스 채널로 추가했다(`scene_wall_tracking_v1`). 바닥 LK 마스크/추적점 경로는 그대로이며 벽 점을 z=0 계량 VO로 융합하지 않는다. 별도 벽 inlier 중앙은 PNG49.5/JPEG6/PIL8로 압축 관측은 여전히 약하다.
- 벽 H133을 기존 C 바닥 표식 H143.077±12로 읽는 혼동을 분리했다(`scene_floor_landmark_mask_v1`, 기본 off). 저장56자세의 벽→바닥선 오인88/99/105→0/0/0. 경계 혼합 바닥픽셀62/25/15도 unknown으로 빠지므로 모든 바닥픽셀 보존은 주장하지 않는다. LK/문 경로는 바꾸지 않았다.

|88자세 저장 관문(카메라 자격56, unknown32)|PNG|JPEG90|PIL82|
|---|---:|---:|---:|
|경계 컬럼 중앙/p10, 후보|82/72.5|82/70.5|80.5/68.5|
|v1/native 기준|88/73.5|88/72.5|87/72.5|
|픽셀 오차 중앙/p95|0.5/1.5|0.5/1.5|0.5/1.5|
|기존 검출기 출력 동일|88/88|88/88|88/88|
|실제 접점 없는 반환 컬럼, 후보/기준|0/96|0/98|0/96|

오차·기존 검출기는 유지했지만 **컬럼 관문은 실패**했다. 같은 v5의 원래 색 검출 PNG78/59.5→82/72.5이며, 남은 색/계량 지지523·직선81·연결81은 [순차 거부 표](rejection_table.md)에 있다. 없는 접점을 채우거나 범위를 늘려 기준 수를 맞추지 않았다. 기존RGB edge 색 재검증 후보도 추가반환0이어서 켜지 않았다.

## 운반 yaw: 정적 배경 + 공간 재검증 + 다음 실제 RGB

`reloc16_wall_compass_v1`(기본 off)은 자기RGB 벽–바닥 선의 Manhattan 방향을 쓴다. 분리된 영상영역을 제외한 재적합/그 영역 예측 p95≤원본1.5px, 기존 pitch 오차 경계, 다음 실제 RGB와 발행 회전의 일치가 있어야 수용한다. 미관측/90° 모드 모호성은 명령 예측을 유지한다. xy/전체 metric fix age를 갱신하지 않는다. 새 각도·개수 문턱은 없으며 기존 근거와 출처는 코드/개발 기록에 있다. 새 장면의 정적 yaw 관측 가능은20/88이고 나머지는 unknown이다.

가림에서 `reloc16_active_view_v1`은 기존 pose budget의 setdown→실제 lookaround를 재사용한다. 단순 PWM 팬 기록을 주변 관측 성공으로 세지 않는다. loaded 계량 FK/정답 위치/접촉을 제어 입력에 넣지 않았다.

|운반 라운드|93266: 절대·증분>5° 오수용/수용|93315: 절대·증분>5° 오수용/수용|닫힘 명령 중 수용(각 시드)|place|
|---|---:|---:|---:|---:|
|R1 `93635d6e`|0/66|0/20|0,0|0/2|
|R2 `5f8b3eb2`|0/58|0/39|13,0|0/2|
|R3 `df8115a5`|0/8|0/28|0,0|0/2|

닫힘 명령은 실제 접촉/파지 판정이 아니다. R3 수용 절대오차 최대는0.264°/0.421°, 증분 최대0.339°/0.582°였다. **전체 경로의 yaw/위치가 정확했다는 뜻은 아니다:** R3 전체 추정오차 최대 xy0.652/0.245m, yaw24.20/16.85°가 남았다. 이전0.221°→12.474° 반례는 gcp1 회수 요약만 사용했고 같은 이미지 직접 재생은 못 했다. 새로운 장면/호스트/경로의 수용 수를 과거1/55와 합산하지 않는다.

## 폐루프 주행 비교와 미해결

실행은 모두 gcp2 CPU/MuJoCo3.12.0, 자기 동시≤8(본 R2/R3 각4), 호스트 임대 합계≤40. 원본 물리14회·0프레임 HOST_ERROR4회를 전부 기록했다. R1 selfmap의 누락 matplotlib/g++를 기존 환경에 보충하고 같은 SHA/시드로 hostretry1을 분리했다. selfmap cap60, carry cap150 SIM초다. R1 carry93315만120.8초 setdown envelope 거부(own_rgb:can:1, 최소틈−0.1372m); 나머지 물리 실행은 cap_end다.

|시드|이전 v1 xy 중앙/p95(m)|새 장면 R2 xy 중앙/p95(m)|이전→R2 yaw 중앙/p95(°)|이전→R2 오류 프레임(.1m/5°)|
|---|---:|---:|---:|---:|
|93584|.0444/.1082|.1015/.1056|1.429/2.027→9.996/10.466|6/45→62/63|
|93583|.0853/.1102|.0933/.1563|6.616/7.867→1.817/6.779|29/33→54/75|

같은 gcp2·시드의 장면 짝 비교이며 경로가 같다는 뜻은 아니다. R1 새 장면은 등록0/301×2였다. R2 평면 분리로219/301·221/301 등록을 복구했지만93583 최초 xy.1309m 오등록1건, 주행 정확도 개선 실패다. R3는 기존 reloc11 벽 거리장(`static_walls_v1`)만 선택하는 비교였다. PF sensor update124/108건에서 resolved가 각각0, 등록0/301×2로 **이 선택은 채택하지 않는다**. 절대 주행 오차0/0을 개선으로 세지 않는다. [R3 짝 표](pair-table.md)의 미측정은 이 뜻이다. 가림 운반·재관측의 안정적 위치 추정과 목적지 놓기는 미해결이다.

첫30 wall/SIM 중앙 R2=4.866, R3=5.113으로 기록 전용3.5 경고이고 중앙6.0 차단 기준 아래다. 경계/compass 배열화는 저장168 RGB 각각168/168 출력 일치를 확인했고 CPU 중앙 .1003→.0757초 / .1446→.00792초였다. 폐루프 속도와 별개다. 계획/탐색은 기존40000노드 등 계산량 예산을 유지했다.

## 검증·보존·참고 자료

관련 비물리 테스트 **150개 통과**(88+62, Mac 물리/렌더/GUI0). [명령/범위](pytest-final.txt), [전체 요약](summary.json), [18실행 원본·저장 manifest/result SHA256](inventory.json), [순차 funnel/막은 물체/최소틈](rejection-table.json). 모든 실행의 원본 manifest 파일 해시를 gcp2에서 확인했다. invisible_measurements=held_world_reads=0이다. 위치 추정기에 실시간 정답을 넣지 않고 정답 오차는 평가 원장에 분리했다. 모델/학습0, weld OFF. 실제 로봇·ACT 학생 성공은 검증하지 않았다.

실패 selfmap/운반과 정상 등록·주행 구간을 gcp2 ffmpeg으로4배속·전체2Hz·직전10초10Hz로 만들고 파일로 직접 보았다. [본 범위와 시간순 기록](playback-review.md), [최종 대표 실패 영상](videos/representative-selfmap93584-r3-failure.mp4), [해시/원본](representative.json). **완주 성공 영상은 없으며 정상 구간을 대체 성공으로 세지 않는다.** Mac GUI0, ffprobe로 재생 정보만 확인했다.

회수61파일·12,171,257bytes의 SHA256을 원격값과 대조했다([회수 검증](retrieval-verification.json)). 원본은 gcp2 영속디스크에 있고 전체 다운로드/백업은 하지 않았다. 대표 R3 raw는 부모 milestone+keep=raw로 보존하며 raw 내부 manifest를 고치지 않았다. 모든 source 사본은 git-shared.git을 직접 reference하고 gc/prune/삭제하지 않았다. [종료 확인](lifecycle.json): 자기 워커0·자기 임대만 제거, 다른 임대/프로세스가 있어 VM은 RUNNING 유지.

먼저 읽은 자료: [reloc15 README](../2026-10-15-reloc15/README.md)·summary·rejection-table·carry-yaw·quality-admission-audit, 로컬 `outputs/e2e18-admin/research/carryyaw.md`의 추천1–3, [scene-tex5](../2026-10-16-scene-tex5/README.md) 경계/LK 진단. [정확한 경로·SHA256](references.json), [진행 기록·상수 근거·문헌 링크](development-log.md). GlobustVP의 선/Manhattan 기하, Olson/Agarwal의 null 가설, OpenCV LK/HSV, 고정 Nav2 AMCL wall field를 기존 구조에 맞춰 사용했다. 전체 알고리즘 이식이나 공분산의 통계적 보정을 검증했다고 주장하지 않는다.
