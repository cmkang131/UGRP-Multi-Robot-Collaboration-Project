# Baseline Arm C/S 실행 재개 보고

**진행 중 — ARM_S_RUNNING.** C20은정상완료·CPU재집계성공0/20·무결성오류0입니다. C파일럿/속도/원장/저장/스택을확인해07:00:19KST S20을제출했습니다. S첫30속도1.98312271834PASS, 현재표시50.3SIM·20실행중입니다. 모델Release공개재다운로드/13파일해시는PASS이며새소스CPU로딩·S최종집계·종료정지확인은남아있습니다. 아래문구는각시점의이력입니다.

사전등록은 REGISTERED_FROZEN, SHA-256 `043b9583427d845e08c19bb63448f779e4f33913a858b7ad4f8590f7f0e8dafb`이며 무변경입니다. 존 이동은 사용자 승인된 실행 인프라 변경이고 사전등록 프로토콜 변경이 아닙니다. 같은 g2-standard-8/L4 및 동결 step-011000·코드·평가기·20 seeds를 유지합니다. 각 arm을 한 VM에서 실행하고 호스트 간 부분 결과를 합산하지 않습니다.

- 서울 asia-northeast3-a 기동 재시도 2회 모두 `ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`. 공급자는 asia-northeast3-b 가용을 안내했습니다. 실제 작업 시각·원문은 증거 디렉터리에 보존합니다.
- 원본260GB 디스크의 전역 스냅샷 `ugrp-gcp6-baseline-20261026t1850` 생성 완료(READY). 원본 VM·디스크는 보존합니다.
- 같은 리전 b 복원은 SSD_TOTAL_GB 한도300GB에 원본260+복원260GB가 들어가지 않아 실패했습니다. 도쿄 asia-northeast1-a도 지역 한도250GB가 복원260GB보다 작아 실패했습니다. us-central1 지역 한도 역시250GB입니다. 디스크 크기를 줄이거나 원본을 지우지 않습니다.
- 서울의 동시 보존에 정확히 필요한520GB SSD 할당량을 요청 중입니다. GPU 개수·예산 정지 기준을 올리는 요청이 아닙니다. 요청 응답은 별도 증거로 남깁니다.
- DeepSeek 최종 서면 PASS(동결 문서 한정), 차단 결함0. 원격 검증을 대신하지 않습니다. 검토 전문: `2026-10-27-baseline-resume-crossreview-deepseek.md`.
- budget-stop ACTIVE, 최신 공급자 예산 알림 2026-10-26T18:47:04Z costAmount=0 KRW, budgetAmount=1000 KRW. 함수가 프로젝트 모든 존을 aggregated_list하므로 복원 VM도 정지 대상입니다. 실시간 크레딧 잔액은 API 미제공이고 순비용0을 잔액으로 표현하지 않습니다.
- C-07 actual-host 저장 검사, 원격33/33, S/T/R/A Git 보존, RUN_META 봉인은 복원 후 완료합니다. Oracle ARM·실제Mac 공간은 직접 확인했고 기본 all-hosts의 은퇴 alias 실패도 보존했습니다.
- 신규 workload GPU0, 이전 근사 원장약13.1/20 GPU-h. 새 VM의 실제 할당 구간과 실험 wall을 각각 기록합니다. C→파일럿/속도/무결성 통과→S→즉시 TERMINATED 확인 순서, C wall>9180s이면 후속취소, 신규5.3/전역20 GPU-h 유지.

증거: `2026-10-27-baseline-resume-evidence/`. 결과 수치는 실행·회수 후에만 추가합니다.


## 2026-10-27 04:02 KST 인프라 진전

- 서울 SSD quota520GB 실제 승인(기존300→520, GPU수/예산불변). asia-northeast3-b에 스냅샷 복원 pd-balanced260GB 디스크 READY를 확인했습니다. 원본a의 VM·260GB 디스크와 스냅샷은 보존합니다.
- 새b VM 기동은 직전a 실패 후10분 간격인19:06UTC에 제출합니다. 대기 중 GPU VM은 가동하지 않습니다.
- S/T/R/A 고정커밋을 Oracle에서 Git refs로 고정하고 완전한1,034,407,929B Git bundle을 생성·verify했습니다. SHA와4개HEAD는 source-git-preservation.json에 있습니다. 처치패키지는 별도commit99fd922afbd5a03cf4231fd166fc56920b67d0aa 및 bundle로 보존했고 동결실행10파일의 로컬해시도 일치합니다. 원격확인을 대신하지 않습니다.


## 2026-10-27 04:11 KST 후속 시도

- 19:06:00–19:06:06UTC 새b존 실제L4 할당도 `ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS`로 실패했습니다. 모든오류원문은 create-vm-b-01.command.json에 보존했습니다.
- 도쿄SSD quota260GB가 실제승인됐고 asia-northeast1-a에도 pd-balanced260GB 스냅샷복원이 완료됐습니다. 다음실제VM기동은10분간격인19:16:10UTC입니다. GPU할당/에피소드실행은아직0입니다.
- DeepSeek의 문서최종PASS는수령했습니다. 별도3파일코드보충은 reasoning길이상한으로본문0 종료하여, 원문·reason=length·32,000reasoning tokens를남기고 사용자지시대로MiniMax서면코드확인으로대체중입니다. 검토를생략하지않습니다.


## 최종 교차검토 보충 수령

MiniMax-M3가 지정 동결 문서와 코드3파일을 직접읽고 **CONDITIONAL_PASS, 설계·코드 차단결함0** 서면판정을 반환했습니다. 조건은 원격33/33·S/T/R/A HEAD/clean·C07·RUN_META·소스Git의 실행전의무이며 새설계조건이 아닙니다. L의 실제AST삽입스코프와최종argv는원격에서추가확인합니다. 원격/GPUruntime을확인한것으로확대하지않습니다. 전문: 2026-10-27-baseline-resume-code-review-minimax.md.


## 2026-10-27 04:22 KST 연속 재시도

도쿄a 실제기동도 용량부족으로 실패했습니다(19:16:10–19:16:16UTC). 다음 순서는 도쿄b·c→미국중부a·b·c→서울재시도이며10분간격으로순환하는실행기를기동했습니다. 각시도의UTC·계정/프로젝트/존·명령·오류원문을개별command.json과infra-attempts.jsonl에보존합니다. 지역260GB한도내복원을위해, 우리작업이새로만든 **미부팅·미연결 복원사본**만확인후제거하고다음존에다시복원합니다. 원본a디스크·VM·스냅샷·study원본은보존합니다. 지금까지GPU할당성공/실험은0입니다.


## 2026-10-27 04:56:25 KST Arm C 제출

도쿄c L4기동성공(19:36:29UTC, id2102818194467198298). 원본33/처치10/HEAD-clean/CPUactor/ASTplan/실제3호스트저장/원장·budget-stop/소스Git/서면검토를완료했고 RUN_META revision2 봉인뒤Arm C20개를제출했습니다. supervisor pid3647, study root `/home/ugrp/ugrp-sim/runs/baseline-resume-20261027T1936Z`. 상세C07: 2026-10-27-baseline-resume-c07.md. 원래host확인기의서울zone하드코드는디스크파일무수정·기본off 외부exact-ID zone어댑터로해결했으며별도서면검토와CPU실측을완료했습니다. 사전등록프로토콜변경이아닙니다. S와재시도는아직제출하지않았습니다.


## 2026-10-27 05:21 KST 속도 관문 PASS

C20 started=20·completed=0, 33.6/180SIM진행중. 첫30SIM median wall/per-worldSIM=2.037200643825, SPEED_GATE_FAIL=false·warning=false. 모델/physics실행중이며아직성공·funnel·파일럿결과를확정하지않습니다. 사용하지않는서울b의우리복원중복디스크만ID/미연결확인후제거했습니다. 원본a와현재Tokyo c실행디스크·snapshot은보존합니다.


## 최신 스택 점검의 절차 누락 공시 (2026-10-26T20:57:40.155082+00:00)

C 실행 제출 전 check_current_stack 결과 파일을 남기지 않은 절차 누락을 확인했습니다. C 제출 후 생성한 current-stack-declaration-v1.json와 current-stack-check-v1.json은 시각을 그대로 남겼으며 사전 점검으로 소급하지 않습니다. 점검16개 current, 동결 유지에 따른9개 approved_deviation, ok=true/current_compliant=false입니다. 장면/화물/시나리오 버전명 미확인, 학생 경로의 교사 toggle 미적용, 실행 후 원장 확인 예정, 별도 heading 보정 금지, 사용자 GPU 예산 watchdog, 원본 min_gap_m 필드명을 항목별로 기록했습니다. 이 도구는 선언 점검이며 runtime/물리 검증을 대신하지 않습니다. 사전등록/봉인/원본 코드는 무변경이고 S는 이 점검을 실행 전에 연결합니다.


## 2026-10-27 07:00:19 KST S20 제출

C20 정상 완료·CPU 재집계 N_eff20, 물리 성공0/20, CP95%[0,16.843347%], 등록 exact McNemar p=1.0. 무결성 오류0, 실제 거부0·software_hold0, stage합/infer/discard/issued 모두69,926. stage: approach40,567/alignment14,405/ready877/execute13,752/carry252/place73. 첫4 파일럿4조건 PASS, 첫30속도PASS, C batch wall6873.517s<9180. raw cap_end18와 조기 learned_finished2를 별도 집계하며 batch60기준 cap_end와의 차이는 termination-crosscheck에 남깁니다.

S 제출 전 새 스택 선언 점검PASS(16 current/9 frozen approved_deviation, current_compliant=false), 실호스트3곳 저장·순비용0/1000·budget-stop ACTIVE·봉인RUN_META·원33·처치10·funnel SHA를 재확인했습니다. 제출 시 예상재개4.4699/5.3GPU-h·누적약17.5699/20입니다. 원RUN_META는 변경하지 않고 S_ADMISSION/S_ADMISSION_FINAL 및 stack-check를 별도 봉인했습니다. S supervisor12706, 재시도없음.

C 종료 후 원VM GPU프로세스0에서 분석했습니다. 하위 원기록기 RUN_META의 과거dev/pr484 표기는 수정하지 않았고, 부모study/pr621 봉인과 원본complete·정상20 확인을 근거로 새 EXIT0/housekeeping sidecar만 추가했습니다. 종료표시 부족으로 최초압축거부 원문을 보존했고, 뒤23파일 무손실압축·해제SHA일치와 전체해시를 기록했습니다(18,066,015B 절감). 정책·원본 rows/decision은 무변경입니다. 모델10파일도GPU0구간에만수집해동결bytes/SHA를확인했고Release는아직미완료입니다.
