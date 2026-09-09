param([switch]$Install)

$ErrorActionPreference = 'Stop'
$harborRoot = Split-Path -Parent $PSScriptRoot
$harborExecutable = Join-Path $harborRoot '.venv\Scripts\harbor.exe'
if (-not (Test-Path -LiteralPath $harborExecutable)) {
    throw 'Run uv sync in this checkout before installing the daemon.'
}

if ($Install) {
    $harborUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $harborAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
        '-NoProfile -NonInteractive -WindowStyle Hidden -File "' + $PSCommandPath + '"'
    ) -WorkingDirectory $harborRoot
    $harborTrigger = New-ScheduledTaskTrigger -AtLogOn -User $harborUser
    $harborPrincipal = New-ScheduledTaskPrincipal -UserId $harborUser -LogonType Interactive -RunLevel Limited
    $harborSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName 'CodexHarbor-Daemon' -Action $harborAction `
        -Trigger $harborTrigger -Principal $harborPrincipal -Settings $harborSettings `
        -Description 'Run the local Harbor scheduler after user login; retain existing recovery tasks.'
    exit 0
}

$harborLogRoot = Join-Path $env:LOCALAPPDATA 'CodexHarbor\logs'
New-Item -ItemType Directory -Path $harborLogRoot -Force | Out-Null
$harborStamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$harborProcess = Start-Process -FilePath $harborExecutable -ArgumentList 'daemon' `
    -WorkingDirectory $harborRoot -WindowStyle Hidden -Wait -PassThru `
    -RedirectStandardOutput (Join-Path $harborLogRoot "daemon-$harborStamp.out.log") `
    -RedirectStandardError (Join-Path $harborLogRoot "daemon-$harborStamp.err.log")
exit $harborProcess.ExitCode
