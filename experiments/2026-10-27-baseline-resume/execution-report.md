# Baseline Arm C/S 실행 재개 최종 보고

**실행 완료·VM 정지 확인.** Arm C와 S는 각각20/20 정상 종료, 물리 성공은 각각0/20입니다. C 파일럿·속도·무결성 관문을 통과한 뒤에만 S를 실행했습니다. HOST_ERROR·관리 중단·재시도는 모두0입니다. 2026-10-27 09:01:51.767 KST 실제VM `TERMINATED` 확인. 이번 할당4.422833611 GPU-h, 이전 근사13.1을 더한 누적 **약17.522833611/20 GPU-h**이며 새 연구 전체5.3 GPU-h 상한도 지켰습니다.

동결본 SHA-256 `043b9583427d845e08c19bb63448f779e4f33913a858b7ad4f8590f7f0e8dafb`를 실행 후에도 확인했습니다. **사전등록 동결본은 변경하지 않았습니다.** 존 이동은 사용자 지시에 따른 실행 인프라 변경이며 사전등록 프로토콜 변경이 아닙니다. 체크포인트 step-011000·원33/처치10 파일·실행 소스·평가기·20 seeds를 유지했습니다.

## 실행과 예산

| 항목 | Arm C | Arm S |
|---|---:|---:|
| 정상 분모 / 성공 | 20 / 0 | 20 / 0 |
| 성공률·양측 CP95% | 0%, [0,16.843347%] | 0%, [0,16.843347%] (기술통계) |
| 제출 UTC | 19:56:25.554 | 22:00:19.702 |
| 종료 UTC (2026-10-26) | 21:51:10.975 | 23:49:20.074 |
| 소유 실행기 wall초 | 6885.421491 | 6540.372171 |
| 배치 wall초 | 6873.517023 | 6523.393227 |
| 첫30SIM median wall/per-worldSIM | 2.037200644 PASS | 1.983122718 PASS |
| raw `cap_end` / 조기 learned 종료 | 18 / 2 | 17 / 3 |
| 입력·처치·완료 무결성 오류 | 0 | 0 |

C 대 동결 r2(성공0/20)의 등록 paired exact McNemar p=1.0입니다. S와 C↔S의 기전 비교에는 확증 p-value를 만들지 않았습니다. 팔별 분모를 합치거나 평균내지 않았습니다. C batch wall6873.517<등록 후속 취소 임계9180초였습니다. 첫4 완료 world13,18,0,1의 파일럿4조건이 모두 PASS였고, S 전 저장·봉인·원33/처치10·스택·예산·C funnel을 다시 확인했습니다. 정상 실패를 재실행하지 않았습니다.

물리 성공은 원본 physical_success와 원본 carry evaluator 성공의 AND를 유지했습니다. 배치의 간이60SIM `cap_end`가 조기 learned 종료까지 시간종료로 표시하는 차이는 별도 termination-crosscheck에 보존했습니다. C world13/18, S world0/12/18은 learned_finished_early이며 HOST_ERROR나 성공으로 바꾸지 않았습니다. 원래 reason `teacher_terminal` 문자열은 학생 종료 라벨로 그대로 보존했으며 교사 행동 사용을 뜻하지 않습니다.

L4 할당 시작2026-10-26 19:36:29.566UTC→종료2026-10-27 00:01:51.767UTC의 **전체 구간**을 GPU 원장에 넣었습니다. C/S 실행기 wall 합산은3.729387128 GPU-h이며 나머지는 필수 복원검증·CPU집계·보존 구간입니다. 원장은 과거13.1이 근사이므로 누적도 근사입니다. 최신 확인한 공급자 예산 이벤트2026-10-26 23:55:49.225677UTC는 순비용0 KRW/예산1000 KRW입니다. 이는 지연 집계이며 실시간 크레딧 잔액이 아닙니다. budget-stop·유휴20분 장치를 변경하거나 우회하지 않았습니다.

## 행동과 관문

| 학습 stage 로봇 틱 | C | S |
|---|---:|---:|
| approach | 40,567 | 40,843 |
| alignment | 14,405 | 18,995 |
| ready | 877 | 1,674 |
| execute | 13,752 | 6,868 |
| carry | 252 | 0 |
| place | 73 | 582 |
| 실제 유효 틱 합 | 69,926 | 68,962 |

각 arm에서 유효 틱=inference=discard=issued이며 state225 비영0, skill은 모두grasp였습니다. C software hold0·실제 거부0·nonzero wheel15,379틱입니다. S software hold8,323·nonzero wheel15,753틱, 실제 거부는 `execution_without_GO_ACK`4,682틱이고 close 거부는0입니다. 이는 남긴 S 장벽의 동작이며 무결성 오류가 아닙니다. 모든4개 정답/교사 입력·보정 카운터는0입니다. 자기 RGB·자기 발행 이력만 사용하고 TOP/정적지도/정답 제어, weld, noslip 보정은 쓰지 않았습니다.

후보별 **순차 누적** 평가 funnel은 approach→alignment→READY→grasp→hold3s→carry1m→door→place 순으로 C `20→0→0→0→0→0→0→0`, S `20→1→0→0→0→0→0→0`입니다. alignment는 평가 전용 GT 공동 기하이며 학습 stage 이름과 다른 관측입니다. C frame funnel: approach34,963중25,047통과/9,916거부, alignment25,047중0통과/25,047거부. S: approach34,481중23,928통과/10,553거부, alignment23,928중665통과/23,263거부, 그665프레임의 누적READY는0/거부665입니다.

**S에서 handshake가 한 번도 열리지 않았다고 결론 내릴 수 없습니다.** 누적 alignment 뒤의 READY는0이지만, 전체 원본에서는 동시 policy READY8틱(1world), 동시 protocol READY410틱(2world), GO7/ACK4/START3, permit801로봇틱(2world)이 기록됐습니다. policy READY1,674틱과 protocol READY4,442틱은 서로 다른 관측원입니다. C는 동시 policy/protocol READY·GO/ACK/START·permit 모두0입니다. C의 개별로봇 READY877틱은 동시 READY 성공이 아닙니다. S barrier event READY51도 틱 수와 다른 이벤트 수입니다.

평가 전용40로봇 궤적의 max XY excursion(m) 최소/중앙/최대는 C0.171713/0.616572/1.554284, S0.152359/0.618721/1.023511입니다. net XY 중앙값 C0.570545/S0.615386m, XY path 중앙값 C1.150100/S1.001809m, yaw path 중앙값 C8.126799/S8.351676rad입니다. 기존r2 경험적 P100 0.030829875m를 넘는 실제 XY 이탈이 관측됐지만 목표 접근·유용한 주행·운반 성공을 보장하지 않습니다. C 개별로봇 양쪽 jaw의10Hz 표본 접촉223틱, S0틱이고 원본 공동 hold 발생은 두 arm 모두0입니다. 로봇간 직접 접촉·낙하의 원인·최소 장애물 틈은 미측정이며 UNKNOWN/not_observed·null로 명시했습니다.

## 동결 해석표와 적용 범위

아래는 동결본 C-12(b)의 허용/불허 표를 그대로 재현한 인용이며, 마지막 열의 문구는 이 보고서의 결론이 아닙니다.

| 관측 | 허용할 결론 | 허용하지 않을 결론 |
|---|---|---|
| C 성공 ≥1/20 | 고정 과제에서 감독 해제와 입력 피드백 변화 아래 성공 사례가 생김. 감독의 원인적 기여 가설과 부합 | 조율 불필요, 일반화, 1건으로 유의한 개선 |
| C 0/20 + stage가 approach 밖으로 진행 | 감독 해제가 정체를 일부 해소해도 이 정책/과제에서는 성공으로 이어지지 않음 | 원래 장벽이 필요했음 |
| C 0/20 + 유효 stage 표본 전부 approach | 감독 해제만으로 stage 정체를 해소하지 못했고, **G1을 포함한 장벽이 stage 진행의 병목이었다는 근거는 없다**(병목 후보는 정책 stage head 쪽) → stage-head 진단이 다음 과제 | **'모든 실패 원인이 stage-head로 확정됨'**. |
| S에서 파지 시도·움직임이 생기나 READY=0, 성공 0 | close freeze는 행동을 가렸고 handshake는 여전히 열리지 않음. stage 병목 가설을 좁힘 | 장벽 제거가 손해였음 |
| S 성공, C 실패 | 남긴 조율과 다른 입력/전환 경로를 후속 진단할 근거 | 조율의 보편적 필요성 증명 |
| C 성공, S 실패 | G1 해제만으로 부족한 이 과제의 추가 실행 경로 효과 후보 | 어떤 개별 G5–G8이 원인인지 식별 |
| C 접촉/낙하·비대칭 release | 평가 전용 원본으로 물리 실패 양상 보고 | 장벽이 옳았다는 증거 |
| close 거부 0 | 처치 무결성 확인 | 파지·운반 성공 |

실제 C는 **0/20이면서 유효 학습 stage가 approach 밖으로 진행한 분기**입니다. 감독 해제가 정체를 일부 해소해도 이 고정 정책/과제에서는 성공으로 이어지지 않았습니다. 전부approach인 분기나 stage-head 단일 원인 확정 분기를 적용하지 않습니다. S는 일부 handshake가 열렸으므로 표의 READY=0 문구를 전체 프로토콜에 일반화하지 않습니다. 개별 장벽의 필요성·보편적 조율 효과·실물 및 미관측 조건의 일반화는 결론 내리지 않습니다.

동일 보류20개는 P5·r2에 이은 세 번째 사용이며 n=20입니다. C/S의 입력 피드백·전환 경로가 달라집니다. grasp 고정 skill과 B의 release/place 토큰이 섞이는 confound를 제거하지 않았습니다. 과거 교사P5는 다른 감독/장벽의19/20이고 첫4 funnel은 미기록이며0으로 보충하지 않았습니다. 과거 held flag20과 strict19의 기준 차이도 유지합니다. 호스트 복원 뒤 렌더 바이트 동등성은 별도 측정하지 않았고, 과거 호스트·백엔드·noslip10 결과와 합산하지 않았습니다. 학습·새 데이터·새 seed·hybrid·교사 강제 forward·stage-head 변경은 수행하지 않았습니다.

## 복원·봉인·검토 및 절차 공시

서울a18:45:45UTC 시작 실패→10분 경계 뒤 a재시도 실패→서울b19:06:00→도쿄a19:16:10→b19:26:20 모두 `ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`였습니다. 도쿄c19:36:20 제출이 성공해19:36:29.566 할당됐습니다. a2차는 **18:55:45UTC 이후** 재시도이며 초 단위 실제 시작은 stderr에 없으므로 스케줄 경계로만 기록합니다. 성공 후 불필요한 미국 존 할당은 하지 않았습니다. 원문·명령·시각·해시는 증거 디렉터리와 summary의6개 시도에 연결했습니다. 용량 부족으로 연구를 ABORTED 처리하지 않았습니다.

원본260GB 디스크와 READY snapshot `ugrp-gcp6-baseline-20261026t1850`을 보존했습니다. 복원에 필요한 SSD quota만 서울300→520/도쿄250→260으로 승인됐고 GPU/예산 한도는 늘리지 않았습니다. 미국 quota 요청은 쓰지 않았습니다. 미연결·미부팅인 우리 중복 복원 디스크만 ID/사용자0 확인 뒤 제거했습니다. 실제 실행은 `ugrp-sim-f-1016 / asia-northeast1-c / ugrp-act-l4-gcp6 / id2102818194467198298`, g2-standard-8·L4 한 대입니다.

C-07은 실제GCP·OracleARM·실제Mac 디스크와 전체 쓰기/동시쓰기0, GPU중복작업0, 원장·budget-stop ACTIVE/IAM/전존 aggregated_list·유휴20분·서비스계정 없음까지 확인했습니다. 은퇴alias의 기본 all-hosts 실패 원문도 남기고 실제3호스트를 따로 측정했습니다. 상세는 [C-07](2026-10-27-baseline-resume-c07.md)입니다. VM에 모델 키나 에이전트 자격 증명을 복사하지 않았습니다.

원33/처치10 해시는 실행 전·S전·종료 후 모두 일치했습니다. 실행 소스commit `22fc786b5813e9139bb58d790a98e984e33d03e8`, 부모 study RUN_META SHA `519723dcdaff812373da9628e8d13a23a119b742217fba5856e1d20d073e9507`를 코호트 동안 고정했습니다. 기본off 외부exact-ID 존어댑터만 명시적으로 켰고 원host 검사·정책/물리/카메라/평가기 파일은 무변경입니다. S/T/R/A4개HEAD는 C 전 Git refs와1,034,407,929B 완전bundle로 보존·verify했습니다. 별도L원본도 사전 해시 확인 후21:16UTC에 정확한 바이트를 Git에 추가했으며 그 보존 시점을 앞당겨 표현하지 않습니다.

필수 검토는 C 전 DeepSeek 동결문서 **PASS** 판정을 받았습니다. 별도 코드 보충은 응답길이 종료·본문0 원문을 남긴 뒤 사용자 지시대로 MiniMax의 서면 **CONDITIONAL_PASS/구조 차단0**으로 대체했고 명시한 원격/봉인/33 조건을 실측 충족했습니다. 인프라어댑터도 별도 서면검토·양성/음성 CPU검사를 통과했습니다. 후처리 CPU집계기는 MiniMax D1–D3를 결과 집계 전 수정했고 두 arm의 실제 schema·완료·입력·평가 재계산이 오류0으로 확인됐습니다. 추가 선택적 중간검토는 MiniMax 하네스의 설정 인증파일 부재로 실패했고 DeepSeek 대체 CLI도47분44초 본문0이라 해당 소유 프로세스만 종료했습니다. **추가 검토는 NO_VERDICT**이며 필수 사전 검토의 판정으로 둔갑시키지 않습니다.

C 제출 전 `check_current_stack` 결과파일을 빠뜨린 절차 누락은 사후 발견·그 시각 그대로 공시했습니다. 점검은16 current/9 frozen approved_deviation, `ok=true/current_compliant=false`입니다. 이를 현재스택 완전준수나 사전검사로 소급하지 않습니다. S는 새 점검을 제출 전에 연결했습니다. 하위 원기록의 legacy dev/pr484 메타는 변경하지 않았고 부모 study/pr621를 실제 식별자로 사용합니다. 정상20·상위exit0·GPU0 확인 후에만 종료 EXIT/housekeeping sidecar를 추가했습니다. 첫 압축 거부·모든 오류 원문도 보존했습니다.

## 원본 보존·모델 배포·재현

원본 실행디스크는 정지 상태로 보존합니다. ARM 사본 `/home/ubuntu/ugrp-archive/runs/baseline-resume-20261027T1936Z-tokyo-c`는 **67,165파일·984,266,253B** 전체SHA 및 rsync checksum diff없음을 검증했습니다. 사본 작성 뒤 계산 여유46,839,118,323B>25GiB입니다. 전체 source inventory SHA `29ddc8787bf6dab5c22cafb6699c5e864b3c9e1130beaaa5ee38463352447574`이며 `.jsonl/.json`의 검증된 zstd 표현과 원/압축/해제SHA는 COMPRESSED/ALL-hashes/SHA256SUMS에 남았습니다. C 사전압축23파일·18,066,015B와 연구 최종25파일·18,304,357B 절감은 별개 단계입니다. 최종 보존은 모든 이미지 파일의 바이트 해시를 확인했지만 의미/시각 동등성 재분석을 수행한 것은 아닙니다.

선택 모델은 [새 GitHub Release](https://github.com/cmkang131/UGRP-Multi-Robot-Collaboration-Project/releases/tag/models-20261027-pairact-r2-step11000-v1)에 보존했습니다. ZIP192,222,979B·SHA `8a64f127dbc727d7f625bc8b7b8520f10fa1d586090795198ff089b8e0d87e01`, payload13파일208,826,488B입니다. Oracle 공개 재다운로드·모든 파일해시와, VM 정지 뒤 Mac의 새 공개 다운로드·고정 sourceS `3c9337d5f5c9deefd49139b26ae7117022e3d5cc` clone의 strict CPU로딩을 확인했습니다. 239 state entries·51,818,398 parameters·CPU전용·CUDA초기화false·forward0입니다. 배포 검증은 물리 성공·학습 데이터 전체 백업을 뜻하지 않습니다. 기존Release자산을 덮어쓰지 않고 검증JSON을 추가했습니다.

실행 CPU집계 소스 SHA `29792450dd3fc8e0a54f46eb80bc134c3e2d3368a5165dee4ea66f597f819222`. GPU cohort 종료 후 원VM CPU에서만 아래 명령을 실행했습니다. 같은 이름의 출력이 이미 있으므로 재계산 시 새 디렉터리를 사용해야 합니다.

```sh
CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 python3 -B \
  /home/ugrp/ugrp-sim/baseline-resume-ops-20261027/summarize_arm.py \
  --arm arm_c --input /home/ugrp/ugrp-sim/runs/baseline-resume-20261027T1936Z/arm-c \
  --out /home/ugrp/ugrp-sim/runs/baseline-resume-20261027T1936Z/derived-C-v1
# S: --arm arm_s, arm-s, 새 derived-S-v1 사용. 현재 VM은 정지 상태.
```

짧은 결과·40개 실행의 실패 사유/원본 경로/해시·funnel·검토·예산·보관 검증은 `experiments/2026-10-27-baseline-resume/summary.json`에 연결했습니다. 현지 증거는 `2026-10-27-baseline-resume-evidence/`, 이전 진행 이력은 `resume-report-before-final.md`입니다. 현재 실험 소스 이후 변경은 보존·후처리·보고와 테스트 픽스처뿐이며 동결 실행에는 배포하지 않았습니다. 마지막 결과 커밋의 CI/PR 상태는 아래 후속 기록으로 확정합니다.
