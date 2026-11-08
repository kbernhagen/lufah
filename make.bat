@ECHO OFF

set VENV=.venv
set PYTHON=%VENV%\Scripts\python.exe
set UV=%VENV%\Scripts\uv.exe

if "%1"=="" goto help
if "%1"=="help" goto help

if "%1"=="install-user" (
	call :bootstrap
	"%UV%" tool uninstall lufah
	"%PYTHON%" -m pipx uninstall lufah
	if errorlevel 1 exit /b 1
	"%UV%" tool install --force .
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
python -c "import sys; print('Python ' + sys.version.split()[0]); sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 (
	echo Python 3.11 or newer is required.
	exit /b 1
)
python -m venv "%VENV%"
if errorlevel 1 exit /b 1
"%PYTHON%" -m pip install "pip @ https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl#sha256=fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70"
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
