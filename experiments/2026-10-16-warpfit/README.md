# warpfit — MJWarp 접촉 프로필 비교

후속 **[warpfit2 — CPU 모방15항목 감사·runtime 두 후보](warpfit2.md)** 완료: MJWarp25/25배치, 후보별 상자30/30·빔 짧은 유지. 용량 축소의 속도 이득0.1–1.2%, 공식plane의 빔 slip/속도 퇴행으로 두 후보 기본값 채택 권고 없음. v1 바이트·기본값 보존, gcp6 TERMINATED 확인. 아래는 선행 warpfit의 별도 결과다.

**권고 후보는 `warp_native_contact_v1`이다. 기본값·본 흐름은 변경하지 않았다.** 본 비교28개 배치와 별도 관통 조건 대조8개를 모두 평가했다. 총36개 중34개 고정 명령 완주·fast 빔2개 LS 한도 탈락이다. 모든 흐름의 MJWarp 이관 방향을 유지한다. 채택하면 같은 프로필로 교사 관문을 다시 재고 기존 CPU·다른 프로필/호스트 결과와 합산하지 않는다.

[Draft PR #562](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/562). `codex/warpfit`, base `0936e5609b500fa95d5db07a6441c328e5c4738e`. 물리 실행은 gcp6(g2-standard-8/L4), 초기 분석·영상은 gcp2, 최종 분석·N64 실패 영상은 원본이 있는 gcp6 CPU에서 완료했다(조정자22:17 지침 반영). 같은 입력을 반복한 기계 구간 진단이며 RGB 교사·학생·LLM E2E·실기 성공 검증은 아니다.

## 비교 조건과 결과

[전체 프로필 표](timing-table.md), [짧은 요약 JSON](summary.json), [모든 주행 벡터/회전·예측 CSV](drive-table.csv), [누적 funnel/거부 분포](rejection_table.json), [실행 전체 원장](all-attempts.json)을 함께 본다. `summary.json.box30`은 요청한30개 들기 궤적의 결과이고 [선택 목록](box30-selection.json)은 순서를 고정한 실제 world ID다.

상자는 N16 두 배치32궤적 중 첫 배치0–15 + 두 번째0–13, N64는0–29를 선택한다. 전체32/64 원본을 보존했다. 각 궤적은 닫기1.2초·들기1.5초·유지3초(10Hz30표본)다. **30표본과30회 들기를 구분한다.** 같은 초기조건을 복제한 세계들이며30개 무작위 seed의 일반화 성공률이 아니다. 빔은 공통 C 참조의 파지 전2.7초 상태에서 원래 명령2.7–6초를 실행하고 마지막0.3초3표본을 잰 짧은 구간이다.

주행 본 비교 `clear3`은 drivecheck PR#564의 검증된 초기 겹침 제거 진단 장면과 같은100/60/100ms 펄스다. cargo_box_00의 y(qpos216)만+0.2533209244140883m 이동했다. 이동량은 기존 차체/상자의 XY 외접 반경 합×2이며 새로운 맞춤 상수가 아니다. 준비 시 C forward만 사용했고 물리 step은0이다. 원래 -15.344881mm 접촉은 해당 pair의 contact array에서 사라졌다(양의 실제 간격은 미측정). 원래N16의18펄스는 `group16/tail2` 별도 진단으로 보존하고 N64에서 반복하지 않았다. 두 장면을 합산하지 않는다. 새 위치·주행 보정이나 장면 기본값으로 채택하지 않았다.

v1은 N16·N64 상자 선택30개를 모두 유지했고, 상대 미끄럼 P95는 각각0.05205/0.04908mm다. 빔도16/16·64/64를 유지했으며 P95는0.06717/0.06798mm다. v2의 빔 미끄럼은0.45089/0.44793mm였고 속도 차이는 작았다. fast는 빔에서 N16 1.8초(world6), N64 1.7초(world10)에 line search10회 한도가 발생해 탈락했다. 이 수치를 다시 맞추지 않았다. 개별 원인의 인과 분해를 하지 않은 **프로필 묶음 비교**다.

N16 본 주행의 전진100ms+정지1초 해당축 변위는 기준16.6493mm / v1 16.5569mm / v122 등록 예측12.9172mm, 펄스~정지 구간 최대 tilt는0.07662° /0.07133°였다. 모든 축의 부호 있는 XY와 yaw, 펄스 끝/정지 후를CSV에 남긴다. v122는 등록된 짧은 펄스만 쓰고 긴 펄스 예측은null이다.1초 정지 후 비교는 등록곡선0.2초 끝값을 유지하므로 이후 drift의 예측이 아니다.

GPU 시간은 같은10tick CUDA graph를 CUDA event로 잰 배치 step당 시간이며 고정 명령 커널을 포함한다. setup/JIT·기록·최종 저장은 GPU 시간에서 제외한다. wall/SIM은 기록·평가를 포함한 배치 지연, wall/(N×SIM)은 세계당 상각 처리량이며 서로 바꾸어 쓰지 않는다. 단일 GPU 프로세스의N64세계는64개 독립 VM 작업이 아니다. 기존 개별 실행 속도 관문 통과나 E2E 속도를 선언하지 않는다.

|N|구간|기준 GPU ms|v1 GPU ms|기준/v1|v1 wall/SIM|
|---:|---|---:|---:|---:|---:|
|16|box|9.0077|0.6501|13.86×|2.693|
|16|beam|54.6428|2.9125|18.76×|11.813|
|16|drive|44.2885|2.0284|21.83×|8.286|
|64|box|11.5191|0.7344|15.69×|3.048|
|64|beam|81.3407|3.5485|22.92×|14.394|
|64|drive|62.4938|2.2703|27.53×|9.297|

N16 box의 성능은 같은16세계 두 배치 평균이고 파지 평가는고정선택30개다. 나머지는각한배치며표의GPU 시간은배치step당이다.

## 프로필과 판정 근거

|프로필|NoSlip|impratio|Newton/LS|finger pair 변경|
|---|---:|---:|---|---|
|baseline_noslip10|10|1|80/50|기존 유지|
|warp_native_contact_v1|0|5|80/50|기존 유지|
|warp_native_contact_v2|0|5|80/50|condim3, solref .01/1, solimp .99/.995/.01/.5/2, solreffriction0/0|
|warp_native_fast_v1|0|5|10/10|v2와 같음|

elliptic·implicitfast는 기준에도 적용돼 있다. 기준의 명시적 tolerance1e-8과 후보의 고정 MJWarp float32 변환 floor1e-6도 다르다([고정 io.py433–436행](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py#L433)). NoSlip만 제거한 단독 효과로 속도 향상을 해석하지 않는다. friction·질량·관성·dt250μs·차체/물체/카메라·weld OFF는 유지했다. C3.12 컴파일 mesh/actuator 호환과 legacy Plane–Mesh는 전 프로필에서 고정했다. 공용 backend·제어기·지도 보정은 수정하지 않았다.

들기 존재 지표는 기존 교사의12mm 하부 clearance와 모든 finger의 양의 접촉력이다(`6f057f7e`, `sim/grasp_act_solo_evaluation.py:10`). 새 실기 허용치로 만들지 않았다. 미끄럼은 유지 첫 표본을 기준으로 한 물체 COM의 집게 좌표계 상대 이동량이고, 세계별 시간P95를 낸 뒤 세계간P95를 보고한다. 접촉점 전단 속도·회전 미끄럼은 이 값에 포함하지 않는다. tilt는 파지 유지 구간/주행 각 펄스 시작~정지 끝의 최대다.

C3.12 참조의 높이P05/미끄럼P95를 추가 배율 없이 비교선으로 사용했다. 상자70.654829mm/0.002580249mm(30표본), 빔40.269162mm/0.082036801mm(3표본)다. [thresholds.json](thresholds.json)에 원본 state SHA와 경로를 썼다. 궤적 비교는 해당 궤적 높이P05≥C P05·미끄럼P95≤C P95·접촉 유지다. 개별 프레임 funnel과 궤적 분포 판정은 별도이며 모든 프레임이 백분위 경계를 이기도록 요구하지 않는다(회귀 검사 포함).

v1 상자는 C의 미크론 단위 비교선을 충족하지 못했다. 기준 NoSlip10도 N16 0/30·N64 1/30이었다. 이를 실제 낙하나 새 실기 허용치 초과와 혼동하지 않는다. 실기 미끄럼 허용치·새 조건 일반화는 미검증이다. 따라서 권고는 후속 교사 관문의 후보 선택이며 기본값 채택·관문 완료가 아니다.

## 실행·무결성·재현

최대3라운드 안에서 후보 물리값을 재맞춤하지 않았다: R1 짧은N1 import/step, R2 N16·C 참조·요청30회용 두 번째 상자 배치·검증된 초기 겹침 제거 주행, R3 N64 동일 설정이다. [초기 계획](plan-initial.json)과 [최종 프로토콜](protocol-final.json), 실제 모든 argv/fixture SHA를 보존했다. R2 최초 긴 상자13.7초 기준은 별도 long-probe이며 primitive5.7초와 합산하지 않는다. 최초 import 실패와 fast의 두 solver 실패, smoke cap_end, 중단된 대기열의 미제출 작업도 전체 원장에 남긴다.

물리 코드 `scripts/warpfit.py`와 프로필 정의는 첫 primitive 커밋82bff588 이후 동일하다([코드 동일성](evidence/physical-code-equality.json)). 실행별 소스 SHA는 raw `result.json`/`RUN_META.json`에 있다. 최종 분석 소스는7514029f9(820d06324 경로 분류 수정 포함)다. 이전 분석기의 `clear3` 경로 끝 구분 오류는 원인과 실패 로그를 보존했고 물리 재실행 없이 고쳤다.

10Hz 상태는 모든 세계, 직접 기록한 MJWarp 자기 RGB JPEG 고리는 대표world0의 원래 mount/FOV로 기록했다. 다른 세계의 자기 영상은 저장 상태의 C 재구성임을 표시한다. 원본 호스트에서 개요+r1+r2의3배속 MP4(각≤8MB)를 만들고 ffprobe로 확인했다. 전체2Hz·실패 직전10초10Hz 띠를 직접 봤다. 실제 N16 fast실패 world6와 N64 world10도 별도로 재구성했고, 각각 마지막1.7/1.6초까지 뚜렷한 이탈·빠른 왕복 진동은 보이지 않았다. solver 경고 이후 상태가 없으므로 낙하 원인으로 추정하지 않는다. [검토 기록](evidence/N16-playback-review.json)과 해당 beam review JSON에 시각 범위·재구성 한계를 남긴다.

원본은 `gcp6:/home/ugrp/ugrp-sim/runs/warpfit`, gcp2의 검토 사본은 최종 라운드 일부만 포함한 과거 중간본이며 최종 백업으로 취급하지 않는다. 최종 분석은 `gcp6:/home/ugrp/ugrp-sim/ops-reviews/warpfit-ownhost`다. Mac에는 요약·해시·선택 영상/띠만 가져온다. 실행 기록의 기존 hash와 PR 메타데이터 이전본을 보존하고, >64KiB JSON은 zstd 무손실 압축·복원 SHA·삭제 전 매니페스트 기록을 확인한다. 원본59개 실행의 기존 SHA를 모두 확인했다. 압축67개와 분석 JSON2개를 복원 SHA로 검증했고, 최종 원본4,348파일·분석41파일의 전체 hash도 재확인했다. 선택 요약15파일727,876bytes 회수 SHA불일치0·Mac raw state 회수0이다([회수](evidence/final-retrieval.json), [전체 해시](evidence/final-inventory-verification.json)). JSON의 논리 파일명이 압축된 경우 `.zst`와 archive-receipt의 원래 SHA로 먼저 복원한다.

재현은 동결 fixture·기존 절대경로 rejection_table을 갖춘 queue·자기 lease와 새 출력 경로를 사용한다. 예: gcp6에서 `python -m scripts.warpfit_queue --enabled --round 3 --drive-clear-v1 --fixture-version primitive-v1 --preceding-funnel <R2-funnel> --root <raw> --source <0b5ef498e-source>`; 실제 실행 argv는 원장에 있다. 최종 분석은 gcp6 CPU에서 `MUJOCO_GL=disable python -m scripts.warpfit_analyze --root <raw> --assets <renderer-source> --output <new-analysis>` 다음 `python -m scripts.warpfit_report --analysis <new-analysis> --output <new-report>`다. 모델 호출·정답/접촉/측정 관절의 제어 피드백은0이다.

## 참고 자료


- [고정 MJWarp README](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/README.md), 같은 버전 io.py350행: NoSlip 미지원은 discrete 적분기에 한정된다. 다른 적분기에서 NoSlip 구현이 있다. 과거 '미지원' 설명을 이 버전 전체에 확대하지 않는다.
- [공식 MJWarp 성능 안내](https://mujoco.readthedocs.io/en/latest/mjwarp/): CUDA graph, 관측 최대치에 맞춘 contact/constraint 용량, 그다음 solver 반복 조정. 현재 문서는 sparse/compact solver로60DoF 초과 장면을 다루므로 '60초과 미지원'으로 일반화하지 않는다.
- [MuJoCo 접촉과 slip](https://mujoco.readthedocs.io/en/stable/modeling.html#preventing-slip): elliptic/impratio로 soft-contact 마찰 이행을 강화한다. 무한 마찰·기계적 고정을 넣지 않으며 잔류 creep는 계측한다.
- [Playground Aloha](https://github.com/google-deepmind/mujoco_playground/blob/d59156e099a8785dd58fbce2e25a6ee1f7b5800c/mujoco_playground/_src/manipulation/aloha/xmls/mjx_aloha.xml): impratio5, condim3, finger contact 값의 출처.
- [Playground Panda Robotiq](https://github.com/google-deepmind/mujoco_playground/blob/d59156e099a8785dd58fbce2e25a6ee1f7b5800c/mujoco_playground/_src/manipulation/franka_emika_panda_robotiq/xmls/scene_panda_robotiq_cube.xml): implicitfast·iterations10·ls_iterations10. 예제의 물체 마찰0.6은 우리 실기의 측정값이 아니므로 복사하지 않았다.
- [공개 TIAGo 바퀴 모델](https://github.com/google-deepmind/mujoco_menagerie/blob/62ab00f2bc44f6f20c1c9b7a13f3fb1dd41a4e35/pal_tiago/tiago.xml): implicitfast·condim6. 일반 바퀴 예제이며 mecanum 롤러/집게의 condim6 정당화로 쓰지 않고 기존값을 유지한다.

공개 예제의 설정은 무미끄럼 보증이 아니다. 원문 URL·고정 커밋·읽은 파일 SHA는 [sources.json](sources.json)에 있다. drivecheck의 완료 결과와 파일 hash는 [최종 읽기 기록](evidence/drivecheck-final-readback.json), 검증된 setup 재사용은 [출처 기록](evidence/drive-clear-source.json)에 남겼다.

## 종료·남은 범위

비물리 시험27개 통과(4.50초), 관리 기록58개에서 실행 중 source/input 변경0·최종화 오류0이다. 직접 실행한 기록 옵션 smoke1개는 별도다. 전체 원장은59개 중완료56/HOST_ERROR3/cap_end17을 구분한다. 초기 import 실패1개와 fast 빔 solver 실패2개를 포함하며, cap_end17개는 짧은 smoke다.

gcp6는 2026-10-16T14:02:14.626062+00:00 TERMINATED를 API로 확인했다. 다른 임대·UGRP 계산 프로세스·GPU PID가0임을 확인하고 자기 임대만 제거했다. 실행 상한 없음·idle20·budget-stop 설정을 유지했다([종료 전 검사](evidence/stop-admission.json), [종료 확인](evidence/host-after-stop.json)).

추가 조정자 요청인 [모델 정적화·원시 충돌 기하 및 warm 횡펄스](model-variant-plan.md)는 원본 재고0step과 설계까지다. 원래3라운드 상한에 맞춰 해당 추가 물리 검증은 실행하지 않았다. 새 프로필의 교사 관문도 미실행이다. gcp2 CPU의 마지막 확인 상태는TERMINATED이며 재시작 금지 지침 뒤 추가 시작0이다. 기존 `leases/warpfit-analysis.json`의 삭제 여부는 마지막 CPU 종료 뒤 미확인이다. 이를 확인하려고 CPU VM을 다시 시작하지 않았다.
