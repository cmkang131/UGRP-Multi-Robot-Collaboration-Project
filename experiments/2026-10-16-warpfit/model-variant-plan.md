# 추가 모델 변형·warm 횡펄스: 설계, 물리 미측정

조정자 노트의 scope2 추가 요청을 확인했다. 원래 접촉 비교3라운드와 분리한다. 이번 기록의 모델 변형·warm 펄스 물리 실행은0이며, 아래는 채택할 구현이나 성공 결과가 아니다. 사용자에게 범위/시간 연장 선택을 요청했고 답을 기다리는 동안 원래 비교를 마무리한다.

[원본 모델 재고](model-design-audit.json)는 gcp6의 MuJoCo3.12 CPU forward/배열 검사0step이다. 작은 상자는nv58/ngeom469, 빔은nv222/ngeom1386, 주행은nv234/ngeom1392다. 충돌 mesh는36/108/108개이며 주로36개/로봇의 수동 roller다. 단순히 모든 free body를 미관여 화물로 분류하면 r3 로봇까지 포함하므로 모든 로봇을 보호한다. 화물 freejoint만 없앨 경우의 nv는 원본 재고에서 계산한 추정치이며 컴파일·렌더·물리 확인값이 아니다.

후속 후보 M1 `warp_task_static_v1`(기본off): 명시된 활성 로봇·현재 화물을 보호하고 다른 화물의 freejoint를 제거한다. frozen reset의 pose를 XML body pose로 옮겨 같은 외관을 유지하고 qpos/qvel을 joint 이름으로 다시 매핑한다. 새 모듈에서 XML 사본을 컴파일하며 장면 원본을 고치지 않는다. C3.12 geometry/actuator reference도 변형 XML별로 새로 export해야 한다(원래 nq/nv/배열 reference를 재사용하지 않는다).

후속 후보 M2 `warp_task_primitives_v1`(기본off): M1 위에서 충돌 mesh를 CAD 경계로 계산한 원시 도형으로 바꾸고 시각 mesh는 유지한다. renderer에 보이는 collider는 시각용 사본을 보존한다. 원본 mass/inertia·마찰·카메라·dt를 고정하며, 충돌 도형 변경으로 자동 추정 관성이 바뀌지 않게 검증한다. 단순 AABB capsule 근사는 실제 roller 접촉과 같다는 보장이 없으므로 형상 오차 분포·주행/파지를 새로 잰다. 배율을 임의로 맞추지 않는다.

contype/conaffinity는 정적 화물끼리의 불필요한 후보만 제거하고 로봇/활성 화물과의 기존 pair eligibility는 그대로 유지해야 한다. 전체 mask eligibility 전후 비교에서 필요한 pair가 하나라도 달라지면 거부한다. 정적화 물체와 로봇(활성 화물 포함)의 보고된 접촉은 world·시각·두 geom·거리·힘을 원장에 적고 해당 세계를 비교 무효로 분류한다. 이 감사가 구현되지 않은 변형은 물리 실행에 승인하지 않는다.

렌더 관문은 같은 초기 reset에서 r1/r2 원래 카메라의 변형 전후 RGB 전체 hash/차이 픽셀0이다(사용자 요구의 동일 화면). 관절 상태 매핑·정적 body pose·시각 기하·관성도 별도 비교한다. 물리 GPU 시간/step·nv·ngeom·ncon·파지·slip·주행을 같은 N16/N64의 contact-v1과 짝지어 새 cohort로 기록하고 이전 결과와 합산하지 않는다. 파지/미끄럼 허용선은 원본 분포·실기 사양에 근거하며 새 보수적 상수를 넣지 않는다.

warm 주행 추가 계획은 같은 깨끗한 reset에서 전진100ms+정지 후 횡60ms/400ms다. 원래 단독 펄스와 구분하고 해당축 부호 있는 변위·yaw·tilt·실제 roller 접촉 상태를 평가로만 기록한다. v122에 등록되지 않은400ms 예측은null이며 임의 선형 외삽/이동 보정을 하지 않는다. 실제 채택·학습·교사 관문은 별도다.

## 출처

- [Menagerie Panda MJX 변경 설명](https://github.com/google-deepmind/mujoco_menagerie/blob/62ab00f2bc44f6f20c1c9b7a13f3fb1dd41a4e35/franka_emika_panda/README.md#mjx): 별도 MJX XML, 더 적은 접촉 도형·capsule과 solver 조정. 공개 예제의 actuator gain 변경은 우리 실기 근거가 없으므로 복사하지 않는다.
- [고정 mjx_panda.xml](https://github.com/google-deepmind/mujoco_menagerie/blob/62ab00f2bc44f6f20c1c9b7a13f3fb1dd41a4e35/franka_emika_panda/mjx_panda.xml).
- [고정 G1 MJX](https://github.com/google-deepmind/mujoco_menagerie/blob/62ab00f2bc44f6f20c1c9b7a13f3fb1dd41a4e35/unitree_g1/g1_mjx.xml): 시각 mesh와 원시 충돌 도형 분리, 명시 contact pairs. 보행 예제의 접촉 whitelist를 운반 장면에 그대로 복사하지 않는다.

세 원문은 실제 다운로드했고 sources.json에 SHA를 보존했다. MJX-JAX 예제는 모델 설계 참고이며 MJWarp의 성능/물리 성공 증거가 아니다.
