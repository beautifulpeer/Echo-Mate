param([Parameter(Mandatory = $true)][string]$Port)
$ErrorActionPreference = 'Stop'
if (-not ('EchoMateSerialConsole.Native' -as [type])) {
    Add-Type @'
using System;
using System.Runtime.InteropServices;
namespace EchoMateSerialConsole {
    public static class Native {
        [DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int n);
        [DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out uint mode);
        [DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, uint mode);
    }
}
'@
}
$serial = New-Object System.IO.Ports.SerialPort $Port,115200,None,8,one
$serial.Encoding = New-Object System.Text.UTF8Encoding -ArgumentList $false
$serial.Handshake = [System.IO.Ports.Handshake]::None
$serial.DtrEnable = $true
$serial.RtsEnable = $true
$serial.WriteTimeout = 1000
$handle = [EchoMateSerialConsole.Native]::GetStdHandle(-11)
[uint32]$oldMode = 0
$hasMode = [EchoMateSerialConsole.Native]::GetConsoleMode($handle, [ref]$oldMode)
$oldControlC = [Console]::TreatControlCAsInput
try {
    $serial.Open()
    if ($hasMode) {
        [void][EchoMateSerialConsole.Native]::SetConsoleMode($handle, $oldMode -bor 4)
    }
    [Console]::TreatControlCAsInput = $true
    Write-Host "Connected to $Port, 115200 8N1. Press Ctrl+] to disconnect."
    $serial.Write("`r")
    while ($true) {
        if ($serial.BytesToRead -gt 0) {
            [Console]::Write($serial.ReadExisting())
        }
        if ([Console]::KeyAvailable) {
            $key = [Console]::ReadKey($true)
            if ([int]$key.KeyChar -eq 29) { break }
            $text = switch ($key.Key) {
                'UpArrow'    { [string][char]27 + '[A' }
                'DownArrow'  { [string][char]27 + '[B' }
                'RightArrow' { [string][char]27 + '[C' }
                'LeftArrow'  { [string][char]27 + '[D' }
                'Home'      { [string][char]27 + '[H' }
                'End'       { [string][char]27 + '[F' }
                'Delete'    { [string][char]27 + '[3~' }
                'Enter'     { "`r" }
                'Backspace' { [string][char]127 }
                default     { if ($key.KeyChar -ne [char]0) { [string]$key.KeyChar } }
            }
            if ($text) { $serial.Write([string]$text) }
        }
        Start-Sleep -Milliseconds 10
    }
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
    [Console]::TreatControlCAsInput = $oldControlC
    if ($hasMode) { [void][EchoMateSerialConsole.Native]::SetConsoleMode($handle, $oldMode) }
}
