# T07 실물 실행 기록기 확인

## 목적
정책이 실제 소비한 영상과 발행 명령, 실패를 실행 단위로 재구성할 수 있는지 확인한다. 실물 결과는 **확인 안 됨**.

## 준비물
기존 recorder/trace 분석기, 저장 RGB·가짜 명령, 저장 공간, 해시 도구. 개인 주소·계정·인증정보를 로그 공개본에서 제거한다.

## 병렬 준비와 물리 통합
저장 입력 재생과 오류 주입은 독립. 실제 로봇 trace를 검증할 때만 T06 이벤트·명령 ID 의미를 맞춘다. T08/09를 기다리지 않고 무부하 시험으로 통합할 수 있다.

## 실행절차
1. [기록기](../../real_execution_recorder.md)와 [trace 구조](../../real_trace_system.md)의 기존 run/span 형식을 사용한다. 임의 새 logger로 대체하지 않는다.
2. 정상·입력 소실·명령 거부·기록 저장 실패를 모의 주입하고 종료·실패 이유·프레임 연결을 확인한다.
3. 정적 자산 감사에서 기록기 개요는 기본 4 Hz JPEG 샘플링, trace 문서는 all-consumed-frame 모드를 설명한다. 실행별 설정을 확인하고, 이 trace를 ACT 10 Hz 데이터셋 완성으로 간주하지 않는다. 관측·행동 계약으로 변환하고 프레임/발행 명령 시각을 맞추는 작업이 필요하다. 10 Hz 명령을 4 Hz 저장 영상만으로 완전 재생했다고 하지 않는다.
4. 원본 해시를 검증하고 기존 분석기를 실제 trace에 실행한다. consumed/saved 수와 저장 지연을 별도 보고한다.
5. 무부하 실물 trace의 처음·중간·끝 영상과 명령을 직접 대조한다. best-effort 로거가 실패를 삼켜도 증거 누락을 성공으로 처리하지 않는다.

## 수치 통과기준
**초안 제안·실물 미검증·담당자 합의 필요:** 모의 100틱에서 발행 명령 연결 100/100, 누락 이유 없는 소비 프레임 0개, 보존 파일 해시 불일치 0개. full-frame 기록을 선택했다면 소비 프레임 보존율 100%; 오류 주입 case는 누락 수/이유를 정확히 보고한 것으로 검사하며 정상 완전성 통과와 분리한다.

## 기준의 근거
100틱은 10 Hz에서 10초 입력·출력 연결을 확인하는 smoke 제안으로 장기 성능 보장이 아니다. 100%/0은 증거 연결의 완전성을 검사하려는 기준이며 실제 logger의 best-effort 특성상 충족 여부는 별도 실측해야 한다.

## 시뮬 기준
자기 RGB 640×480·모델 320×240, 명령 10 Hz. 발행값과 실제 관절·이동 상태는 구별한다. 시뮬 평가 GT는 입력 로그와 분리한다.

## PR 결과 상대경로와 형식
`experiments/sim2real-<YYYYMMDD>-T07-<run>/`: [공통 template](../04_tasks.md#result-template), `trace_audit.csv`, `analysis.json`. CSV: `run_id,span_id,consumed,saved,issued,linked_commands,missing_frames,missing_reason,hash_mismatches,scope`. raw는 `outputs/real_traces/<run>/` 상대경로로 manifest에 연결한다.

## 막힐 때
[trace 분석](../../real_trace_system.md), [기록기 시험](../../../tests/test_real_execution_recorder.py), [분석기 시험](../../../tests/test_real_trace_analysis.py). 로그 부재로 물리 실패 원인을 추정하지 않는다.
