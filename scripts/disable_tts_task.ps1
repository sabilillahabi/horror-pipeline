# Stop the laptop from using the Gemini keys: disable the hourly TTS retry task.
# Run in PowerShell (no admin needed for a task you created):
#   powershell -ExecutionPolicy Bypass -File scripts\disable_tts_task.ps1
param([string]$TaskName = "HorrorPipeline-JuruKunci-TTS")

$t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $t) {
    Write-Host "Task '$TaskName' tidak ada (sudah dihapus) - laptop tidak memakai key Gemini lewat task ini."
    exit 0
}
Disable-ScheduledTask -TaskName $TaskName | Out-Null
# stop a run that is in progress right now, if any
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$t = Get-ScheduledTask -TaskName $TaskName
$i = Get-ScheduledTaskInfo -TaskName $TaskName
Write-Host ("Task '{0}': State = {1} (harus Disabled) | terakhir jalan {2} | berikutnya {3}" -f `
    $TaskName, $t.State, $i.LastRunTime, $i.NextRunTime)
if ($t.State -ne "Disabled") { exit 1 }
