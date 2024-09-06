@ECHO OFF

set VENV=.venv
set PYTHON=%VENV%\Scripts\python

if "%1" == "" goto help

if "%1" == "help" (
	:help
	echo.Please use `make ^<target^>` where ^<target^> is one of
	echo.  install-user  install via pipx for current user
	goto end
)

if "%1" == "install-user" (
	echo. py -m venv %VENV%
	py -m venv %VENV%
	%PYTHON% -m ensurepip
	%PYTHON% -m pip install pipx
	%PYTHON% -m pipx install --force .
	%PYTHON% -m pipx ensurepath
	goto end
)

:end
