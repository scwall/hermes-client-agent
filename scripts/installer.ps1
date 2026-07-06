<#
.SYNOPSIS
    Hermes Agent Windows installer / uninstaller.

.DESCRIPTION
    Installs hermes-agent.exe as a startup application.
    Optionally registers it as a Windows service.

.PARAMETER Uninstall
    Remove the installed agent, registry key, and optional service.

.PARAMETER InstallPath
    Target installation directory (default: C:\Program Files\HermesAgent\).

.PARAMETER InstallService
    Register hermes-agent.exe as a Windows service via sc.exe.

.EXAMPLE
    .\installer.ps1

.EXAMPLE
    .\installer.ps1 -Uninstall

.EXAMPLE
    .\installer.ps1 -InstallService
#>

param(
    [switch]$Uninstall,
    [string]$InstallPath = "${env:ProgramFiles}\HermesAgent",
    [switch]$InstallService
)

$ErrorActionPreference = "Stop"

$displayName = "Hermes Agent"
$exeName = "hermes-agent.exe"
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$regName = "HermesAgent"

function Test-Admin {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object System.Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Host "ERROR: This script must be run as Administrator." -ForegroundColor Red
        Write-Host "Right-click PowerShell and select 'Run as Administrator'."
        exit 1
    }
}

function Invoke-Uninstall {
    Write-Host "Uninstalling Hermes Agent..." -ForegroundColor Yellow

    Get-Process -Name "hermes-agent" -ErrorAction SilentlyContinue | Stop-Process -Force

    if ($InstallService) {
        Write-Host "Removing Windows service..."
        sc.exe stop "HermesAgent" *>$null
        sc.exe delete "HermesAgent" *>$null
    }

    if (Test-Path $regPath) {
        $prop = Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue
        if ($prop) {
            Remove-ItemProperty -Path $regPath -Name $regName -Force
            Write-Host "Removed registry run key."
        }
    }

    $startMenu = [Environment]::GetFolderPath("StartMenu") + "\Programs\Hermes Agent.lnk"
    if (Test-Path $startMenu) {
        Remove-Item -LiteralPath $startMenu -Force
        Write-Host "Removed Start Menu shortcut."
    }

    if (Test-Path $InstallPath) {
        Remove-Item -Recurse -Force -LiteralPath $InstallPath
        Write-Host "Removed installation directory: $InstallPath"
    }

    Write-Host "Uninstall complete." -ForegroundColor Green
}

function Invoke-Install {
    Write-Host "Installing Hermes Agent..." -ForegroundColor Cyan
    Write-Host "Target: $InstallPath"

    $exeSource = Join-Path (Join-Path $PSScriptRoot "..") "dist\$exeName"
    if (-not (Test-Path $exeSource)) {
        Write-Host "ERROR: $exeSource not found." -ForegroundColor Red
        Write-Host "Run 'python build_exe.py' first to build the executable."
        exit 1
    }

    New-Item -ItemType Directory -Force -Path $InstallPath | Out-Null
    Copy-Item -Force -LiteralPath $exeSource -Destination $InstallPath

    $iconSource = Join-Path (Join-Path $PSScriptRoot "..") "icon.ico"
    if (Test-Path $iconSource) {
        Copy-Item -Force -LiteralPath $iconSource -Destination $InstallPath
    }

    New-Item -Path $regPath -Force | Out-Null
    $exeFull = Join-Path $InstallPath $exeName
    Set-ItemProperty -Path $regPath -Name $regName -Value "`"$exeFull`""

    $startMenuDir = [Environment]::GetFolderPath("StartMenu") + "\Programs"
    $wsh = New-Object -ComObject WScript.Shell
    $shortcut = $wsh.CreateShortcut("$startMenuDir\Hermes Agent.lnk")
    $shortcut.TargetPath = $exeFull
    $shortcut.Save()

    if ($InstallService) {
        Write-Host "Registering Windows service..."
        sc.exe create "HermesAgent" binPath= "`"$exeFull`"" start= auto *>$null
        sc.exe description "HermesAgent" "Hermes Remote Control Agent" *>$null
        Write-Host "Service created. Start with: sc.exe start HermesAgent"
    }

    Write-Host ""
    Write-Host "Hermes Agent installed successfully." -ForegroundColor Green
    Write-Host "It will start automatically at login."
    Write-Host "Start it now with: & `"$exeFull`""
}

Test-Admin

if ($Uninstall) {
    Invoke-Uninstall
} else {
    Invoke-Install
}
