$WshShell = New-Object -comObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($WshShell.SpecialFolders("Desktop") + "\라씨 매매비서.lnk")
$Shortcut.TargetPath = (Resolve-Path "venv\Scripts\pythonw.exe").Path
$Shortcut.Arguments = "desktop_app.py"
$Shortcut.WorkingDirectory = (Get-Location).Path
$Shortcut.WindowStyle = 7  # 최소화 상태로 시작 (검은 창 숨기기)
$Shortcut.Save()
Write-Host "바탕화면에 바로가기가 생성되었습니다!"
