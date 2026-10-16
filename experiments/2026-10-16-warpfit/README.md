# warpfit — MJWarp 고유 접촉 프로필 (진행 중, 기본 OFF)

`origin/main` 0936e5609에서 codex/warpfit로 시작했다. 모든 흐름의 MJWarp 이관 방향은 유지하며, 이 진단은 기본 물리나 제어기를 바꾸지 않는다. gcp6 자체 결과는 다른 호스트 결과와 합산하지 않는다.

최대 3라운드: R1 짧은 import/step, R2 N16 및 C 기준 분포, R3 N64 같은 고정 명령 비교. 고정 명령과 공통 시작 상태만 전달하고 정답·접촉·관절은 평가 기록 전용이다. 작은 상자는 같은 시연의 3초 유지 구간 30개 10Hz 표본이며 독립 30개 무작위 임무 성공률로 보고하지 않는다. N16/N64는 단일 GPU 프로세스의 세계 수이며 독립 호스트 작업 수가 아니다.

후보 v1은 NoSlip0·elliptic·implicitfast·impratio5, v2는 Aloha/Robotiq의 finger pair solref .01/1·solimp .99/.995/.01·condim3 및 기존 tangential -6000 제거, fast는 v2와10/10 solver 반복이다. 기존 마찰계수·질량·기하·dt·카메라·weld OFF는 유지한다. 기준의1e-8 보존과 후보의 고정 MJWarp float32 tolerance floor 차이도 따로 기록한다. 후보 묶음의 효과이며 개별 인자의 인과 분해가 아니다.

파지 높이·유지·미끄럼은 C 기준 기록의 백분위로 판정하고, 물리 GPU event/step과 setup/JIT 제외 wall/SIM을 분리한다. 기준 자체가 들지 못하면 수용 관문은 미성립이다. 실행·실패·HOST_ERROR·cap_end와 원본 해시는 모두 남긴다.

## 참고 자료

- [고정 MJWarp README](https://github.com/google-deepmind/mujoco_warp/blob/57b4692f4d3cdf4d27d916b4b8c4759ba36e9148/README.md), 같은 버전 io.py350행: NoSlip 미지원은 discrete 적분기에 한정된다. 다른 적분기에서 NoSlip 구현이 있다. 과거 '미지원' 설명을 이 버전 전체에 확대하지 않는다.
- [공식 MJWarp 성능 안내](https://mujoco.readthedocs.io/en/latest/mjwarp/): CUDA graph, 관측 최대치에 맞춘 contact/constraint 용량, 그다음 solver 반복 조정. 현재 문서는 sparse/compact solver로60DoF 초과 장면을 다루므로 '60초과 미지원'으로 일반화하지 않는다.
- [MuJoCo 접촉과 slip](https://mujoco.readthedocs.io/en/stable/modeling.html#preventing-slip): elliptic/impratio로 soft-contact 마찰 이행을 강화한다. 무한 마찰·기계적 고정을 넣지 않으며 잔류 creep는 계측한다.
- [Playground Aloha](https://github.com/google-deepmind/mujoco_playground/blob/d59156e099a8785dd58fbce2e25a6ee1f7b5800c/mujoco_playground/_src/manipulation/aloha/xmls/mjx_aloha.xml): impratio5, condim3, finger contact 값의 출처.
- [Playground Panda Robotiq](https://github.com/google-deepmind/mujoco_playground/blob/d59156e099a8785dd58fbce2e25a6ee1f7b5800c/mujoco_playground/_src/manipulation/franka_emika_panda_robotiq/xmls/scene_panda_robotiq_cube.xml): implicitfast·iterations10·ls_iterations10. 예제의 물체 마찰0.6은 우리 실기의 측정값이 아니므로 복사하지 않았다.
- [공개 TIAGo 바퀴 모델](https://github.com/google-deepmind/mujoco_menagerie/blob/62ab00f2bc44f6f20c1c9b7a13f3fb1dd41a4e35/pal_tiago/tiago.xml): implicitfast·condim6. 일반 바퀴 예제이며 mecanum 롤러/집게의 condim6 정당화로 쓰지 않고 기존값을 유지한다.

공개 예제의 설정은 무미끄럼 보증이나 우리 장면의 검증 결과가 아니다. 원문 URL·고정 커밋·읽은 파일 SHA는 sources.json, 최초 실패 분포와 관문은 rejection_table.json에 있다. Drive·화면 앱·모델 호출·VM 자격증명 전송은 사용하지 않는다.

## 측정 작업량 정리 (R2 첫 기준 계측 뒤, 물리값 불변)

N16 상자 긴 시연의 4.1 SIM초에서 GPU147.011초를 관측했다. 사용자 요청은 작은 상자의 접촉·들기·3초 유지와 빔 짧은 구간이므로, 불필요한 돌아보기 시연을 성능 분모에 넣지 않는 별도 primitive-v1을 만든다. 기존 긴 시연 원본은 별도 long-probe로 보존하며 최종 짝 표와 합산하지 않는다. 세 물리 후보의 값은 수정하지 않는다. 주행은 같은18펄스를 N16에는16+2, N64에는18을 한 배치로 묶어 같은N·같은 명령으로 기준과 비교한다. 상자 유지 구간과 빔 시작 시각·C 기준은 새 fixture의 정확한 원본 인덱스와 함께 기록한다.

## drivecheck 반영

[별도 진단 PR #564](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/pull/564)의 완료 기록을 읽었다. 원래 장면은 차체–cargo_box_00이15.3449mm 관통하고 명령 전 약6° 기울며, C에서도 변위 붕괴가 재현됐다. 상자 하나를 옮긴 진단에서는 native3.16 17.03288mm / MJWarp17.04845mm(100ms)로 회복됐다. 이는 해당 작업자의 인과 대조이며 warpfit 측정에 합산하지 않는다. 본 비교의 원래 펄스·장면은 그대로 유지하므로 주행 수치는 초기 관통 조건의 프로필 반응이고, 새 주행 보정값이나 정상 접지 성능으로 수용하지 않는다. 같은 상자 이동 실험을 중복하지 않았다.

fast의 N16 빔은1.8SIM초에 OverflowType.LS_ITERATIONS=1024가 발생했다. 공통 실행기의 과거 문자열 CAPACITY_OVERFLOW와 실제 비트를 구분한다. 접촉 버퍼 확대나 solver 수치 재맞춤 없이 후보 탈락으로 남기고, 검토한 오류 경로를 명시하여 미제출 작업만 같은 라운드에서 재개했다. 원래 중단 funnel/attempts도 보존한다.
