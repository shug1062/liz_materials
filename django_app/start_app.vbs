Set objShell = CreateObject("WScript.Shell")
strPath = objShell.CurrentDirectory

' Check if venv exists
Set fso = CreateObject("Scripting.FileSystemObject")
venvPath = strPath & "\.venv\Scripts\python.exe"

If Not fso.FileExists(venvPath) Then
    ' Create venv and install requirements
    objShell.Run "cmd /c cd /d """ & strPath & """ && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt", 0, True
End If

' Run migrations and collect static
objShell.Run "cmd /c cd /d """ & strPath & """ && .venv\Scripts\python manage.py migrate --noinput && .venv\Scripts\python manage.py collectstatic --noinput", 0, True

' Start the app (hidden window, 0 = hide)
objShell.Run "cmd /c cd /d """ & strPath & """ && .venv\Scripts\python -m waitress --listen=0.0.0.0:8000 studio.wsgi:application", 0, False

' Wait for app to start
WScript.Sleep 3000

' Open browser
objShell.Run "start http://localhost:8000/sales/", 1, False
