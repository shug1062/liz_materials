' Run once: puts a "Silver Bird Studio" shortcut on the Desktop that can be pinned to the taskbar.
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)

Set link = shell.CreateShortcut(shell.SpecialFolders("Desktop") & "\Silver Bird Studio.lnk")
' Windows only lets shortcuts to programs be pinned, so target cmd.exe rather than the .bat itself.
link.TargetPath = shell.ExpandEnvironmentStrings("%ComSpec%")
link.Arguments = "/c """"" & appDir & "\start_windows.bat"""""
link.WorkingDirectory = appDir
link.WindowStyle = 7
link.IconLocation = appDir & "\studio.ico"
link.Description = "Start The Silver Bird studio app"
link.Save

MsgBox "A 'Silver Bird Studio' shortcut is now on your Desktop." & vbCrLf & vbCrLf & _
    "To add it to the taskbar, right-click it and choose Pin to taskbar" & vbCrLf & _
    "(on Windows 11: Show more options, then Pin to taskbar).", vbInformation, "Silver Bird Studio"
