@ECHO OFF

set VENV=.venv
set PYTHON=%VENV%\Scripts\python.exe
set UV=%VENV%\Scripts\uv.exe

if "%1"=="" goto help
if "%1"=="help" goto help

if "%1"=="install-user" (
	call :bootstrap
	if errorlevel 1 exit /b 1
	"%UV%" tool uninstall lufah
	"%PYTHON%" -m pipx uninstall lufah
	"%UV%" tool install --managed-python -p ">=3.15.2,<3.16" --force .
	if errorlevel 1 exit /b 1
	"%PYTHON%" -m pipx ensurepath
	if errorlevel 1 exit /b 1
	goto :eof
)

if "%1"=="uninstall-user" (
	call :bootstrap
	if errorlevel 1 exit /b 1
	"%UV%" tool uninstall lufah
	if errorlevel 1 echo Note: uv uninstall failed
	"%PYTHON%" -m pipx uninstall lufah
	if errorlevel 1 echo Note: pipx uninstall failed
	goto :eof
)

:help
echo.Please use `make ^<target^>` where ^<target^> is one of
echo.  install-user    install via uv for current user
echo.  uninstall-user  uninstall via uv and pipx for current user
exit /b 0

:bootstrap
REM require a patched python 3.11-3.15 for safe bootstrap
python -c "import sys; ^
version = sys.version_info; ^
patched_minor_floors = {11: 18, 12: 16, 13: 18, 14: 10, 15: 2}; ^
is_supported = ( ^
    version.major == 3 and ^
    version.minor in patched_minor_floors and ^
    version.micro >= patched_minor_floors[version.minor] ^
); ^
print('Python ' + sys.version.split()[0]); ^
sys.exit(not is_supported)"
if errorlevel 1 (
	echo Patched Python 3.11-3.15 is required.
	exit /b 1
)
python -m venv "%VENV%"
if errorlevel 1 exit /b 1
"%PYTHON%" -m pip install --upgrade "pip>=26.2.2"
if errorlevel 1 exit /b 1
"%PYTHON%" -m pip install "pipx>=1.18.7" "uv>=0.13.6"
if errorlevel 1 exit /b 1
"%PYTHON%" -m pipx ensurepath
if errorlevel 1 exit /b 1
"%PYTHON%" -m pipx install --upgrade uv
if errorlevel 1 echo Note: uv install/upgrade failed
exit /b 0
