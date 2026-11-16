# 3차 측정 실행 묶음 (P-063, P-064 · 2026.10.15)
# 측정용 85턴을 같은 밤에 같은 코드로 3회씩: C · 지금 D (전부 gemini) · 개선 D (gemini + 규칙 분류) · 안 2 (n0·n2·n3 luna + 규칙 분류, n5·n6 gemini)
# B는 뺌: 노드 2가 없어 ⑦이 들지 않고, 사전 밖 풀이가 구조적으로 낮음(2차 측정 84.6% vs C 96.2%·D 92.3%, 10.15 개발용 10/14 vs 14/14) (P-066)
# 안 2는 개발용에서 속도 탈락이었지만 그 시간대 API 지연(gemini 노드 1.4~1.7배) 때문일 가능성이 커 같은 밤에 다시 잼 (P-061)
#
# 두 번에 나눠 실행한다 (P-064: 채점 모델을 1·2 결과를 보고 정함)
#   .\scripts\run_3rd.ps1 -To 2                                  # 0 오프라인 검사, 1·2 2차 68건 새 지침 재채점 (10분 안쪽)
#   (1·2 결과 확인: 두 채점기 판정이 같으면 싼 쪽, 갈리면 사람 판정에 가까운 쪽)
#   .\scripts\run_3rd.ps1 -From 3 -Judge openai/gpt-6-sol       # 3~7 3차 측정, 채점 모델 지정 (빼면 멈춤)
#   중간에 멈췄으면 그 번호부터: .\scripts\run_3rd.ps1 -From 6 -Judge <모델>
# 3차는 새 랭퓨즈 프로젝트에서 검토한다 (P-065, 10.15 본인 결정). 3번 전에 .env의 랭퓨즈 키(LANGFUSE_PUBLIC_KEY·
# LANGFUSE_SECRET_KEY·LANGFUSE_BASE_URL)를 새 프로젝트 것으로 본인이 바꾼다. 1·2번(다시 채점)은 랭퓨즈에 쓰지 않아 상관없다.
#
# 순서
#   0 오프라인 검사 (실패하면 여기서 멈춤)
#   1 2차 답변 68건 다시 채점 · claude-sonnet-5.5 (P-055 새 채점 지침)
#   2 2차 답변 68건 다시 채점 · gpt-6-sol (P-055 새 채점 지침)
#   3 새 랭퓨즈 준비 · 점수 항목 + 지침 올리기 (langfuse_setup --prompts-only, 측정 trace에 지침 버전이 연결되게)
#   4 3차 측정 · C · 지금 D (전부 gemini) · 측정용 85턴 × 3회 (채점은 -Judge 모델, 첫 회만)
#   5 랭퓨즈 Dataset 실행 "3차-C/D" 연결 + 검토 대기열 "3차 측정 검토" (4번 결과, 첫 회 trace)
#   6 3차 측정 · 개선 D · gemini 전부 + 규칙 분류(--fast-path) · 측정용 85턴 × 3회
#   7 랭퓨즈 Dataset 실행 "3차개선-D" 연결 + 검토 대기열 "3차개선 측정 검토" (6번 결과)
#   8 3차 측정 · 안 2 · n0·n2·n3 = gpt-6-luna, n5·n6 = gemini, 규칙 분류 · 측정용 85턴 × 3회
#   9 랭퓨즈 Dataset 실행 "3차안2-D" 연결 + 검토 대기열 "3차안2 측정 검토" (8번 결과)
# 반복 실행은 --dataset-run과 함께 쓰지 않으므로, 대기열은 측정이 끝난 뒤 5·7·9번(langfuse_setup)으로 만든다.
# 5·7·9번은 results\test_*.xlsx 중 가장 최근 파일을 쓴다 (바로 앞 측정 결과). 대기열 수 상한에 걸리면 그 단계만 실패하고 다음으로 넘어간다.
# 가상환경을 켜지 않아도 .venv의 python을 직접 쓴다. 키는 .env에서 읽고 출력하지 않는다.
# 한 단계가 실패해도 다음 단계로 넘어가고, 끝에 단계별 완료·실패를 보여준다. 전체 기록은 results\run_3rd_<시각>.log

param([int]$From = 0, [int]$To = 9, [string]$Judge = "")

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "가상환경 python을 찾지 못했습니다: $py"; exit 1 }
if ($To -ge 4 -and $From -le 8 -and -not $Judge) {
    Write-Host "3차 측정(4·6·8번)은 채점 모델을 정해야 합니다. 먼저 -To 2로 1·2를 돌려 결과를 보고,"
    Write-Host "그다음 -From 3 -Judge <모델 ID>로 실행하세요. 예: .\scripts\run_3rd.ps1 -From 3 -Judge openai/gpt-6-sol"
    exit 1
}
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $root "results\run_3rd_$stamp.log"
Start-Transcript -Path $log | Out-Null

$review = "results\review_2차_20261014_183114.xlsx"
$abc = "results\test_ABC_google_gemini-3.8-flash_20261012_110507.xlsx"

$steps = @(
    @{ n = 0; name = "오프라인 검사"; stop = $true; args = @("tests\test_offline.py") },
    @{ n = 1; name = "2차 답변 다시 채점 · claude-sonnet-5.5 (P-055 기준)";
       args = @("eval\rejudge.py", "--result", $abc, "--judge-model", "anthropic/claude-sonnet-5.5", "--review", $review) },
    @{ n = 2; name = "2차 답변 다시 채점 · gpt-6-sol (P-055 기준)";
       args = @("eval\rejudge.py", "--result", $abc, "--judge-model", "openai/gpt-6-sol", "--review", $review) },
    @{ n = 3; name = "새 랭퓨즈 준비 · 점수 항목 + 지침 올리기";
       args = @("scripts\langfuse_setup.py", "--prompts-only") },
    @{ n = 4; name = "3차 측정 · C · 지금 D (전부 gemini) × 3회 · 채점 $Judge";
       args = @("eval\run_dev.py", "--set", "test", "--modes", "C", "D", "--repeat", "3", "--judge-model", $Judge) },
    @{ n = 5; name = "랭퓨즈 Dataset 연결 + 대기열 · 3차 (4번 결과)";
       args = @("scripts\langfuse_setup.py", "--run", "3차") },
    @{ n = 6; name = "3차 측정 · 개선 D (gemini + 규칙 분류) × 3회 · 채점 $Judge";
       args = @("eval\run_dev.py", "--set", "test", "--modes", "D", "--repeat", "3", "--fast-path", "--judge-model", $Judge) },
    @{ n = 7; name = "랭퓨즈 Dataset 연결 + 대기열 · 3차개선 (6번 결과)";
       args = @("scripts\langfuse_setup.py", "--run", "3차개선") },
    @{ n = 8; name = "3차 측정 · 안 2 (n0·n2·n3 luna + 규칙 분류) × 3회 · 채점 $Judge";
       args = @("eval\run_dev.py", "--set", "test", "--modes", "D", "--repeat", "3", "--node-models", "n0,n2,n3=openai/gpt-6-luna", "--fast-path", "--judge-model", $Judge) },
    @{ n = 9; name = "랭퓨즈 Dataset 연결 + 대기열 · 3차안2 (8번 결과)";
       args = @("scripts\langfuse_setup.py", "--run", "3차안2") }
)

$summary = @()
foreach ($s in $steps) {
    if ($s.n -lt $From -or $s.n -gt $To) { continue }
    Write-Host ""
    Write-Host ("===== {0}. {1} =====" -f $s.n, $s.name)
    $t0 = Get-Date
    & $py @($s.args) | Out-Host
    $code = $LASTEXITCODE
    $min = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
    $state = if ($code -eq 0) { "완료" } else { "실패 (코드 $code)" }
    $summary += ("{0}. {1} : {2} · {3}분" -f $s.n, $s.name, $state, $min)
    if ($code -ne 0 -and $s.stop) {
        Write-Host "오프라인 검사가 실패해서 멈춥니다. 위 실패 줄을 붙여 주세요."
        break
    }
}

Write-Host ""
Write-Host "===== 요약 ====="
$summary | ForEach-Object { Write-Host $_ }
Write-Host "기록 파일: $log"
if ($To -lt 3) { Write-Host "1·2 결과로 채점 모델을 정한 뒤, .env 랭퓨즈 키를 새 프로젝트로 바꾸고: .\scripts\run_3rd.ps1 -From 3 -Judge <모델 ID>" }
Stop-Transcript | Out-Null
