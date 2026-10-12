<#
Creates (or updates) the Windows scheduled task that runs the sync four times
a day, evenly spaced from 9:00 to 22:00, with no console window.

Run it from the project folder:
    powershell -ExecutionPolicy Bypass -File .\install_schedule.ps1

To change the times:  edit -Times below, or pass  -Times '08:00','14:00','20:00'
To remove it later:   Unregister-ScheduledTask -TaskName AssignmentSync -Confirm:$false
#>
param(
    [string]$TaskName = 'AssignmentSync',
    # 4 runs evenly spaced from 9:00 to 22:00 (every 4h20m).
    [string[]]$Times = @('09:00', '13:20', '17:40', '22:00')
)

$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot
$pythonw = Join-Path $dir '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $pythonw)) {
    throw "Can't find $pythonw. Run 'uv sync' in $dir first."
}

# pythonw.exe is Python without a console, so no window flashes up (or gets
# closed by accident, which kills the run). sync.py writes sync.log itself.
$action = New-ScheduledTaskAction -Execute $pythonw -Argument '-X utf8 sync.py' -WorkingDirectory $dir
$triggers = @($Times | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ })

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    # Keep the task's current settings, except: wait for a network connection.
    # The PC is often awake before Wi-Fi is, so catch-up runs after waking
    # failed with DNS errors.
    $settings = $existing.Settings
    $settings.RunOnlyIfNetworkAvailable = $true
    Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings | Out-Null
    $verb = 'Updated'
} else {
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 20)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings `
        -Description 'assignment-sync: pull Gradescope/Canvas deadlines into Todoist or Notion' | Out-Null
    $verb = 'Created'
}

$info = Get-ScheduledTaskInfo -TaskName $TaskName
"$verb task '$TaskName'. Runs daily at: $($Times -join ', ')"
"Next run: $($info.NextRunTime)"
