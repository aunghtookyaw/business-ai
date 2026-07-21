$ErrorActionPreference = "Stop"
$PackageDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$Executable = Join-Path $PackageDirectory "BigShot Business OS.exe"

if (-not (Test-Path $Executable)) {
    throw "BigShot Business OS.exe was not found. Run BUILD_WINDOWS.bat first."
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "BigShot Business OS.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Executable
$Shortcut.WorkingDirectory = $PackageDirectory
$Shortcut.Description = "Open BigShot Business OS"
$Shortcut.Save()

Write-Host "Created: $ShortcutPath"
