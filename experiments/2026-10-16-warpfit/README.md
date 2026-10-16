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
