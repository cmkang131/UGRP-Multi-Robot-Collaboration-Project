# 결과 전 구현 점검

사전 등록 커밋 `5b2aba3f`. 최초 outcome 채점/본 replay 이전에 확인한 사항이다.

- 여섯 지도 모두 마지막 online snapshot과 frontend-grid의 frame/resolution/cells는 동일하다.
  전체 dict는 이후 odometry/공분산/입자/계수 갱신 때문에 다르다. 최초 생성자 smoke는 과도한
  dict 동일성 검사로 중단했다. 입력으로 사용하지 않는 동적 상태를 제외하고 지도 3필드의
  일치만 검사하며, 실제 변환은 명시한 마지막 online grid에서 한다. 지도 선택·관문 변경 없음.
- 생성자 연결 중 provider_factory 중복 인자와 function-binding의 metadata 누락을 수정했다.
  RGB/명령 재생 전 생성자 오류이며 새 지도/PF 상수 조정은 없다. 수정 후 100,000개 시작 입자가
  모두 자기 지도 observed-free에 놓이고 route=[]/slot=None, 기존 camera_v3 변환 유지 확인.
- S2의 exact-map admission은 기존 그대로이다. 새 모듈 내부의 private binding에서만 자기 map을
  전달하고, 카메라/운동 calibration은 기존 exact hash로 검증한 동일 값을 이전한다.
  생성자 호환용 legacy map_id는 시작 위치를 제공하지 않으며 외부 산출물은 ownmaps2a/own frame.
- 점유 셀을 가로 run으로 합친 obstacle rectangle은 생성자 호환용 무손실 2D 표현이다.
  미관측 height는 0 placeholder이며 sensor는 자기 grid EDT만 사용한다. 3D guard/경로/운반
  기능에는 이 지도를 사용하지 못하게 step/drive/_control을 명시적으로 차단한다.
- 확인된 floor 경계가 없어 S2 MapFeatures의 regions는 비어 있고, B 부분 관측은 observed_regions에
  원래 범위/출처와 함께 남긴다. 이미 본 부분의 바깥을 GT 구역으로 채우지 않는다.
- 평가 프레임 변환은 mapping-run 첫 eval trajectory chassis pose의 강체 SE(2)뿐이다.
  평가-only oracle의 관측지원 거리 0.4m는 사용자 제시 20–40cm 오차 규모를 사용하며,
  coverage는 0.2/0.4m 모두 표시한다. 이 설정은 첫 본 replay 이전에 고정했다.
