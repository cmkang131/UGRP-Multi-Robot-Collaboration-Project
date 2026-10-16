# simalt5 — C 버전 동등성 회복, MJWarp 끝점 관문 실패

**PARITY_FAIL / ready=false.** 컴파일·충돌 호환을 적용한 C3.12와 C3.16은 **173,600스텝×135열 전체 비트 일치**했다. 같은 모델의 Warp에는 **12.099 mm** 끝점 차이가 남는다. 3라운드에서 종료했으며 빔 들기·처리량 N16/64/256은 제출하지 않았다. 운영 backend와 기본값은 유지한다.

[요약](summary.json) · [거부 분포·관문](rejection_table.json) · [최종 벡터 분해](evidence/remote/version-decomposition-corrected.json) · [첫 관절 분기](evidence/remote/first-joint-divergence-corrected.csv) · [스텝·관절 발췌](evidence/remote/joint-step-excerpts-corrected.csv) · [전체25개 스텝 표 색인](step-tables-index.json) · [영상 검토](playback-review.md) · [작업 기록](work-log.md).

## 실제 결과

5 mm/2°/높이 차 2 mm는 사용자의 탐색 관문이며 완화하지 않았다. hold의 30은 같은 3초를 10 Hz로 잰 **시간 표본**이고 독립 30회 성공률이 아니다.

| 같은 grip tape | 몸체 끝점 차이 | 각도 차이 | 양쪽 접촉/30 | hold 높이 차 최대 |
|---|---:|---:|---:|---:|
| simalt4 Warp, 새 컴파일 값 | 11.508 mm | 0.242° | 30 | 0.01584 mm |
| R1 Warp, C3.12 감쇠 복원 | 10.558 mm | 0.150° | 30 | 0.00821 mm |
| R3 Warp, 감쇠+기하·캐시 복원 | **12.099 mm** | **0.141°** | **30** | **0.01876 mm** |
| C3.16, 같은 복원+검증된 native Plane–Mesh | **0** | **0** | **30** | **0** |

R3 상자 끝점은 1.949 mm/0.048°다. 무부하 전진·측면·회전은 각각 0.228/0.0467/0.0202 mm로 3/3 통과했다. 그러나 몸체 끝점 한 항목이 실패해 작은 장면 전체 관문은 불통과다. 최종 Warp 첫 접촉/제약 수 차이는 **4스텝/0.001초**, 첫 패드 접촉 유무 차이는 **53,626스텝/13.4065초**, 첫 5 mm 초과는 **53,825스텝/13.45625초(close)**다. 파지·release 뒤에만 생긴 차이가 아니다. 모든 최종 tape에서 overflow0을 확인했다.

## 원인 분리에서 확인한 것

1. **감쇠만의 문제는 아니다.** C3.12에 C3.16 감쇠만 넣으면 11.305 mm 움직이고 기존 Warp와는 0.575 mm 차이였다. 그러나 반대로 Warp 감쇠를 C3.12로 맞춰도 10.558 mm가 남았다. 따라서 초기의 “대부분 감쇠일 것” 가설을 채택하지 않는다.
2. **컴파일 호환은 C에서 실제 검증했다.** 같은 XML의 `actuator_biasprm[:,2]` 4개와 기하·캐시 65개 배열을 C3.12 컴파일 결과에서 가져왔다. 기하에서는 12개 배열 값이 달랐다: `bvh_aabb`, `bvh_nodeid`, `geom_aabb`, `geom_quat`, `geom_rbound`, `geom_sameframe`, `geom_size`, `mesh_extrema`, `mesh_normal`, `mesh_polynormal`, `mesh_quat`, `mesh_vert`. 형상을 튜닝한 것이 아니라 같은 형상의 주축·정점·연결 캐시를 함께 옮겼다. simalt4의 body-frame Hausdorff 최대 8.883e-10 m를 근거로 했고 새 허용 오차를 만들지 않았다.
3. **전체 배열 감사도 했다.** 479개 공통 numeric 배열 중 남은 차이는 `actuator_ctrlspec`와 `dof_length`뿐이며, 현재 fixed-gain actuator 경로와 sleep OFF에서 사용하지 않는 차이다. 모든 공통 옵션은 같고 flex는 없다. 감쇠는 `put_model` 뒤에도 C3.12 값의 float32 변환과 정확히 일치했다. [전체 감사](evidence/remote/full-model-differences-C316-compiled312.json), [입력 범위](evidence/remote/inactive-array-scope.json).
4. **native 대조기의 오류를 따로 제거했다.** 초기 C 포팅은 translation을 matvec 합 안에 넣어 원본과 덧셈 순서가 달랐다. 그 포팅은 같은 C3.12에서도 13.318 mm 어긋났다. 이 4개 실행은 버전 원인 추론에서 제외했다. MuJoCo 원래 수학 함수 호출 순서로 고친 뒤 C3.12 원본↔C3.12 포팅↔C3.16 호환 모델의 모든 기록이 비트 일치했다. 따라서 초기 13.318 mm를 “버전 엔진 차이”라고 해석한 진행 중 설명을 철회한다. [최종 비트 검사](evidence/remote/native-corrected-bit-parity.json).
5. **남은 차이는 Warp 경로다.** 최종 C 버전 간 잔차는 0, 같은 버전·컴파일 모델 C↔Warp 잔차는 12.099 mm다. float32 상태/명령·충돌 support/접촉 선택·솔버 산술의 개별 기여까지는 분리하지 못했다. 순수 float32 원인이라고 단정하지 않는다. native에서 덧셈 순서만 바뀌어도 긴 접촉 궤적이 달라진 사실은 수치 경로 민감도를 보여 주지만 GPU 잔차의 단독 원인 증명은 아니다.

원래 11.508 mm 벡터는 감쇠 개입 4.343 mm, 기하 개입 4.533 mm, 최종 Warp 잔차 12.099 mm의 **벡터 합**으로 분해했다. 서로 상쇄되므로 이 norm들을 더하거나 독립 원인 비율로 읽지 않는다. 벡터·부호 있는 투영·첫 관절 차이·각 단계 원본 SHA는 최종 분해 JSON/CSV에 있다. C3.12 `MjModel`을 그대로 쓰는 경로도 조사했으나 pinned Warp import가 `mjINT_DISCRETE` 부재로 거부했다(0 physics step). [직접 변환 검사](evidence/remote/direct312-import.json).

## 토글·검증·남은 범위

`legacy-plane-v1`, `dense-capacity-v1`(njmax256), `compiled-312-v1`, `compiled-geometry-312-v1`은 모두 기본 off다. 마찰·질량·접촉 solref/solimp·dt·noslip10·관절 이득을 새로 맞추지 않았다. XML/이름/배열 레이아웃/물리 배열 불일치는 거부하며 파라미터를 추정하지 않는다. 일반 backend에는 적용하지 않는다.

- 새 물리 진단 16회 완료, HOST_ERROR0·cap_end0. 초기 native 대조 4회는 위 이유로 원인 추론에서 제외한다. 모든 실패·분석 오류·직접 API 거부·source setup 오류를 원장과 작업 기록에 남겼다.
- 비물리 고유 검사 8개 통과, 구문·diff 검사 통과. actual gcp2 물리 결과와 별도다. PR은 Draft이고 전체 CI 결과는 없다.
- 모델 호출·학습·실물·Mac 물리/렌더0, weld OFF. 저장 명령만 재생했고 평가 상태를 제어에 돌려주지 않았다. 10 Hz 자기 RGB ring은 기록 전용이며 마지막 10 SIM초를 보존했다.
- 빔 들기·새 처리량·n4 대비 SIM초/$는 **미측정**이다. simalt3의 비동등 처리량을 이번 후보에 재사용하지 않는다. RGB renderer의 기존 부분 투명도 문제도 해결된 것으로 보고하지 않는다.

## 재현·보존

기준 fixture는 simalt3의 `d3548742053aa18ee526297baa2611bb37b32f923b504097dc5a0c17f4184577`, XML은 `ad46cd87ef4188daa9a4dbebd79c470fac6f1b3fcb5e5a1fe0d9dfa3c2261849`다. R1 source e89ff153, R3 source62563f51, 수정 native 대조 source09d585b7이며 각 result의 실제 script·XML·fixture SHA와 argv를 따른다. 실행 중 source 사본을 변경하지 않았다.

실행 명령은 [R1](run-round1.py), [R2 native](run-native-controls.py), [R3](run-round3.py), [native 자기 대조](run-native-selfcontrol.py), [대조기 수정](run-corrected-native-controls.py)에 있다. 모든 queue는 당시 존재한 절대경로 `rejection_table`을 포함했다. R2의 이른 분석은 실행 중 Warp 입력을 거부했고 완료 뒤 새 경로에서 재분석했다. 탐색/계획 wall 예산은 없고 고정 physics tick으로 제한했다. 3시간 wall 상한은 사용자 자원 제한만을 위한 것이다.

원본은 gcp2 L4 `/home/ugrp/ugrp-sim/runs/simalt5/` 영속 디스크에 남는다. 전체 외부 백업은 아니다. 전체 스텝 CSV는 압축/복원 SHA를 확인해 VM에 보존하고, Mac/Git에는 요약·해시·발췌를 회수했다. 최종 원본 해시·회수 검증·L4 시간/비용/정지 상태는 `summary.json`과 연결된 증거를 따른다. CPU gcp2의 다른 작업 임대·프로세스는 유지한다.

## 참고 자료

- [공식 3.15 dampratio 변경 b3dd9e617](https://github.com/google-deepmind/mujoco/commit/b3dd9e617): 반사 관성 계산 변경. 추정값 대신 같은 XML의 C3.12 실제 컴파일 값을 사용했다.
- [C3.12 Plane–Mesh 원본](https://github.com/google-deepmind/mujoco/blob/3.12.0/src/engine/engine_collision_convex.c#L966): support/이웃 선택, maxplanemesh3·tolplanemesh.3, matvec 뒤 translation 순서의 근거다.
- [공식 변경 기록](https://mujoco.readthedocs.io/en/stable/changelog.html): 3.13 Plane–Mesh와 elliptic Newton 구현 변경을 확인했다. 이 중 하나를 잔차의 유일 원인으로 단정하지 않았다.
- [고정 MJWarp io.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/io.py), [고정 types.py](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/mujoco_warp/_src/types.py): put_model과 float32 저장 형식. 고정 설치를 재사용했고 전 패키지 source 재감사·float64 실행을 주장하지 않는다.
- [C3.16 forward](https://github.com/google-deepmind/mujoco/blob/3.16.0/src/engine/engine_forward.c), [sleep](https://github.com/google-deepmind/mujoco/blob/3.16.0/src/engine/engine_sleep.c): fixed gain 입력과 dof_length/sleep 범위 확인. URL·다운로드 SHA는 [참고 파일 원장](evidence/reference-sources.json)에 있다.

L4는 **TERMINATED**, 실제 사용 **3,417.701초(0.94936h)**다. 기존 $1.096/h 가정의 VM 정가 추정은 **$1.04050**이며 실제 청구·디스크·네트워크·세금은 미확인이다. 3시간 상한 안에서 종료했고 Mac 자원 감시도 끝냈다. CPU gcp2도 외부 임대·프로세스0을 확인하고 자기 임대를 해제한 뒤 정지했으나, 이후 `scenetex5.json` 작업이 다시 시작했다. 현재 CPU VM은 RUNNING이며 추가 정지하지 않았다. [종료 상태](evidence/hosts-final.json), [CPU 최신 임대](evidence/CPU-restarted-state.json).
