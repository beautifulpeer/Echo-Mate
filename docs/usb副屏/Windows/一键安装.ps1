$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$driver = Join-Path $root 'driver'
$inf = Join-Path $driver 'IddSampleDriver.inf'
$helper = Join-Path $driver 'IddSampleApp.exe'
$cert = Join-Path $root 'EchoMateUsbDisplayTest.cer'
$watcher = Join-Path $root 'watch-echomate-usb.ps1'

try {
    if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw '请右键“一键安装.cmd”，选择以管理员身份运行。'
    }

    certutil.exe -f -addstore Root $cert | Out-Host
    if ($LASTEXITCODE -ne 0) { throw '根证书导入失败。' }
    certutil.exe -f -addstore TrustedPublisher $cert | Out-Host
    if ($LASTEXITCODE -ne 0) { throw '发布者证书导入失败。' }
    pnputil.exe /add-driver $inf /install | Out-Host
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 259) { throw '显示驱动安装失败。' }

    $senderAction = New-ScheduledTaskAction -Execute $helper -WorkingDirectory $driver
    $senderTrigger = New-ScheduledTaskTrigger -AtStartup
    $senderTrigger.Delay = 'PT15S'
    $senderSettings = New-ScheduledTaskSettingsSet -RestartCount 999 `
        -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable
    Register-ScheduledTask -TaskName 'EchoMateUsbDisplay' -Action $senderAction `
        -Trigger $senderTrigger -Settings $senderSettings -User SYSTEM `
        -RunLevel Highest -Force | Out-Null

    $userId = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $watchAction = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
        '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $watcher + '"')
    $watchTrigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
    $watchPrincipal = New-ScheduledTaskPrincipal -UserId $userId `
        -LogonType Interactive -RunLevel Highest
    Register-ScheduledTask -TaskName 'EchoMateUsbAutoExtend' -Action $watchAction `
        -Trigger $watchTrigger -Principal $watchPrincipal `
        -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew) `
        -Force | Out-Null

    Stop-ScheduledTask EchoMateUsbDisplay -ErrorAction SilentlyContinue
    Get-Process IddSampleApp -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-ScheduledTask EchoMateUsbDisplay
    Start-ScheduledTask EchoMateUsbAutoExtend
    Start-Sleep -Seconds 4
    Start-Process "$env:WINDIR\System32\DisplaySwitch.exe" -ArgumentList '/extend'

    Write-Host 'SUCCESS：驱动、发送端、自动扩展均已安装。' -ForegroundColor Green
    Write-Host ('Sender: ' + (Get-ScheduledTask EchoMateUsbDisplay).State)
    Write-Host ('Auto extend: ' + (Get-ScheduledTask EchoMateUsbAutoExtend).State)
}
catch {
    Write-Host ('FAILED：' + $_.Exception.Message) -ForegroundColor Red
}
Read-Host '按回车关闭'
