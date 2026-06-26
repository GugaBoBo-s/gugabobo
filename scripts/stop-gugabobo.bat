@echo off
setlocal

echo [gugabobo] Stopping running API processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*gugabobo*api*' }; foreach ($p in $procs) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; Write-Host ('Stopped PID ' + $p.ProcessId) } catch { Write-Host ('Failed PID ' + $p.ProcessId + ': ' + $_.Exception.Message) } }"

echo [gugabobo] Done.
endlocal
