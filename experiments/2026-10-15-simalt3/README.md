# simalt3 — gcp2 MJWarp 효율 시험

**NOT_ADOPTED / ready=false.** 입력 변환·첫 step·N256까지 측정은 끝났지만 C MuJoCo3.12와 물리 응답·자기 RGB 정보가 다르다. 운영 교사·평가 backend와 기본값은 바꾸지 않았다. 학습·실물 검증은 0회다. [summary.json](summary.json), [거부 분포·관문 표](rejection_table.json).

## 물리 동등성

같은 VM에서 C3.12와 MJWarp에 정확히 같은 명령 tape를 넣었다. 1대+작은 청록 상자, 4구간 모두 재생 완료. `unused_efm_v1`로 비활성 EFM 작업 공간만 upstream zero-allocation 경로로 가져와 put_data·첫 step을 통과했다. 이후 위치/속도 유한성·capacity overflow 검사를 통과했다. 마찰·접촉·dt0.00025·noslip10·질량·관성·solver 반복 수는 유지했다. upstream의 tolerance1e-8→1e-6 자동 보정은 원래1e-8로 복원하고 전후를 기록했다.

| 구간 | 몸체 끝점 위치 차이 | 몸체 끝점 각도 차이 | 제안5mm/2° 기준 |
|---|---:|---:|---|
| 전진+정지 | 4.325mm | 0.026° | 통과 |
| 측면+정지 | 7.330mm | 0.909° | 초과 |
| 회전+정지 | 2.958mm | 2.371° | 초과 |
| 집게 전체 trace | 50.887mm | 2.934° | 초과 |

파지 유지3초의 양쪽 집게–상자 접촉은 **C30/30·Warp0/30 표본**이고, 상자 최소 높이는 **70.835mm 대 사실상0mm**였다. C의3초 이동량은0.0306mm다. Warp 이동량0은 바닥에 남은 상자의 정지이며 파지 성공이 아니다. 30은10Hz 표본 수이고 독립30회 성공률이 아니다. 상자 자체의 마지막 위치 차이는14.374mm다. 5mm/2°/2mm는 사용자 원인 탐색용 제안값이며 기존 임무 성공 기준을 완화하지 않았다. 들기12mm는 동결 교사의 기존 평가 기준을 그대로 썼다.

추가 C3.16 대조에서도 같은 파지 실패와 비슷한 무부하 오차가 재현됐다. 첫0.1 SIM초에 각 롤러–바닥 접촉이 C3.12에서는1개, C3.16·Warp에서는4개였다. 따라서 GPU float32만으로 설명할 수 없다. [공식3.13 변경 기록](https://mujoco.readthedocs.io/en/stable/changelog.html#version-3-13-0-september-8-2026)의 Plane–Mesh 재작성은 우선 조사 후보지만, 해당 변경의 인과관계를 bisect로 확정하지 않았다. [대조](evidence/comparison-cpu316.json), [접촉 분포](evidence/contact-distribution.json).

## 처리량과 비용 환산

각 N에서 같은 **4 SIM초 전진1초+정지3초**를 복제했다. 단위는 전체 world의 합계 SIM초/wall초다. 물리 시간은 evaluator 전송/집계와 구분했고, RGB 값에는640×480 자기 카메라1개/world·10Hz·배치 렌더·모든 world readback·동일 OpenCV fisheye가 들어간다. JPEG·교사 판단/탐색·ACT 추론·reset은 제외한다. [전체 시간 분해·cold wall](benchmark.json).

| N | 물리만 SIM초/초 | 물리+RGB·후처리 SIM초/초 | GPU 메모리 물리/RGB MiB | $/SIM시간 물리/RGB | RGB SIM초/$ vs n4 |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.098 | 0.098 | 316/342 | $11.180/$11.231 | 0.04–0.05배 |
| 16 | 0.850 | 0.797 | 316/406 | $1.290/$1.375 | 0.34–0.38배 |
| 64 | 2.497 | 2.161 | 316/662 | $0.439/$0.507 | 0.91–1.03배 |
| 128 | 4.222 | 3.352 | 348/1046 | $0.260/$0.327 | 1.41–1.60배 |
| 256 | 6.402 | 4.601 | 444/1782 | $0.171/$0.238 | 1.94–2.19배 |

메모리는1Hz 표본 최대이며 allocator의 순간 peak가 아니다. n4 기준은 사용자 과거 동시16·wall/SIM2.35–2.66에서 환산한6.015–6.809 SIM초/초와$3.145/h다. L4는 사용자$1.096/h를 썼다. 같은 전체 교사 workload를 새 n4에서 재측정한 결과가 아니므로 비용 배율은 산술 참고다. N256 물리만은2.70–3.05배지만, RGB 포함은1.94–2.19배다. N256 RGB 실행은 물리159.265초·렌더2.394초·readback/NumPy 변환/fisheye60.920초였다.

더구나 **현재 RGB는 정보 동등성 실패**다. [같은 저장 상태의 C(왼쪽)/Warp(오른쪽)](evidence/rgb-matched-state-comparison.jpg)에서 C는 파란 구역 아래 checker를 보여 주지만 Warp는 거의 불투명하게 가린다. `zone_pickup` alpha0.14·그룹0을 그대로 유지했다. 고정 renderer 소스의 부분 투명도 처리 차이와 부합하며, 구역을 숨기거나 지도/색을 바꾸지 않았다. 따라서 현재 RGB 속도를 동등한 관측의2배 가속으로 채택할 수 없다.

## 고정 소스·실행 경계

- 프로젝트 `ugrp-sim-b-1014`, 계정 `changmin5781@gmail.com`, `ugrp-act-l4-gcp2`/서울a/`g2-standard-8`/L4한 장. 첫 프로젝트 API/SSH 접근0. gcp1 사용 금지로 분석·영상 생성도 gcp2 L4에서 했다.
- 교사/장면 동결 `6f057f7e97c1a3aec9e8c398b8d9068e27b25df8`, MJWarp개발 `57b4692f4d3cdf4d27d916b4b8c4759ba36e9148`, MuJoCo3.16.0·Warp1.15.0. C3.12 평가 환경과 분리했다. GPU 릴리스 표기3.16.0을 noslip 미지원 정식 tag와 혼동하지 않는다.
- C3.12/Warp N1은`25bf9995`, C3.16·물리 배치는`737f5a0e`, RGB 배치는`01cd2a9c`다. 후속 변경은 렌더 후변환 동기화·실제 K/D/mount 기록이며 물리/명령 경로를 바꾸지 않았다. full SHA·script/fixture/XML·물리 배열 해시는 summary/각 result에 있다. 코호트가 끝난 뒤 다음 소스를 올렸다.
- simalt2 인계는`d93837eb..17b19ae7`의12커밋이다. 기존 감사3개는 [인덱스](inherited-audits.json)와 simalt2의`.json.zst`에 보존했고, 전체 복원 해시가 일치한다. 기존 Mac 미추적 원본은 그대로 남겼다.
- 실시간 교사/정책/모델 호출 없이 발행 명령 whitelist만 재생했다. 정답은 초기 상태·비교/평가·사후 렌더 전용이다. 계획/탐색 자체를 하지 않았으며 wall 제한은 자원3시간 전용이다. 학습 자격 증명·모델 키·Kaggle 키 전송0.
- 물리만 실행은10Hz 상태 버퍼에서 C로 사후 RGB를 복원했다. 온라인 RGB ring으로 표현하지 않는다. RGB 배치는 기록 전용 world0 마지막100프레임 ring을 항상 저장했고 이번4초 실행은40장씩이다. 학습 카메라/제어 경로는 추가하지 않았다.

## 원본·검토·종료

실제 실행12개·명령 구간21개 모두 완료, HOST_ERROR0·cap_end0·수치 실패0. 별도의 설치 사고(부팅 직후 SSH 거부, python3.12-venv 누락)는 로그에 남겼고 물리 실패와 합산하지 않았다. 작은 장면의 동등성이 실패해 두 로봇+빔으로 확대하지 않았다.

[영상 검토](playback-review.md): 실패2개·C성공1개를 전체2Hz와10Hz 구간으로 직접 보았다. MP4는 모두8MB 이하이며 ffprobe·해시로 검증했다. Mac 물리/렌더/화면 앱 실행0. 비물리 검사12개·구문 검사·git diff --check 통과.

원본 `992/992` 파일 SHA256 PASS. 신규 대형 JSON21개는 zstd 복원 전체 해시 확인 후 압축 표현으로 보존했고 [매핑](evidence/compression-map.json)을 남겼다. Mac 요약48파일·검토23파일 해시 일치, lite archive62,088bytes 전체 SHA PASS. 원본은 **정지한 L4의 영속 디스크**에 있고 전체 외부 백업은 아니다. [원본 매니페스트](evidence/SHA256SUMS), [검증](evidence/raw-verification.json), [회수 검증](evidence/local-transfer-verification.json).

비용 장치 시험의 실제 RUNNING→STOPPING9.019초→TERMINATED55.517초를 확인하고 시작했다([setup-gate](setup-gate.json); 최초 줄은HOST_READY, 뒤에 조정자PASS도 추가됨). 8h STOP·idle20분·별도3h 자원 감시를 유지했다. 작업 뒤 자기 GPU/분석 프로세스를 정리했고 L4는 **TERMINATED** 확인, 3h 감시는 종료했다. 다른 gcp2 CPU VM은 변경하지 않았다.

생성 요청 `2026-10-15T14:28:07.269057+00:00`부터 정지 `2026-10-15T08:26:01.016000-07:00`까지 **3473.747초 = 0.9649h**, VM 정가 추정 **$1.058**. 설치/컴파일/종료 대기를 포함하며 디스크·네트워크·세금·실제 청구/크레딧 잔액은 별도 미확인이다. [최종 호스트](evidence/final-host-status.json).

## 재현과 남은 가능성

소스별 실제 CLI·입력 SHA·압축 복원·새 output 재현 절차는 [reproduce.md](reproduce.md)에 있다. 각 result에는 실제 source/fixture/XML 해시와 원장이 있으며, Mac에서는 물리·렌더를 실행하지 않는다.

남은 것은 C3.12→3.16의 접촉/solver 차이 분리와 부분 투명도 렌더 보존이다. 마찰·접촉·dt·noslip·질량을 낮추거나 바꾸는 우회는 하지 않았다. 두 동등성 관문이 해결된 뒤에만 실제 teacher/평가의 배치 reset·명령 latch·서보·직접 MjData 읽기 분리와 두 로봇+빔/기존 C target 검증을 다시 검토할 수 있다. 현재는 운영 backend 이식을 구현하지 않는다.

참고: [고정 io/EFM](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py), [고정 renderer](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/render.py#L569), [공식 배치/overflow/float32 설명](https://mujoco.readthedocs.io/en/latest/mjwarp/), [사용한 GPU 이미지 계열](https://docs.cloud.google.com/deep-learning-vm/docs/images). 고정 upstream io SHA는 simalt1 설치본과 일치했다. 새 이미지의 정확한 버전은 boot-disk.json에 있다.

조건부 adapter 변경 지점·공수·위험 목록은 [migration-assessment.md](migration-assessment.md)에 분리했다. 현 판정으로 구현에 착수하지 않는다.
