# R11 — HIGH base-motion sweep의 시간 표본 사이 bound

source: #363 `6727751b49ce11fb62234bb97274137f22850765`; 후속 `de03fe87d08879abefaa7dac67c7ff313df5df89`는 README만 바뀌었다. **검사한 predicted trajectory의 표본 사이에 padding이 없다는 의심은 반박된다.** 아래는 코드에 구현된 고정-servo rigid-envelope 경로의 수학적 경계이며 실제 물리 collision safety의 증명은 아니다. 새 simulator/renderer/실기기/영상 실행은 하지 않았다.

## 실제 호출과 값

HIGH의 base command는 `PairCommandGuard.check` → `guard.motion_clear(..., loaded=self.carrying_beam)`를 거친다(`zone_pair_guards.py:757–790`). 현재 wrapper는 shared `PairSweepGuard.motion_clear`의 결과를 먼저 사용한다. 그 함수가 거부할 때만 start-relief의 별도 규칙을 검토한다. 이 메모는 **shared motion_clear가 정상적으로 True인 경로**를 다룬다. 기존 R8의 start-relief finding을 다시 세지 않는다.

`zone_pair_geometry.py:103–144`의 실제 계산은 다음과 같다.

- 입력 command의 forward/left/turn을 각각 `BACKOFF_GAIN_MAX=1.6`으로 곱해 f,l,w를 만든다. duration은 finite,0…1초다.
- `n=max(1,ceil(duration/0.05))`, Δt=duration/n이며 시작과 끝을 포함한 n+1개 time을 검사한다.
- `L=max(0.2, hypot(bx,by)+radius for all body/loaded-beam spheres)`.
- `pad=(hypot(f,l)+abs(w)*L)×Δt/2`를 residual에 더한다. 현재 PairGeometry margin은 이 residual을 **계수1**로 사용한다(`zone_final_pair_guards.py:22–26`). 예외가 나도 finally로 이전 residual/loaded flag를 복원한다.
- 실제 평가하는 angular rates는 `ω∈{-|w|,0,+|w|}`다. “모든 가능한 intermediate ω를 검사한다”는 구현은 아니다.

current carry emitter의 lease는0.15초이므로 n=3, interval0.05초다. tick도0.05초이지만 padding은 tick을 암묵적으로 가정하지 않고 command duration/n에서 계산한다. `door_schedule`은 원하는 속도0.06m/s를 measured full gain/deadband로 역변환해 raw command를 만든다(`zone_final_pair_skill.py:167–205`). **desired yaw velocity가0이어도 raw turn이0이라고 가정하면 안 된다.** 같은 source가 raw action의 허용 범위를 검사한 후 schedule을 만든다.

## 구현된 곡선이 derivative bound를 만족하는 이유

초기 yaw를 θ, 고정 body point를 b라 하자. 코드가 쓰는 base-frame translation q(t)는 ω≠0에서

\[
q_x(t)=\frac{f\sin(\omega t)+l(\cos(\omega t)-1)}{\omega},\quad
q_y(t)=\frac{f(1-\cos(\omega t))+l\sin(\omega t)}{\omega}.
\]

그러므로 `q′(t)=R(ωt)(f,l)`이고 norm은 항상 √(f²+l²)다. ω=0 분기는 q(t)=(ft,lt)로 같은 bound를 만족한다. `pose.moved`는 이를 초기 yaw로 회전해 world translation을 만들고, `replace(...,yaw=θ+ωt)`가 body rotation을 별도로 더한다. 즉 검사 point의 world path는 `p(t)=p0+R(θ)q(t)+R(θ+ωt)b`다. 이 함수는

\[
\|p'(t)\|\le\sqrt{f^2+l^2}+|\omega|\|b\|
\le\sqrt{f^2+l^2}+|w|L=:B
\]

를 만족한다. 각 sample 사이 어떤 t에도 가장 가까운 sample ti가 Δt/2 이내에 있으므로 `||p(t)−p(ti)||≤BΔt/2=pad`이다. 이는 코드와 다른 Euler integration이나 endpoint chord를 가정한 유도가 아니다.

`_rect_distance`(`zone_own_guards.py:225–231`)는 rotated solid rectangle까지의 **unsigned Euclidean distance**다. set까지의 distance는1-Lipschitz이고 rigid coordinate rotation은 거리를 보존한다. 따라서 sample에서 `distance−sphere_radius−base_reserve−pad≥0`이면 중간 time에서 `distance−sphere_radius−base_reserve≥0`이다. 현재 margin의 σ 항과 body lever는 고정 servo/고정 σ인 이 sweep에서 불변이다. base yaw만 변하므로 sphere z 및 height-based skip 조건도 변하지 않는다.

chassis의 perimeter test points도 같은 bound 안에 있다. 최대 horizontal lever는 `sqrt(.15²+.09²)=.174929m`으로 L의 하한0.2m보다 작다. 여기서 증명한 것은 **코드가 검사하는 point/sphere envelope의 시간 coverage**이며, chassis의 공간 sample model 자체가 모든 실제 부품을 덮는다는 새 증명이 아니다.

## beam 공간 sampling과 단위 대조

catalogue bar는600×40×32mm이고 own grip은각끝30mm 안쪽이다(`sim/zone_cargo.py:151–160`). `_beam_spheres`는 길이방향 n=ceil(.6/.02)=30개 간격,31개 center를 두고

`radius=sqrt(.020²+.016²+(.300/30)²)=.02749545m`

를 쓴다(`zone_pair_geometry.py:49–60`). bar 임의 점에서 가장 가까운 center까지 longitudinal 차이는최대0.01m이고 yz 차이는각각0.02/0.016m이므로 이 sphere union은 **저장된 rigid bar box**를 덮는다. beam flex/slip/tilt를 추정한다는 뜻은 아니다. 그런 제한은 모듈 설명에도 명시되어 있다.

이 bound에서 f,l은 예측 translation rate, w는 예측 angle rate, L은 metres, Δt는 seconds이므로 pad는 metres다. 실제 허용 raw command 전체 범위(f≤.15, |l|≤.10, |w|≤.15)를 써도 같은 유도는 성립한다. 이 허용 최대값이 current calibrated schedule에서 실제 발행됐다고 주장하지 않는다.

## 이 증명이 다루지 않는 경우

1. **start-relief가 baseline veto를 뒤집는 경로:** 그 경로는 일부 initial negative clearance를 그대로 허용하며 동일한 zero-clearance 전제가 없다. padding이 존재한다는 사실만으로 relief의 더 넓은 physical guarantee를 결론내리지 않는다.
2. **검사된 세 constant-twist 이외의 경로:** 시간에 따라 바뀌는 actuator response, cross-axis gain, lag/coasting, 다른 turn rate의 집합 전체를 위 세 궤적이 공간적으로 감싼다는 증명은 하지 않았다. gain1.6의 실제 plant bound도 재측정하지 않았다.
3. **arm interpolation 또는 동시에 변하는 shape:** 위 식은 servo가 고정된 base-motion 검사다. `transition_clear`의 ≤20PWM sampling은 별도 알고리즘이며 이 time pad의 보장을 자동으로 가져가지 않는다. frontier가 조사하는 hold/applied-target 의미와도 분리한다.
4. **추정 오차·지도 오차·beam 변형:** guard는 own estimate, issued commands, static geometry에 의존한다. 실제 pose/calibration이 margin 밖으로 틀렸다면 표본 사이 bound가 그것을 고치지 않는다.

정상 bounds 안에서 “0.05초마다 endpoint만 봐서 벽을 건너뛴다”는 합성 반례는 이 코드의 pad를 무시하면 만들어질 수 있지만, 그것은 현재 구현의 반례가 아니다. 이 좁은 의심은 source와 analytic bound로 해결되어 추가 fuzzing/임의로 얇은 벽 테스트는 수행하지 않았다. physical safety나 전체 collision guard의 qualification을 부여한 결과로 사용하지 않는다.
