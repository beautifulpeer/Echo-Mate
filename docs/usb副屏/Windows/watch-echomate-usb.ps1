$ErrorActionPreference = 'SilentlyContinue'
$wasConnected = $false

while ($true) {
    $connected = $null -ne (Get-PnpDevice -PresentOnly | Where-Object {
        $_.InstanceId -like 'USB\VID_2207&PID_1005&MI_00*'
    } | Select-Object -First 1)

    if ($connected -and -not $wasConnected) {
        # Let usbser and the indirect-display driver finish enumeration.
        Start-Sleep -Seconds 2
        Start-Process -FilePath "$env:WINDIR\System32\DisplaySwitch.exe" `
            -ArgumentList '/extend' -WindowStyle Hidden
    }

    $wasConnected = $connected
    Start-Sleep -Seconds 2
}
