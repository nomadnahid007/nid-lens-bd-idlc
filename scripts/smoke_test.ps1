# End-to-end smoke test for NID Lens BD. Assumes the API is already running
# (e.g. `docker compose up`) and reachable at $BaseUrl.
#
# Uses System.Net.Http.HttpClient directly (not Invoke-WebRequest -Form,
# which requires PowerShell 6.1+) so this runs unmodified on both Windows
# PowerShell 5.1 and PowerShell 7.
#
# Usage: powershell -File scripts/smoke_test.ps1 [-BaseUrl http://localhost:8000]

param(
    [string]$BaseUrl = "http://localhost:8000"
)

Add-Type -AssemblyName System.Net.Http

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SamplesDir = Join-Path $ScriptDir "..\fixtures\samples"
$Front = Join-Path $SamplesDir "nid_front_synthetic.png"
$Back = Join-Path $SamplesDir "nid_back_synthetic.png"

$Pass = 0
$Fail = 0

function Check-Result {
    param(
        [string]$Name,
        [int]$ExpectedCode,
        [int]$ActualCode,
        [string]$BodyContains = $null,
        [string]$Body = $null
    )

    if ($ActualCode -ne $ExpectedCode) {
        Write-Output "FAIL  $Name (expected HTTP $ExpectedCode, got $ActualCode)"
        $script:Fail++
        return
    }

    if ($BodyContains -and ($Body -notlike "*$BodyContains*")) {
        Write-Output "FAIL  $Name (HTTP $ActualCode OK, but response missing '$BodyContains')"
        $script:Fail++
        return
    }

    Write-Output "PASS  $Name (HTTP $ActualCode)"
    $script:Pass++
}

function Invoke-Get {
    param([string]$Uri)
    $client = New-Object System.Net.Http.HttpClient
    try {
        $resp = $client.GetAsync($Uri).GetAwaiter().GetResult()
        $body = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        return @{ Code = [int]$resp.StatusCode; Body = $body }
    } catch {
        return @{ Code = 0; Body = "" }
    } finally {
        $client.Dispose()
    }
}

function Invoke-MultipartPost {
    param([string]$Uri, [hashtable]$Files)
    $client = New-Object System.Net.Http.HttpClient
    $content = New-Object System.Net.Http.MultipartFormDataContent
    $streams = New-Object System.Collections.ArrayList
    try {
        foreach ($key in $Files.Keys) {
            $path = $Files[$key]
            $fs = [System.IO.File]::OpenRead($path)
            [void]$streams.Add($fs)
            $sc = New-Object System.Net.Http.StreamContent($fs)
            $sc.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse("image/png")
            $content.Add($sc, $key, [System.IO.Path]::GetFileName($path))
        }
        $resp = $client.PostAsync($Uri, $content).GetAwaiter().GetResult()
        $body = $resp.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        return @{ Code = [int]$resp.StatusCode; Body = $body }
    } catch {
        return @{ Code = 0; Body = "" }
    } finally {
        foreach ($s in $streams) { $s.Dispose() }
        $content.Dispose()
        $client.Dispose()
    }
}

Write-Output "NID Lens BD smoke test -- target: $BaseUrl"
Write-Output ""

if (-not (Test-Path $Front) -or -not (Test-Path $Back)) {
    Write-Output "Sample images not found at $SamplesDir."
    Write-Output "Run: python scripts/generate_samples.py"
    exit 1
}

# 1. Health check
$r = Invoke-Get -Uri "$BaseUrl/health"
Check-Result -Name "GET /health" -ExpectedCode 200 -ActualCode $r.Code -BodyContains '"status"' -Body $r.Body

# 2. Full extraction, both images present
$r = Invoke-MultipartPost -Uri "$BaseUrl/api/v1/nid/extract" -Files @{ front = $Front; back = $Back }
Check-Result -Name "POST /api/v1/nid/extract (full)" -ExpectedCode 200 -ActualCode $r.Code -BodyContains '"status":"complete"' -Body $r.Body

# 3. Missing back image -> 422
$r = Invoke-MultipartPost -Uri "$BaseUrl/api/v1/nid/extract" -Files @{ front = $Front }
Check-Result -Name "POST /api/v1/nid/extract (missing back)" -ExpectedCode 422 -ActualCode $r.Code

# 4. Sample image routes used by the UI
$r = Invoke-Get -Uri "$BaseUrl/api/v1/samples/front"
Check-Result -Name "GET /api/v1/samples/front" -ExpectedCode 200 -ActualCode $r.Code

$r = Invoke-Get -Uri "$BaseUrl/api/v1/samples/back"
Check-Result -Name "GET /api/v1/samples/back" -ExpectedCode 200 -ActualCode $r.Code

Write-Output ""
Write-Output "Results: $Pass passed, $Fail failed"

if ($Fail -ne 0) { exit 1 } else { exit 0 }
