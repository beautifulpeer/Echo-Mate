$ErrorActionPreference = 'Stop'
try {
    Stop-ScheduledTask EchoMateUsbDisplay -ErrorAction SilentlyContinue
    Get-Process IddSampleApp -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-ScheduledTask EchoMateUsbDisplay
    Start-Sleep -Seconds 2
    Start-Process "$env:WINDIR\System32\DisplaySwitch.exe" -ArgumentList '/extend'
    Write-Host 'SUCCESS：推流已重启。' -ForegroundColor Green
} catch { Write-Host ('FAILED：' + $_.Exception.Message) -ForegroundColor Red }
Read-Host '按回车关闭'
