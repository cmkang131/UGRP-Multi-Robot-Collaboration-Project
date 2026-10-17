# mapbuild11 — 긴 경로에서의 지도 위치 보정

**NOT_READY. 이 녹화에서 지도 보정은 XY 누적 오차를 크게 줄였지만 방향·분포 수렴 관문은 남았다.**
실제 MJWarp 미적재 주행6.461m에서 수정 후 AMCL의 끝/최대 XY는 **35.13/88.87mm**, OFF는 **3323.18/3327.91mm**였다. 수정 후에도 방향결합 요구표 이탈17/1642프레임, 분포 수렴0회여서 생산 인계·운반에 채택하지 않는다.

## 같은 녹화의 세 줄 비교

공개 시작 상자 .5m×.5m·북쪽±30°에서 실제 시작을 균일 표본으로 뽑았다(구역 크기·방향 반폭은 조정자 설계). 필터에는 범위만 전달했다. setup RNG2026101710, 필터 RNG2026101700이다. 녹화 중 주행은 **수정 전 `nav2_defaults_v1`의 미자격 제안**으로 진행했고, 새 `nav2_rgb_field_v1`은 **같은 프레임에서 오프라인으로만** 평가했다.

주행 구간38.4–202.5 SIM초,1642프레임. 전체는2026프레임/202.5 SIM초, 전체 이동6.688m(초기 둘러보기 포함)이다. `ROUTE_COMMAND_COMPLETE`는 추정 자세로 두 경유점 명령을 마쳤다는 뜻이며 실제 도착·ACT·LLM·실물 성공 판정이 아니다.

|방식|끝 XY mm|최대 XY mm|XY ATE RMSE mm|끝/최대 yaw °|XY+방향결합 요구표 통과|
|---|---:|---:|---:|---:|---:|
|보정 OFF|3323.18|3327.91|1532.31|52.546/101.886|140/1642|
|AMCL 수정 전|69.49|174.72|96.84|19.606/36.842|1507/1642|
|AMCL 수정 후|35.13|88.87|53.31|18.595/21.620|1625/1642|

[0.5m 간격의 세 오차 곡선](operations/final-gcp5/error-curves.png), [0.5m 구간별 수치](operations/final-gcp5/half-metre-table.csv), [전체 요약](operations/final-gcp5/long-summary.json). OFF에는 시작 SE(2) 정렬 한 번만 허용했고 척도 피팅은 없다. AMCL은 초기 사전 오차까지 포함한 정적 지도 절대 오차다. 정답은 예측 봉인 뒤 평가에만 썼다. R3의 짧은 OFF43.22mm 결과와 이번 6.46m 결과를 같은 코호트로 합치지 않는다.

요구표는 기존 **XY≤200.751mm**, `abs(yaw)+atan2(XY,.84831457-XY)≤21.4233°`를 그대로 썼다. 수정 후 끝 방향결합21.069°는 통과하지만 최대23.649°로 **114.5–122.8 SIM초의17프레임**이 초과했다. 주행 XY 초과는0이다. 수정 전은135프레임, OFF는1502프레임이 결합 요구표 밖이다. 초기 둘러보기까지 포함한 수정 후 최대 XY는266.58mm이며, 시작4프레임은 AMCL 후보가 없다. 주행 숫자로 초기 불확실성을 숨기지 않는다.

수정 전 수렴은 전체10측정 갱신(주행6), 오수렴0이고 수정 후는 **수렴0·오수렴0**이다. 한 녹화의 갱신 횟수이며 독립 시행 성공률이 아니다. 위치 오차가 작은 미수렴 후보를 수렴 성공으로 세지 않았다. 자기 벽 관측은 계속 쌓았지만 자기 서브맵은 위치 보정 참조로 쓰지 않았다. [인과적 자기 벽 지도 그림](operations/final-gcp5/own-map-overlay.png)은 미수렴 제안도 포함하며, 지도 coverage·잘못된 free·벽 정확도·전체 지도 완성을 검증한 결과가 아니다.

## 수렴20/20→5/20 원인

동일 R3 MC20 사전·입자 RNG와 과거 예측을 비교해 candidate/ready 불일치0을 확인했다. **수렴이 사라진 같은168갱신은 방향결합 초과168, XY 초과4, ESS 초과0**이다. 이 부분집합의 결합 P95 중앙17.659→25.423°, ESS488.45→497.20/501, XY P95 109.49→154.56mm였다. 수정 후 가중치가 더 평평하고 공분산이 커졌다. ESS 붕괴가 직접 사유는 아니다. 경계/센서 범위를 함께 고친 결합 후보이므로 두 수정의 독립 기여는 미확인이다. [상세 한 줄 표·근거](convergence.md). 문턱·σ·α·입자 수를 변경하지 않았다.

## would_stop와 이동량 진단

초기 등록 **5.8초**, 주행 **38.4초**에 처음 `would_stop`을 기록했고 총1539이벤트를 남겼다. DEV에서 위치 불확실 정지로 끊지 않고 끝까지 녹화했다. 실제 낙하·전복 같은 물리 실패를 보인 실행은 아니며, 새 방식의 실제 제어 성공으로 해석하지 않는다.

주행 LK 측정1378/1642, 미측정264(그중 rigid consensus251)였다. 미측정 때의 명령 예측264프레임에서 yaw 증분 잔차합은 **−49.462°**, 측정된1378프레임은 합 **−.604°**, 준비 구간은−2.480°였다. 전체 합−52.546°는 OFF 끝 yaw 오차52.546°와 맞는다. 이는 **평가용 증분 잔차 분해**이며 XY3.32m의 선형 인과 기여나 정답으로 맞춘 이동 모델이 아니다. native 주행 펄스의 명령 예측 자격과 회전 중 LK 미측정이 다음 진단 대상이다. 이 자료로 새 상수나 이동 모델을 맞추지 않았다. [분해](operations/final-gcp5/yaw-increment-decomposition.json).

실제 주행 절대 회전합은2250.66°(작은 되돌림 포함), 순 yaw 변화는−39.08°다. 따라서 이 자료를 “깔끔한180°회전 한 번”으로 표현하지 않는다. 0–202.5초 전체2Hz·192.5–202.5초10Hz·112.8–123.7초10Hz를 직접 파일로 검토했다. r1이 벽을 따라 전진하고 모서리에서 돌아 복귀하며 r2는 정지해 있다. 짧은 방향 되돌림은2Hz만으로 판단할 수 없었다. [검토 기록](playback-review.md).

## 변경·검증·보존

- 기본 off `--dev-light`는 명시 long 진단에서만 위치 분포 정지를 기록 후 통과한다. 생산 수용은 계속false다. 기존 MCL/필터 상수·물리·카메라·근거리 교사는 바꾸지 않았다. 관측은 자기 RGB·발행 명령·고정 보정·허용 정적 지도·공개 시작 범위뿐이다.
- 승인1라운드/최대2녹화를 모두 사용했다. 첫 시도는 sparse 복사에서 기존 카메라 모듈을 빠뜨려 첫 프레임 전에 HOST_ERROR(저장0프레임)였다. 같은 소스의 정확한 의존 파일을 복원한 녹화2만 주행 데이터를 냈다. 실패를 제외한 성공률로 보고하지 않는다.
- MCL·수치 평가 소스 `cfdcd88450b8bef8730dfdec1fa8e3baa67ede7f`, 별도 그림/영상 소스 `22293978afb486e7d188d4d2d0f57e6eec17625a`. 예측·봉인·오차·요약4파일은 그림 작성 전후 SHA가 같다. 자기 지도 파일도 봉인 해시와 일치했다. 실제 온라인 수정 전 제안과 오프라인 재생2026프레임도 존재 불일치0/최대 차0이다.
- 원본4078파일(RGB4052)·예측 입력11파일·고정 소스16772파일을 검증했고 불일치0이었다. 별도 오차 재계산2026프레임 차0. [무결성](operations/final-gcp5/integrity.json), [압축·온라인 재생 일치](operations/final-gcp5/closure-integrity.json).
- 실행 후 스택 검사에서 기준표 `on`과 실제 공유 기본값 `path_tangent_v1`의 표기 차이를 발견했다. `c8dc1e65:harness/path_heading_policy.py:9`의 DEFAULT를 근거로 **그 이름만** 대응시켰다(`8a6a4917f176729abe6081b088ee21f6296a13bb`). off/다른 모드는 계속 거부한다. 사용자 결정·제어·허용 오차를 바꾸지 않았다. [이전 차단](operations/final-gcp5/runtime-stack-before-alias.json), [수정 후 검사](operations/final-gcp5/runtime-stack-heading-alias.json). 선언+XML 검사와 실제 입력/물리 감사 범위는 구분한다.
- 그림 의존성이 물리·기존 분석 환경에 없어 그래프 단계가 두 번 실패했고, 물리 종료 뒤 기존 분석 환경에 matplotlib3.11.2를 추가했다. 필터 재실행 없이 그림을 완성했고 수치는 변하지 않았다. 기존 물리 환경은 변경하지 않았다. [환경](operations/final-gcp5/environment.json), [후처리 완료](operations/final-gcp5/postprocess-exit.json).
- Mac 비물리6개1.35초 + 스택 검사4개(활성 heading/disabled 반례 포함).14초 통과. 전체 CI는 별도이며 최종 CI 통과로 보고하지 않는다. 새 물리·학습·모델 호출·실제 ROS 노드·실물 인수는 추가하지 않았다.
- 큰 JSON15개는 zstd 무손실 압축 후 해제 SHA와 압축 SHA를 확인했다. 기록 원본은 gcp5 영속 디스크에 남아 있다. 녹화2는 대표 진단 증거 보존을 위해 dev→milestone으로 선택했고 처음 메타 바이트를 `RUN_META.initial.json`에 보존했다. 지도/학생 성공이라는 뜻은 아니다. [메타 이력](operations/final-gcp5/metadata-evolution.json).
- Mac 회수48파일 SHA 불일치0. CPU/GPU noslip0, 입력 감사 invisible_measurements0/held_world_reads0. gcp2 CPU·gcp1·gcp3 새 시작0, 모델 키 전송0, Mac sim/render/화면 앱0, Drive0. 실제 클라우드 청구액은 확인 안 됨이다.
- 자기 lease 해제·타 계산/GPU 프로세스0 확인 후 **gcp5 TERMINATED**, 마지막 정지 **2026-10-17 15:12:04 KST**. [정지 영수증](operations/gcp5-stopped.json), [직전 상태](operations/gcp5-prestop.json).

[전체 funnel](rejection_table.json), [차단된 다음 큐](next-queue.json), [재현·원본·라이선스](API.md), [대표4배속 영상](representative-4x.mp4) (736907bytes, SHA256 `7d35f222e635167648a9dd7cb0c60d7302875fe42c82cbfb3f4aa5ab24ef5b5f`). 원래2.30MB 검토 영상과 전체 프레임 띠는 Mac 기본 체크아웃 `outputs/e2e18-admin/playback/mapbuild11-recording2/`에 있고 원본은 gcp5에 남는다.

## 참고 자료

- [Nav2 likelihood_field 원본](https://github.com/ros-navigation/navigation2/blob/main/nav2_amcl/src/sensors/laser/likelihood_field_model.cpp): 기존 가산 likelihood·정수 stride·혼합항을 유지한다. 기존 [LGPL-2.1-or-later 고지](../../harness/mapbuild_amcl_vendor/NOTICE.md)와 vendor는 변경하지 않았다.
- [Nav2 AMCL 설정](https://docs.nav2.org/rolling/configuration_and_development/configuration_guide/others/configuring_amcl/), [이전 측정 감사](../2026-10-17-mapbuild10/followup-results.md): σ=.2·입자500–2000·고정 요구표의 출처와 이전 실패 범위. 이번 작업은 새 정합기를 만들지 않았다.
- [Matplotlib 설치·비대화형 출력](https://matplotlib.org/stable/install/index.html): 그림 생성 의존성에만 사용했다.
