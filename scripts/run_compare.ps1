# 모델 비교 한 번에 실행 (P-052, 2026.10.15)
# 채점 기준(P-051)을 고정한 뒤 남은 실행 5개를 정해진 순서로 한 번에 돌린다.
#
# 실행 (stock-term-agent 폴더에서, PowerShell)
#   .\scripts\run_compare.ps1            # 0번부터 끝까지
#   .\scripts\run_compare.ps1 -From 4    # 중간에 멈췄으면 그 번호부터 다시
#
# 순서
#   0 오프라인 검사 (실패하면 여기서 멈춤)
#   1 2차 답변 68건 다시 채점 · claude-sonnet-5.5 (새 기준)
#   2 2차 답변 68건 다시 채점 · gpt-6-sol (새 기준)
#   3 gemini B·C·D 측정 답변 다시 채점 · claude-sonnet-5.5 (새 기준, 모델 비교 기준선)
#   4 모델 비교 측정 · gpt-5.4-mini · 측정용 B·C·D
#   5 모델 비교 측정 · gpt-6-luna · 측정용 B·C·D
# 가상환경을 켜지 않아도 .venv의 python을 직접 쓴다. 키는 .env에서 읽고 출력하지 않는다.
# 한 단계가 실패해도 다음 단계로 넘어가고, 끝에 단계별 완료·실패를 보여준다. 전체 기록은 results\run_compare_<시각>.log

param([int]$From = 0)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "가상환경 python을 찾지 못했습니다: $py"; exit 1 }
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"  # 진행 상황이 끝에 몰려 나오지 않고 바로바로 보이게 (10.15 추가)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$log = Join-Path $root "results\run_compare_$stamp.log"
Start-Transcript -Path $log | Out-Null

$review = "results\review_2차_20261014_183114.xlsx"
$abc = "results\test_ABC_google_gemini-3.8-flash_20261012_110507.xlsx"
$bcd = "results\test_BCD_google_gemini-3.8-flash_20261012_173514.xlsx"

$steps = @(
    @{ n = 0; name = "오프라인 검사"; stop = $true; args = @("tests\test_offline.py") },
    @{ n = 1; name = "2차 답변 다시 채점 · claude-sonnet-5.5 (새 기준)";
       args = @("eval\rejudge.py", "--result", $abc, "--judge-model", "anthropic/claude-sonnet-5.5", "--review", $review) },
    @{ n = 2; name = "2차 답변 다시 채점 · gpt-6-sol (새 기준)";
       args = @("eval\rejudge.py", "--result", $abc, "--judge-model", "openai/gpt-6-sol", "--review", $review) },
    @{ n = 3; name = "gemini B·C·D 측정 답변 다시 채점 · claude-sonnet-5.5 (새 기준)";
       args = @("eval\rejudge.py", "--result", $bcd, "--judge-model", "anthropic/claude-sonnet-5.5", "--review", $review) },
    @{ n = 4; name = "모델 비교 측정 · gpt-5.4-mini";
       args = @("eval\run_dev.py", "--set", "test", "--modes", "B", "C", "D", "--model", "openai/gpt-5.4-mini") },
    @{ n = 5; name = "모델 비교 측정 · gpt-6-luna";
       args = @("eval\run_dev.py", "--set", "test", "--modes", "B", "C", "D", "--model", "openai/gpt-6-luna") }
)

$summary = @()
foreach ($s in $steps) {
    if ($s.n -lt $From) { continue }
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
Write-Host "실패한 단계가 있으면 그 번호부터: .\scripts\run_compare.ps1 -From <번호>"
Stop-Transcript | Out-Null
