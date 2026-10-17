# warpfit2 — CPU 모방 설정 감사·runtime 두 후보

**이번 두 후보의 기본값 채택은 권고하지 않는다.** 모든 물리는 MJWarp로 유지했다. 용량 후보는 버퍼를 줄였으나 GPU 시간 개선이0.1–1.2%에 그쳤다. 공식 Plane–Mesh 복원 후보는 빔에서 약14% 느려지고 상대 slip이 커졌으며 warm60ms의 정지 후 순횡변위가 거의0이었다. 기본값·공용 backend·다른 작업자의 vendor는 바꾸지 않았다.

같은 worktree·`codex/warpfit`·[PR #562](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/562)의 후속이다. [CPU 모방/API 호환/할당15항목 감사](cpu-mimic-audit.md), [전체 수치 표](warpfit2-results/delivery.md), [25실행 요약 원장](warpfit2-results/run-ledger.json), [관문·거부표](warpfit2-results/rejection_table.json)를 함께 본다. 선행 warpfit 결과와 합산하지 않는다.

## 변경과 비교

- `warp_upstream_plane_v1`: C3.12 plane/mesh 선택을 복제한 monkeypatch를 생략하고 설치 pin의 공식 collider를 쓴다. C3.12 컴파일 geometry/actuator 참조는 유지하여 collider 변경과 컴파일 변경을 섞지 않았다.
- `warp_measured_capacity_v1`: R1의 native-v1 매physics-step4000Hz P100으로 전체 contact 버퍼와 세계별 constraint 버퍼를 정한다. 실제 import 수를 포함하고 임의 배율·power-of-two 확장을 추가하지 않는다. overflow면 거부하며 재맞춤하지 않는다.

두 토글은 모두 기본off다. 기존 `sim/warp_native_contact.py` SHA `a5c8d370755034b9f9615f66a94b87883327b7d7ecc4e13082eac2c2d4751c6a`는 바이트 동일하다. 이번 모든 물리 실행은 그 파일의 `warp_native_contact_v1`(noslip0)을 명시했다. 모델 정적화·원시 충돌 도형은 [이전 설계](model-variant-plan.md) 단계 그대로이며 새 모델 변형의 검증 결과로 보고하지 않는다.

## 결과와 권고

3라운드 **25/25배치 완주, HOST_ERROR0·cap_end0**이다. R1 N16 baseline↔공식plane8배치, R2 N16 baseline↔관측용량8배치, R3 N64 세조건9배치다. 상자는 각 비교에서 선택30/30, 빔은 각16/16 또는64/64의 모든 기록 hold 표본에서 기존12mm clearance+전 손가락 양의 힘을 만족했다. 동일 초기조건 복제이며 독립 seed 일반화가 아니다. 상자는 닫기1.2·들기1.5·유지3초, 빔은 공통 pre-close 상태에서3.3초 실행 뒤 마지막0.3초의10Hz3표본이다.

|N64 구간|기준 GPU ms/step|관측용량|공식plane|
|---|---:|---:|---:|
|상자|0.7355|0.7320|0.7558|
|빔|3.5548|3.5350|4.0535|
|주행|2.4102|2.4073|2.6327|

관측용량은 상자 ncon32→19/nj128→94, 빔128→65/512→306, 주행128→64/512→252로 줄었다. contact는 전체 버퍼를 세계 수로 나눈 할당값이며 세계별 엄격한 최대가 아니다. 총 VRAM 절감률을 측정한 값도 아니다. 속도 목적의 우선 채택 근거는 약하며, 더 큰 배치의 메모리 할당 후보로만 남긴다.

공식plane의 빔 slip P95는 N16 기준0.0630→0.4334mm, N64 0.0694→0.4338mm였다. 낙하를 관찰한 결과가 아니라 같은 native-v1 분포 대비 퇴행이다. 공식 경로라는 이유만으로 품질 향상을 가정하지 않는다. 실제 실기 slip 허용치는 이번에 새로 만들지 않았다.

warm은 원래 전진100ms+정지1초 뒤 횡60/400ms다. 원래500ms 고정명령의 첫400ms와 기존 정지를 복사해400ms 자극을 만들었다. 동작 예측을 외삽하지 않았다. N64 정지 후 해당축 중앙값은 기준 cold60 **7.062mm**, warm60 **2.927mm**, warm400 **44.263mm**였다. 공식plane은 각각 **6.701mm, −0.016mm, 44.228mm**다. 원래 짧은 전진·회전 펄스도 함께 보존했다. 모든 세계의 부호 있는 XY/yaw·tilt는 [CSV](warpfit2-results/drive.csv)에 있으며, FOLDED/초기 겹침 제거 진단 장면이다. HIGH·생산 지도 보정·학생 동작의 검증으로 확대하지 않는다.400ms는 진단 자극이지 정책 상수가 아니다.

GPU 값은 CUDA event 배치step 시간이다. 명령·매step 최대치 기록 커널을 포함하고 setup/JIT·RGB 기록은 제외한다. [전체 타이밍 CSV](warpfit2-results/timing.csv)의 wall/SIM은 기록·평가를 포함한 배치 지연이다. 독립 실행 지연이나 E2E 속도 관문 통과로 바꾸어 해석하지 않는다.

## 거부표·영상·해석 한계

[최종 funnel](warpfit2-results/rejection_table.json)은 실행·hold 프레임·펄스 경계 이벤트를 순차 누적 통과/거부로 남겼다. native 높이 백분위392프레임·slip 백분위437프레임의 비교 제외가 있고, 기록한 hold 표본의 파지 접촉 상실·12mm 하회와 엔진 오류는0이다. 이 백분위 제외를 실패 실행 수로 합산하지 않는다. 거부 사유·물체 이름·미측정 gap 상태를 명시했고, 각 [대기열](warpfit2-evidence/queues/)의 `rejection_table`은 당시 VM에 존재한 절대경로다.

원본 gcp6에서 성공1개·빔 분포 거부1개·warm60 사례1개의 개요+r1/r2 영상을3배속으로 만들었다. 전체2Hz·전 구간10Hz 띠를 직접 보았고 ffprobe·회수 SHA를 확인했다([검토 시각·타임라인·한계](warpfit2-evidence/playback-review.json)). 큰 낙하·빠른 왕복 진동은 보이지 않았다. 상자 자기 RGB는 파란 면, 빔 자기 RGB는 큰 색 면이 대부분이라 자기 영상만으로 미세 파지를 확인하지 못한다. warm world4의 자기 영상은 저장 상태의 C3.12 재구성이라고 표시했다. 학습/교사 시각 관문 통과가 아니다. 원래 camera mount/FOV는 바꾸지 않았다.

모든 세계 상태는10Hz, 직접 MJWarp 자기 RGB 고리는 대표world0에 저장했다. warm의 다른 lane에 대한 실시간 접촉력 원장은 없다. 추가 물리step0으로 R3 각 프로필의 대표6lane·240개 snapshot을 **같은 MJWarp 충돌 기하로 재구성**했다([기준](warpfit2-evidence/contact-review-off/summary.json), [공식plane](warpfit2-evidence/contact-review-warp_upstream_plane_v1/summary.json), [관측용량](warpfit2-evidence/contact-review-warp_measured_capacity_v1/summary.json)). 이름·접촉점 수·최소 gap을 보존했지만 원래 실시간 힘이나 롤러 위상이 원인이라는 증거로 쓰지 않는다. 반환 현상의 인과는 미확정이다.

판정은 기존 교사의12mm와 native-v1 원본 P05/P95만 사용했다([경계 출처](warpfit2-results/thresholds.json)). 원래 C 백분위의 전체 거부 분포도 [수정 전 기록](warpfit2-evidence/preceding-rejection-distribution.json)에 보존했다. 상수 재맞춤·추측 물리 수정·네 번째 라운드는0이다.

## 무결성·재현·종료

물리 소스는 `4748ef1f0331675ac3849fed5ad9c391b51e6295`, 분석 소스는 `199a55f3a`,0step 접촉 감사는 `fa0aa2062`, 표 생성은 `fed86735a`다. [물리 코드 동일성](warpfit2-evidence/physical-code-equality.json)에서 이후 물리/접촉/큐 코드 변경0을 확인했다. [실행 전 계획](warpfit2-rejection-initial.json), [실행 프로토콜 정리](warpfit2-protocol.json), [공식 원문 SHA](warpfit2-sources.json), [준비 오류·해결](warpfit2-evidence/setup-issues.json)도 남겼다. 준비 오류는 물리 실행 오류와 섞지 않았다.

원본은 `gcp6:/home/ugrp/ugrp-sim/runs/warpfit2`다. **2,175파일89,404,360bytes 전체 SHA 불일치0**, 원래 실행 manifest25·관리 기록25의 실행 중 소스/입력 변경0·최종화 오류0을 확인했다. 큰 JSON36개는 zstd 복원 SHA를 검증했다([검증](warpfit2-evidence/final-inventory-verification.json), [전체 해시](warpfit2-evidence/final-inventory.json.zst), [압축·metadata 이전본 대응](warpfit2-evidence/archive-receipt.json)). 복사된 fixture의 기존 `SHA256.json`은 이전 출처이며, 새 fixture의 권위 있는 스냅샷은 [fixture-hashes.json](warpfit2-evidence/fixture-hashes.json)이다.

Mac에는 요약30파일554,793bytes와 검토20파일만 회수하여 SHA 불일치0을 확인했다([회수 검증](warpfit2-evidence/retrieval-verification.json)). 원본 npz·전체 RGB 프레임은 가져오지 않았다. raw는 gcp6 영속 디스크 보관이며 별도 원격 백업을 완료한 것은 아니다. 선택 영상은 `/Users/changmin/projects/ugrp/outputs/e2e18-admin/playback/warpfit2/`에 있다.

재현은 같은 소스·환경·v1과 새 raw root/자기 lease를 사용한다. 큰 논리 JSON이 `.zst`만 남아 있으면 receipt의 원래 SHA로 먼저 복원한다. 물리 실행은 `python -m scripts.warpfit2_prepare --root <new-root>` 후 `python -m scripts.warpfit2_queue --root <new-root> --round 1` →2→3이며, 구체적인 입력·각 실행 argv는 대기열 attempts와 원본 result에 있다. 분석은 gcp6에서 `PYTHONPATH=<physical-source> MUJOCO_GL=disable <warp-python> scripts/warpfit2_analyze.py --root <raw> --output <new-analysis>`다. GPU 물리 재실행·제어·교사 관문은 서로 구분한다.

gcp6는 **2026-10-16 15:18:59Z (10/17 00:18:59 KST) TERMINATED**를 API로 확인했다. 정지 전 load0.033·GPU PID0·다른 계산 작업0·자기 lease만 확인 후 자기 lease를 제거했다([정지 전](warpfit2-evidence/stop-admission.json), [종료 API](warpfit2-evidence/host-after-stop.json)). VM/task wall 상한 없음·idle20·budget-stop ACTIVE를 유지했다([예산 정지](warpfit2-evidence/budget-stop-after.json)). CPU VM 시작0·Mac sim/render0·GUI/브라우저0·모델 호출/키/에이전트 자격 증명 전송0이다.

관련 비물리 시험11개 통과. PR은 권고 검토용 Draft로 유지한다. 채택 시 각 흐름 자체 관문은 새 프로필에서 다시 재며 기존 결과와 합산하지 않는다.
