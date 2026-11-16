# 4차 측정 · 개발용 실행 묶음 (2026.11.12) · 밤새 한 번에 돌리기
#   .\scripts\run_4th.ps1
# 순서
#   0 오프라인 검사 + 랭퓨즈 연결 확인 (둘 중 하나라도 실패하면 여기서 멈춤)
#   1 4차 개발용 문항 전부: 규칙 · 검수 단독 · 강제 · 자연 3회 (scripts\run_4th_261112.py). 2시간 반 안팎
#   2 1번에서 API 오류가 난 대화만 다시 돌리기 (같은 결과 폴더에 이어서). 오류가 없으면 결과 엑셀만 다시 만든다
#   3 기존 개발용 61턴 × 3회 · 설정 D + 규칙 분류 (eval\run_dev.py). 40분 안팎
# 중간부터: .\scripts\run_4th.ps1 -From 2   (2번은 가장 최근 run4th_개발용_ 폴더를 이어서 돈다)
# 도는 동안 PC가 절전으로 들어가지 않게 막고, 끝나면 원래대로 돌려 둔다 (화면은 꺼져도 됨).
#   노트북 덮개를 닫으면 덮개 설정에 따라 잠들 수 있다. 전원을 꽂고 덮개는 열어 둔다
# 키는 .env에서 읽고 출력하지 않는다. 랭퓨즈에 기록한다 (11.12 바꿈). 돌리기 전에 Docker Desktop을 켜서 langfuse가 떠 있어야 한다.
#   랭퓨즈 없이 돌리려면 .\scripts\run_4th.ps1 -NoLangfuse
# 한 단계가 실패해도 다음 단계로 넘어가고(0번 제외), 끝에 단계별 완료 · 실패를 보여준다. 전체 기록은 results\run_4th_<시각>.log

param([int]$From = 0, [int]$To = 3, [switch]$NoLangfuse)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { Write-Host "가상환경 python을 찾지 못했습니다: $py"; exit 1 }
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path (Join-Path $root "results") | Out-Null
$log = Join-Path $root "results\run_4th_$stamp.log"
Start-Transcript -Path $log | Out-Null

# 절전 막기 (ES_CONTINUOUS | ES_SYSTEM_REQUIRED). 끝나면 ES_CONTINUOUS만 남겨 원래대로
Add-Type -Namespace Win32 -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
[Win32.Power]::SetThreadExecutionState([uint32]2147483649) | Out-Null

function Latest-Run {
    Get-ChildItem (Join-Path $root "results") -Directory -Filter "run4th_개발용_*" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
}

$lfOff = @()
if ($NoLangfuse) { $lfOff = @("--no-langfuse") }

$summary = @()
$before = Latest-Run
try {
    foreach ($n in $From..$To) {
        $t0 = Get-Date
        # (switch 안의 continue는 바깥 반복을 넘기지 않아서 if로 나눈다)
        $skip = $false
        if ($n -eq 0) { $name = "오프라인 검사"; $args_ = @("tests\test_offline.py") }
        elseif ($n -eq 1) { $name = "4차 개발용 문항 전부 (규칙 · 검수 단독 · 강제 · 자연 3회)"; $args_ = @("scripts\run_4th_261112.py") + $lfOff }
        elseif ($n -eq 2) {
            $name = "오류 난 대화 다시 돌리기"
            $run = Latest-Run
            if (-not $run -or ($From -le 1 -and $before -and $run.Name -eq $before.Name)) {
                $summary += "2. $name : 건너뜀 (1번 결과 폴더가 없음)"
                $skip = $true
            } else {
                $args_ = @("scripts\run_4th_261112.py", "--resume", ("results\" + $run.Name)) + $lfOff
            }
        }
        elseif ($n -eq 3) { $name = "기존 개발용 61턴 × 3회 · 설정 D + 규칙 분류"; $args_ = @("eval\run_dev.py", "--mode", "D", "--fast-path", "--repeat", "3") + $lfOff }
        else { $skip = $true }
        if ($skip) { continue }
        Write-Host ""
        Write-Host ("===== {0}. {1} =====" -f $n, $name)
        & $py @args_ | Out-Host
        $code = $LASTEXITCODE
        $min = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
        $state = if ($code -eq 0) { "완료" } else { "실패 (코드 $code)" }
        $summary += ("{0}. {1} : {2} · {3}분" -f $n, $name, $state, $min)
        if ($n -eq 0 -and $code -ne 0) {
            Write-Host "오프라인 검사가 실패해서 멈춥니다. 위 실패 줄을 붙여 주세요."
            break
        }
        if ($n -eq 0 -and -not $NoLangfuse) {
            & $py scripts\run_4th_261112.py --check-langfuse | Out-Host
            if ($LASTEXITCODE -ne 0) {
                $summary += "0. 랭퓨즈 연결 확인 : 실패"
                Write-Host "랭퓨즈에 닿지 않아 멈춥니다. Docker Desktop을 켜고 Containers에서 langfuse가 실행 중인지 본 뒤 다시 돌려 주세요."
                Write-Host "(랭퓨즈 없이 돌리려면 .\scripts\run_4th.ps1 -NoLangfuse)"
                break
            }
            $summary += "0. 랭퓨즈 연결 확인 : 연결됨"
        }
    }
}
finally {
    [Win32.Power]::SetThreadExecutionState([uint32]2147483648) | Out-Null
    Write-Host ""
    Write-Host "===== 요약 ====="
    $summary | ForEach-Object { Write-Host $_ }
    $run = Latest-Run
    if ($run) { Write-Host ("4차 결과: results\" + $run.Name + "\결과.xlsx") }
    Write-Host "기록 파일: $log"
    Stop-Transcript | Out-Null
}
