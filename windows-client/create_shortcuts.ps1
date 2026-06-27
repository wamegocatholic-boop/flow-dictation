$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("$env:USERPROFILE\Desktop\FlowDictation.lnk")
$Shortcut.TargetPath = "C:\Users\z_tes\.gemini\antigravity\scratch\flow-dictation\windows-client\dist\FlowDictation.exe"
$Shortcut.WorkingDirectory = "C:\Users\z_tes\.gemini\antigravity\scratch\flow-dictation\windows-client\dist"
$Shortcut.Save()

$StartupShortcut = $WshShell.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Flow Dictation.lnk")
$StartupShortcut.TargetPath = "C:\Users\z_tes\.gemini\antigravity\scratch\flow-dictation\windows-client\dist\FlowDictation.exe"
$StartupShortcut.WorkingDirectory = "C:\Users\z_tes\.gemini\antigravity\scratch\flow-dictation\windows-client\dist"
$StartupShortcut.Save()
