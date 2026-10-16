# warp8f — 정적 지도 CSM API 오프라인 연결 완료 / NOT_READY

`nocap-ack nocpu-ack nativecontact-ack ownership-ack latest-ack`.
새 기본 off `release_reloc_selfmap_v1(lk)` + `mapbuild_static_csm_v1` 어댑터로
저장된 native release A-S1 **14세계·28로봇·418뷰**를 점검했다.
mapbuild7 `0ace43f25d3121e8f466c4ecefc9789f52958d41`의 모듈은 byte 그대로 사용했다.
**전역 위치 채택 0/28, 요구 오차 통과 0/14세계**다. 새 release A40/B40 대기열은 만들거나
제출하지 않았다. 기존 빔40/40·옛 release0/14·noslip10·CPU 결과와 합산하지 않는다.

|로봇별 정합 funnel|전: 기존 첫 3-pan 종료|후: 전체 저장 뷰 종료|
|---|---:|---:|
|시도|28|28|
|채택|0|0|
|모호하여 None (`ambiguous_modes`)|4|17|
|전역 SE2 관측 부족|20|11|
|벽 선분 없음 / 가까운 점 부족|3 / 1|0 / 0|
|전체 거부(None)|28|28|
|오채택 / 인계 요구 오차 통과|0 / 0|0 / 0|

전후 모두 채택된 지도 위치가 없어 **채택 위치 XY/yaw 오차는 null(미정합)**이다.
거부된 최선 후보의 오차와 첫 평가 SE2에 맞춘 상대 drift는 평가 전용 칸에 따로 기록했다.
이를 채택·성공으로 세지 않고, 정답 시작 위치를 추정기에 대입하지 않았다.
[28로봇 전후 오차표](selfmap-csm-r1-error-table.md), [기계 판독 오차표](selfmap-csm-r1-error-table.json),
[funnel·거부표](selfmap-csm-r1-rejection_table.json), [실행 전체 요약](warp8f-summary.json).
요구값은 mapbuild6 `requirements.json`을 byte 그대로 고정했다:
XY ≤200.751mm와 yaw+atan2(XY,848.315mm−XY) ≤21.423deg를 함께 요구한다.
이 역사적 교사 envelope를 학생·native 물리 성공 범위로 승계하지 않는다.
자리60mm·문 통과·실제 적재/운반 구간은 이번 sparse 입력으로 검증하지 않았다.

새 경로의 벽 검출은190/418뷰·7,653열로 이전 입력 감사와 일치했다.
바닥 특징417뷰·77,571개와 구역 색 보조 성분은 동일 JPEG의 이전 입력 감사값을 출처와 함께
검출표에 연결했다(바닥 검출기 재실행0). 이는 전역 정합의 추가 증거가 아니다.
LK는 bootstrap28·servo 변경 unknown390·실측0이다. 발행 명령의 상대 변화만으로 자세를
전파하며, 카메라 원점과 벽 선분을 같은 자기 좌표계로 합성해 API에 전달했다.
[검출표](selfmap-csm-r1-detection-table.json), [출처·입력 경계](selfmap-csm-provenance.json),
[2,091파일 owner SHA 목록](selfmap-csm-owner-manifest.json).
옛 floor-line Hough·global_consensus 호출0, spawn 대체0, 물리·TOP·모델0이다.

입력은 이전 두 native 렌더 간 JPEG418/418 일치가 확인된 파일을 그대로 재사용했다.
이번에는 렌더·물리를 새로 실행하지 않았다. sparse capture는 기존 자기 서보 명령 후
0.8/1초 wait 계약으로 열린 카메라의0.25초 정착 구간을 만족하는 뷰로 처리했다.
측정 관절이나 평가 FK는 입력으로 사용하지 않았다.
**실제 적재 FK 자격·실제 운반 경로·LK/RBPF 선택은 mapbuild 소유자 관문에서 아직 ready가 아니다.**
이 어댑터는 오프라인 부품 연결이며 release 물리 실행기 교체 연결이나 실제 임무 성공이 아니다.

실행 소스 `a40eb399481e2996899f84a7bf65ca7228902c1b`, 감독자 `951d4c669`,
독립 재계수 `d8c9ec262`(압축 호환 검증 `bba5745d3`)를 커밋한 뒤 사용했다.
첫 운영 감독자 인용 SyntaxError는 추정기 시작 전 발생했고 원격 로그로 보존했다.
커밋된 감독자로 고친 뒤 오프라인 한 라운드가 predict/score 종료코드0/0으로 끝났다.
[명령](selfmap-csm-r1-command.json), [완료 receipt](selfmap-csm-r1-receipt.json).
동일 결함을 고쳐 세 번 반복한 실험이 아니며 물리 라운드는0이다.

원본: `gcp3:/home/ugrp/ugrp-sim/runs/warp8/selfmap-csm-r1`.
독립 원본 재계수56/56 일치, prediction141파일·입력JPEG418·owner2,091파일 SHA 일치,
기존 RUN_META 보정54개+summary 주석2개 SHA56/56 일치다. 원래 라벨·scene의noslip10 표기는
기존 보정 파일에서 실제native0와 구분한다. 정식 admission 부재로
`gate_eligible=false`인 과거 원본을 소급 승인하지 않는다.
[독립 재계수](selfmap-csm-r1-independent-recount.json), [147파일 SHA 목록](selfmap-csm-r1-artifact-integrity.json),
[재검증](selfmap-csm-r1-integrity-verification.json).
큰 JSON14개를 zstd 후 해제SHA 검증해 동일 원본 바이트를 무손실 보존했다
([압축 manifest](selfmap-csm-r1-compression-manifest.json)).
Mac에는 요약·표·SHA·명령/receipt12개만 회수하고 SHA12/12를 확인했다
([회수](selfmap-csm-r1-transfer.json)). 원본 JPEG/상태/궤적 전체는 회수하지 않았다.

실패000/001의 기존 자기 카메라 몽타주4개64프레임(17.9–37.4 world SIM초)을 이번에 직접 봤다.
pan에 따라 벽–바닥 경계·문·질감과 파트너 가림이 보이며, sparse 영상만으로 빠른 진동이나
운반 LK 성능을 주장하지 않는다. 기존 native 대표 성공·실패 영상 각1개의 SHA/ffprobe도 재확인했다.
[직접 검토·영상 기록](warp8f-playback-review.json). 새 GUI 호출0이다.

비물리 단위시험 **5 passed**, 새 시험의 CI shard1회 포함·Python 구문·diff 검사를 확인했다.
전체 CI·물리 성공·release 관문 통과는 별도다. 오프라인 요구 관문 미통과로 새 A40/B40 대기열은 없으며,
향후 제출 전 stackaudit PR#569 `check_current_stack.py`와 `dialogue_language` 검사를 요구한다.
API의 관측 부족/모호성 원본을 mapbuild 소유자에게 전달하고 이 작업에서 상수를 조정하지 않는다.

자기 lease 제거 뒤 타lease0·ugrp 작업PID0·GPU client0·idle20 ACTIVE를 확인하고 VM을 정지했다.
**gcp3 TERMINATED·상한 필드 없음**을 조회했다([정지 전](warp8f-prestop.json), [정지 확인](warp8f-host-stop.json)).
CPU VM 시작0·다른 VM 변경0·키 전송0·Drive 사용0이다.

아래는 warp8e 및 이전 실행의 당시 기록이다.

# warp8e — 자기 지도 입력 14세계 오프라인 점검 완료 / NOT_READY

`nocap-ack nocpu-ack nativecontact-ack ownership-ack latest-ack`.
내려놓기 위치 다시 잡기를 새 자기 지도 경로로 바꾸기 위한 **입력 점검**을 마쳤다.
정적 지도 전역 정합·운반 자세 FK API는 mapbuild 소유자에게 요청했고 아직 연결되지 않았다.
새 경로 위치 오차·release A40/B40은 **미측정·미제출**이다. 기존 native 빔40/40과
옛 위치 추정 경로의 native release A-S1 0/14는 별도 보존하며 합산하지 않는다.
실패 분포는 `active_observation_exhausted` 11, `axis_correction_outside_bounded_domain` 3이다.
옛 Hough 바닥 선/정합 상수를 수정하거나 렌더 차이 진단을 추가하지 않았다.

|gcp3 저장 native 상태 14세계 / 418 자기 뷰|측정|
|---|---:|
|새 MJWarp 렌더 JPEG와 원래 소비 JPEG SHA 일치|418/418|
|집게 열린 카메라 명령 FK 자격|418/418|
|벽–바닥 경계 가상 스캔이 있는 뷰|190/418|
|반환 벽 열 / 전체 열|7,653/40,128|
|바닥 특징점이 있는 뷰 / 특징점 합|417/418 / 77,571|
|LK 구간|bootstrap 28, servo 변경 unknown 390, 측정 0|
|새 지도 보정·위치 오차|미측정(API 대기)|

이는 sparse 둘러보기 뷰의 검출 수다. 특징점 존재를 운반 LK·정합 성공으로 해석하지 않는다.
구역 표시는 기존 RGB 색 서명·성분 크기 조건만 재사용한 보조 성분 수이며 깊이·구역 정체성
자격을 얻은 검출기가 아니다. 바닥 선/Hough를 실행하거나 지도 증거로 쓰지 않았다.
[28로봇 검출표](selfmap-open-r1-detection-table.md), [오차표](selfmap-open-r1-error-table.json),
[순차 funnel/거부표](selfmap-open-r1-rejection_table.json), [요약](selfmap-open-r1-summary.json).
실제 새 위치 오차가 없는 칸은 null/미측정이며 평가 정답으로 초기화하지 않았다.

기본 off `release_reloc_selfmap_v1`의 `lk`/`rbpf` 관측 어댑터를 추가했다.
**기존 release 물리 실행기에 교체 연결한 상태는 아니다.** 정합 API가 없으면 수정을 수락하지 않는다.
LK를 먼저 점검했고 RBPF는 선택지만 있으며 실행·채택하지 않았다. 관련 비물리 **2 passed**다.
운반 중 grip<=1600의 FK 거부를 우회하지 않고 명령 예측/unknown을 구분한다.
mapbuild6에서 mapbuild7로 이어지는 담당자에게 loaded FK 자격과 정적 지도 전역 정합을 요청했다.

물리·제어 0, TOP 렌더/입력 0, 모델 호출 0이다. 렌더 소스와 관측 소스를 별도 프로세스로 분리했고
추정 프로세스는 eval-only 파일을 읽지 않았다. 소스 `5461ba0d82163319251743fe8e4d9e2333374965`,
mapbuild `c7477b1f64910f498b52e1697488c28b2c4569e1` 및 그 경로가 쓰는 renderer597
vision 보충 파일을 byte 그대로 사용했다. [2,083파일 출처·SHA](selfmap-owner-manifest.json).
관측 원본은 `gcp3:/home/ugrp/ugrp-sim/runs/warp8/selfmap-open-r1`이다.
[명령](selfmap-open-r1-command.json), [완료 receipt](selfmap-open-r1-receipt.json),
[원격 449파일 재해시·JSON3개 압축/해제SHA 검증](selfmap-open-r1-integrity.json),
[Mac 요약·표·몽타주10개 SHA 검증](selfmap-open-r1-transfer.json).

기존 native 빔/release 원본의 seal 인계도 완료했다. 38,593파일 재해시 일치,
기존 선언38,525개 missing0/mismatch0, 큰 JSON61개 압축/해제SHA 일치다.
[native seal](native-seal-integrity-warp8e.json). 이미 만든 RUN_META 보정54개+summary 주석2개는
SHA56/56을 확인했고 중복 생성·원본 덮어쓰기0이다([검증](metadata-corrections-verification-warp8e.json)).
옛 PR/branch/batch·noslip10 표시는 보정 파일에서 실제 native0와 구분하고,
`gate_eligible=false`의 정식 admission 부재 사유를 보존한다.

실패000/001 새 자기 뷰는 각 r1/r2 16장, 합64장을 직접 봤다(17.9–37.4 world SIM초).
기존 영상의 처음0–8.5/끝36–40.5/최근40–40.9 task SIM초 프레임 띠도 확인했다.
두 로봇은 반대 끝을 유지하고 pan으로 벽/바닥을 반복해 본다. 이 관찰을 낙하·새 정합 실패로 확대하지 않는다.
기존 대표 native 성공·실패 영상은 Mac에서 각각112,368/159,229bytes, SHA·ffprobe 재확인했다.
[이번 직접 검토 범위](warp8e-playback-review.json). GUI를 열지 않았다.

stackaudit 점검기가 생겨 [다음 release 대기열](selfmap-release-next-queue.json)에 연결했다.
아직 커밋 전인 소유자 파일의 정확한 SHA를 기록해 읽기 전용 실행했고,
5항목 current/26항목 unknown으로 **blocked**다([점검 결과](selfmap-next-current-stack-check.json)).
미제출 후보의 실제 적용 스택 근거를 채워 재검사하기 전에는 제출하지 않는다.

gcp3를 상한 인자 없이 시작했고 idle20·budget-stop ACTIVE를 확인했다.
종료 lease/PID를 확인해 옛 release lease를 정리했다. 회수 뒤 타 lease/작업PID/GPU client가
모두 없는 것을 확인하고 정지했으며 **TERMINATED**를 조회했다.
[정지 전 확인](warp8e-prestop.json), [정지 확인](warp8e-host-stop.json).
CPU VM 시작0·다른 VM 변경0·키 전송0·Drive 사용0이다. API 대기 중 VM을 켜 두지 않는다.

아래는 warp8d 및 이전 실행의 당시 기록이다.

# warp8d — native contact 관문 인수 (빔40/40·release A-S1 0/14)

`nocap-ack nocpu-ack nativecontact-ack cap-ack ownership-ack`.
사용자 2026-10-16 23:1x 결정에 따라 `warp_native_contact_v1`로 빔40 → release A40 → B40을 새로 잰다.
warpfit PR #562 / `df5a1f86aad420f2fab2c10e3ee77cdb5ec11807`의
`sim/warp_native_contact.py`를 byte 그대로 가져왔으며 SHA-256은
`a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a`다.
NoSlip0·elliptic·implicitfast·impratio5·Newton/LS80/50을 전 세계에서 검사한다.
기존 legacy-plane/dense capacity/C3.16 호환은 유지한다. 관련 비물리33PASS.

noslip10 빔R2의40/40은 역사적 별도 결과다. release A-S1은 조정자 SIGINT로
`SUPERVISOR_STOP / not_a_defect_profile_switch`이며 미완료다. 정확한 프로세스 exit code는
회수되지 않아 추정하지 않는다. 새 관문과 noslip10·CPU beampair7/release25·다른 호스트 결과는 합산하지 않는다.
원본은 gcp3에서 보존한다.

gcp3는 상한 없이 시작했고 live scheduling에서 `maxRunDuration`과
`instanceTerminationAction`이 없음을 확인했다. 자체 wall 시한도 없다. idle20·budget-stop 유지.
분석은 gcp3 CPU만 사용하며 CPU VM 시작0. 새 모델키·에이전트 자격증명 전송0.
[현재 실행 계획](native-gate-plan.json), [호스트 검증](native-host-start.json), [프로필 출처](native-preflight.json).

새 XML 참조80개를 gcp3 CPU에서 C3.12로 재컴파일했고 기존 참조의 actuator/material/geometry
배열 전수 일치를 확인했다. 빔40을14:25:57Z에 제출했다(driver3149/child3151, source3170d909).
[현재 대기열](native-gate-queue.json), [제출 근거](beam40-native-r1-submit.json). 준비 중 상대 asset 경로 오류1회와 camera housing 표시그룹 차이2회는
물리·교사 관문 실행이 아니며 원본/실패 산출물을 보존했다. 표시그룹의 근거는
`sim/multi_masterpi_production.py:930-933`의 로봇별 camera housing 숨김이다.
성공 조건·제어·접촉 상수는 추가하지 않았다.

warp8d가 앱 재시작 뒤 기존 PID3149/3151을 인수했다. 중복 제출0이며
실제 scheduling 상한 두 필드가 비어 있고 idle20은 ACTIVE임을 재확인했다.
[인수 원본 상태](warp8d-resume.json). SSH 별칭의 사라진 로컬 proxy 경로는
설정을 바꾸지 않고 명시적 gcloud 조회 IP·기존 strict host key로 접속했다.
첫30SIM 속도는 완료 뒤 noslip10 기준5.60/8.72와 나란히 기록한다.

첫30SIM: **1.055239** = 1266.287wall/(30×40),
배치 wall/SIM 42.20957. noslip10 빔R2 5.6024 및 release A-S1
누적 prefix 8.72(첫30 미완료)와 별도다. 조정자 환산 차단6.0 미만이며
전체 관문 통과 주장은 하지 않는다. 후속prefix 완료8건은 원장 재계수8/8,
입력감사40건0/0은 완료8 전체와 진행32 prefix 범위다.
[원본 속도·재계수](beam40-native-r1-first30-review.json).
완료 원장의 자동 zstd 압축을 감시기가 읽지 않아 생긴 누락 표시를 바로잡았다.
원장·시뮬레이션 소스는 불변이며 과거 감시 사본도 보존했다.

## native 빔 종료·release 인계

빔40은 **40/40 성공·cap_end0·HOST_ERROR0**이다. [재계수](beam40-native-r1-summary.json),
[전체 감사·26,040파일 SHA](beam40-native-r1-terminal-proof.json),
[거부 사유·funnel](beam40-native-r1-rejection_table.json). 전체 배치52.7SIM/loop1911.026s의
환산0.906559와 실제 작업 처리량1.298693은 구분한다. setup264.989s는 별도다.
대표 known seed8318706의81개2Hz/100개10Hz 프레임쌍을 모두 검토했고
398개 native/evaluator qpos 비트일치·마지막 평가1행 보충을 확인했다.
112,368바이트/3배속 영상은 Mac playback에 회수·SHA·ffprobe를 확인했다.
[검토 타임라인](beam40-native-r1-playback-review.json), [회수](beam40-native-r1-playback-v2-transfer.json).
이 빔 배치에 실패는0이므로 실패 영상 대상은 없다. 초기 파생본도 보존한다.

[빔 인수](beam40-native-r1-admission.json) 뒤 release A-S1 native14세계를15:07:27Z에
제출했다(driver17837/child17839, 같은 고정 소스3170d909).
[제출](releaseA-s1-native-r1-submit.json), [실행 큐](native-gate-queue.json).
release A 나머지26·B40은 아직 미제출이며 전체 데이터 수용은 NOT_READY다.

release A-S1 첫30SIM은 **1.582445** = 664.627wall/(30×14), 배치22.15423이다.
[비교 표](native-first30-comparison.json), [원본 측정](releaseA-s1-native-r1-first30-speed.json).
14세계 모두 진행 중이며 최종 release 성공·입력감사는 아직 판정하지 않았다.

## native release A-S1 실패 — 후속 제출 보류

**0/14 성공·cap_end0·HOST_ERROR0**, 종료코드0이다.
[원장 재계수](releaseA-s1-native-r1-summary.json),
[12,485파일 SHA·제어구간 감사14건0/0](releaseA-s1-native-r1-terminal-proof.json).
특권 장면준비 prefix는 제어 입력 감사 범위에서 제외한다.
종료 사유는 active_observation_exhausted11·axis_correction_outside_bounded_domain3이다.
거부 원장 최빈 axis_pair_unobserved25회는 고유후보 수가 아니다.
[물체·틈 단위 원문을 보존한 분포](releaseA-s1-native-r1-failure-distribution.json).

seed110633/88639 실패2건 각각 전체2Hz82장·마지막10Hz100쌍을 모두 검토했다.
카메라는 실제로 방향을 바꾸지만 추가 관측 뒤 재집기/배송으로 이어지지 않았다.
[타임라인과 한계](releaseA-s1-native-r1-playback-review.json).
대표 영상2개(각8MB 이하)와 로봇별6시각 native 프레임을 Mac 회수·SHA·ffprobe 검증했다.
각 마지막 개요1장은 상태가 없어 빈칸으로 표시하며 자기 RGB는 원본 그대로다.

같은 저장 qpos와 같은 fisheye/no_mip/JPEG82·동결 인식기를 비교했다.
world000 native 32뷰의 특징 수는 원본과 모두 일치하지만 양쪽 ambiguous,
C3.12 RGB에서는 양쪽 global_consensus다. 물리 재실행·교사 제어 변경0의
렌더 입력 분리 진단이며 CPU release 성공으로 대체하지 않는다.
world001은 native의 다른 지도 합의 뒤 축 보정 도메인 거부를 추가 조사한다.
후속 A26/B40 미제출, 새 관문 전체 NOT_READY다.

아래는 noslip10 당시 기록이다. 그 안의8h 복원·CPU VM 분석 지시는 최신 사용자 지시로 폐기됐다.

---

# warp8 — gcp3 빔 짝·release MJWarp 관문 (빔 R2 40/40, release A-S1 진행)

warp6와 같은 `codex/warp6`, PR #557 DRAFT에서 이어간다. gcp2 R3의 CUDA700은
gcp3 단독·MPS off·원래 graph 25.3 SIM초에서 **단독 환경에서 미재현**이었다.
공유 GPU/MPS 다중 client와 양립하지만 원인을 확정하지 않는다.
새 CUDA700 발생 시 해당 시드만 memcheck로 재현하고 같은 결함 3라운드면 중단한다.

빔40세계 한 배치, release A40·B40을 계획한다. release A40의 단일 배치 참조 초기화는 `canonical model free-root names differ`로
거부됐다. 서로 다른 모델 topology를 유지해 A/B 각각 S1 14·S3 13·S6 13으로
분리한다. 각 시나리오의 A/B plan은 바이트가 아닌 JSON 값으로 전수 동일함을 확인했고
참조는 실제 XML SHA로 엄격하게 대조한다. 메모리 부족은 세계 수를 줄여 실측을 기록한다.
판정 속도 = 배치 wall / (배치 SIM초 × 세계 수)다. 완료 세계의 padding도 이 물리 처리량 분모에 포함한다.
완료 시각을 반영한 실제 작업 처리량은 별도로 기록하며 판정에 섞지 않는다.
기존 >6 차단을 실행당 환산값에 적용하는 것은 **조정자 결정, 사용자 미확인**이다.
첫30SIM은 본 실행에서 측정하며 setup/compile 비용은 따로 적는다.
물리·NoSlip·시간 간격·성공식·교사 제어를 바꾸지 않는다.

새 후보는 placement_graspable_filter_v1 ON, weld OFF, held_world_reads=0,
학습RGB OFF, 모델호출0, 기존 계산량 예산 ON이다. 실패10SIM/10Hz 디스크 ring을
유지하고 cap_end·HOST_ERROR를 분리한다. CPU beampair7/release25·다른 호스트와 합산하지 않는다.
입력은 warp6 준비본의 알려진 실패 시드 우선 순서를 유지한다.

호스트는 gcp3 / ugrp-sim-c-1016 / ugrp-act-l4-gcp3 / L4 단독이다.
사용자 결정에 따라 VM·드라이버 wall 상한을 없애고 유휴20분·budget-stop을 유지한다. 작업 종료 후 타작업 부재를 확인해 정지한다.
gcp2 L4·gcp1을 건드리지 않는다. VM에 모델키·에이전트 자격증명은 보내지 않는다.
분석은 원본이 있는 gcp3 CPU에서만 한다. ugrp-sim-gcp2를 시작하지 않는다. Mac 회수는 요약·몽타주·실패 프레임과
8MB 이하 대표 성공1·실패1 영상이며 GUI를 열지 않는다.

원래 빔 관문 소스는 `f75e3442957e8e00c4ed894056b3e06ee32399f0`로 고정했다.
그 뒤 완료 세계 padding을 판정 분모에서 빼려던 기록 변경은 사용자 지정 식과 달라
채택하지 않았다. 후속 실제 실행은 지정 식을 명시한 소스35e94d5d 이후를 쓴다.
진행 중 빔 소스와 원래 기록은 유지하고, 원본으로 물리 처리량과 실제 작업 처리량을
각각 다시 센다. 제어·물리는 불변이며 관련 비물리11PASS다.

## warp8b 재개 지시 — 현행 운영 규칙

`nocap-ack nocpu-ack ownership-ack cap-ack`. 아래 과거 기록의 "8h 유지"·자체 정리 시한·gcp2 CPU 분석은 잘못 적용한 운영이며 후속 지시로 대체됐다. 사용자 "상한 좀 없애라고"가 우선한다. gcp2 CPU VM을 분석 때문에 다시 켜지 않는다.

13:48:34Z 제출된 release A-S1 14세계(driver1738/child1740)를 인수했고 중복 제출하지 않았다. VM 상한28800초/STOP과 기존 드라이버21:14Z 시한이 실제로 남아 있음을 조회했다. A-S1 종료 경계에서 gcp3 정지→상한 두 필드 clear→비어 있음 확인→상한 인자 없이 시작하며 다음 그룹으로 간다. 21:00Z까지 완료 전망이 아니면 그 전에 안전한 경계를 만든다. 신규 드라이버는 wall 시한을 읽거나 SIGINT하지 않으며, 비물리 가짜 시계 시험1PASS로 확인했다. 기존 작업 SIM 상한·물리·제어는 그대로다. VM 상한 제거 완료는 실제 경계에서 확인한 뒤 별도로 기록한다.

## R1 관문 중단과 R2 후보

`beam40-r1`은 control225/+22.5SIM까지 정상 저장 뒤 step226에서 world008/seed8318706의
NVMAX bit128로 중단됐다. 완료 성공1(world028, task17.4SIM), cap_end0, 미완료 HOST_ERROR39다.
물리 실패0이라는 뜻이 아니라39건의 물리 결과를 모른다는 뜻이다. CUDA700은 미재현이다.
첫30SIM은 미완료라 속도 관문 통과로 보고하지 않는다. [원본 거부표](beam-r1-rejection_table.json).

실제 초기110→할당128, 마지막 활성156, 총 nv222다. 기본off `full_active_dof_workspace_v1`로
공식 기본 방식인 정확한 전체 nv를 할당하는 후보를 만들었다([근거](references.md)). NoSlip10,
dt, 접촉·마찰·m.opt solver 설정과 행동 경로는 유지한다. upstream compact 정규화의 pad/ctol은
할당 크기에 따라 바뀌므로 기록하며 바이트 동등성을 주장하지 않는다. 관련 비물리30PASS다.
R2는 새 실패seed8318706을 맨 앞에 놓고 원래 canonical XML과40건의 참조를 재사용한다.
R1과 R2는 합산하지 않는다. R2는08:38:49UTC 제출했고 아직 완료되지 않았다. release는 미제출이다. R2 고정 소스는 `175281c8922453465f8bf32707e22988e78b8812`다.

성공1개·HOST_ERROR1개의 원본 재계수와 대표 영상을 회수했다. full2Hz의 초기0.5SIM 동기화 오류는
native NPZ로 고쳐 중복174/221행 qpos가 비트 일치함을 확인했다. 수정본 전체2Hz36/46장과
마지막10SIM/10Hz 각100장을 전부 봤다. [대표 영상·검증](representative-native-sync.json),
[영상 검토](playback-review.md). 원래 파생본은 보존하고 수정본을 최종 대표 영상으로 쓴다.

R2 제출 전 실제 VM scheduling에서8h 필드가 제거된 것을 확인했다. warp8의 명시적8h 유지 지시에 따라
타 lease/GPU client 부재 확인 후 gcp3만 정지했고, maxRunDuration28800/STOP을 복원·조회했다.
재시작으로 VM 상한 기준 시각이 바뀌어도 현재 빔 세션의 기존 정리 시한14:05UTC는 연장하지 않는다.
빔이 정상 완주하면 VM 정지·원본 검증 후 release를 별도 유한 세션으로 진행한다.
시간·budget-stop이 실제 발동하면 새 실행을 내지 않는다. 각 세션의8h STOP·idle20·budget-stop을 유지한다.
[설정 복원 기록](scheduling-restored.json). gcp2는 변경하지 않았다.

R1의별도재계수는실제`claude-haiku-4-5-20251001`이생성한독립판정코드를gcp2 CPU에서실행해확인했다.
작업자가상태명complete·누락감사필드·SHA메타타입만스키마에맞췄으며물리계산은바꾸지않았다.
결과complete1/HOST_ERROR39,175평가행·연속hold3.0000000000000036초·교사2/2,
원본과불일치0·오류0·입력감사0값40건(전체1/prefix39)으로기존계수와같다.
[R1 Haiku코드실행결과](R1-haiku-counter-result.json), [코드/보정근거](R1-haiku-counter-provenance.json).
모델의문장응답은원본증거로쓰지않았고,잘못된상태분류/소스불일치지적을거부했다.

## R2 첫30SIM 원본 점검 (전체40관문은 진행 중)

배치 loop6,722.934wall초/(30SIM×40)=**5.6024**로조정자차단기준6.0미만이며3.5경고다.
원래기록의보조값5.7466은진행중세계와완료세계의시작시각기준이섞여있다.
원본평가시작시각으로통일한교사작업처리량은5.8288이다([시각검증](R2-first30-episode-clock.json)).
이수정은보고용이며수용값5.6024와원본JSON은변경하지않는다. setup/compile408.9초는제외했다.
[측정](R2-first30-speed.json),[CPU재계수/단계](R2-first30-analysis.json),[관문/거부표](R2-first30-rejection_table.json).
완료7세계는독립평가원장재계수7/7일치,나머지33은진행중이다. CPU원본스냅샷1,277파일SHA일치·JSON오류0.
40세계저장진단감사0값은완료7의전체결과와나머지33의진단시점prefix범위이며전체관문통과가아니다.
최빈거부기록은peer_destination_reservation5,270건이다(고유후보수가아님). 영상과종료결과없이실패원인으로단정하지않는다.

알려진시드world000의+.5~29.5SIM2Hz59장·+20.1~29.9SIM10Hz99쌍,성공world028의+.5~17.5SIM2Hz35장·+8.0~17.9SIM10Hz100쌍을모두직접봤다.
진행중RGB100쌍해시는모두맞지만최신1프레임평가상태는다음틱에저장되어개요동기화는99쌍이다.
종료영상의100쌍요구는유지했다. live NPZ는아직저장되지않아startup처음.5SIM은이미지개요에서빠졌고,현재미리보기를전체원본영상으로주장하지않는다.
[회수/시각범위검증](R2-first30-playback-verification.json). Mac에새영상은가져오지않고몽타주와메타만회수했다.
현재새제어결함을확정하지않았고R2를계속한다. release는미제출이다.

알려진NVMAX시드8318706은R2에서task38.1SIM에양교사성공으로종료했고,CPU재계수382행·연속hold3.0초·입력감사0/0·weld off를확인했다.
2Hz77장/마지막10Hz100쌍을모두직접봤다([원본검증](R2-known-seed-success.json)). 전체40완료나CUDA700원인확정으로확대하지않는다.

12:14UTC 진행 스냅샷은42.9SIM·성공31/진행9·오류0·cap_end0이다. 누적환산7.2849는첫30수용5.6024와구분하며전체속도통과를주장하지않는다.

## R2 종료 검증

고정 소스175281c8922453465f8bf32707e22988e78b8812의 빔40 배치는 종료코드0, **성공40/40·cap_end0·HOST_ERROR0**이다. 물리 배치52.5SIM(스케줄러 마지막 tick 표시는52.6), loop17,238.570wall초이며 환산8.2088이다. 실제 교사 작업 합계1,472.3SIM 기준은11.7086이다. 첫30 판정5.6024는 통과/3.5경고이고, 전체 속도 통과로 확대하지 않는다. setup408.9초는 별도다.

CPU 원본 재계수40/40, Haiku 생성 독립 코드 재계수40/40·불일치0, 전체 입력감사40건 held_world_reads=0/invisible_measurements=0, weld off. [원장 재계수](R2-summary.json), [독립계수](R2-haiku-counter-result.json), [검증/자원](R2-terminal-validation.json). GPU 사용률 중앙값100%(1,762표본), physics가 loop94.2%이므로 후반 지연을 GPU가 놀기 때문이라고 단정하지 않는다. NoSlip10은 유지했다.

선언 원본26,060파일/382,010,624바이트 SHA 전수 일치([검증](R2-native-integrity.json)). summary와 manifest 자체는 선언 목록 밖이며, 종료 전송925파일 해시와 대표 선택 snapshot1,558파일 해시에서 따로 확인했다. 대표 성공13파일·108KB 영상과 전체78/최근100쌍을 Mac에서 검증했다([영상](R2-representative-artifacts.json)). R1과 CPU 결과는 합산하지 않는다.

gcp3는 타 lease/작업PID/GPU client 부재를 확인한 뒤 정지했고13:37:28UTC TERMINATED를 확인했다. 정지 직후 별도 set-scheduling 호출로8h 필드가 없어졌음을 감사로그에서 확인하여 정지 상태에서28800초/STOP을 다시 설정했다. 실행 중12:14UTC 변경 시도는 API가 거부했다([로그](R2-scheduling-audit.json),[정지](R2-host-stop.json),[복원](release-scheduling-restored.json)). release는 미제출이며 전체 MJWarp 전환/데이터 수용은 아직 not-ready다. 정상 종료한 빔 세션과 별개의 유한 release 세션에서도8h STOP·idle20·budget-stop을 유지한다.
