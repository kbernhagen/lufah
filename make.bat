@ECHO OFF

set VENV=.venv
set PYTHON=%VENV%\Scripts\python

if "%1" == "" goto help

if "%1" == "help" (
	:help
	echo.Please use `make ^<target^>` where ^<target^> is one of
	echo.  install-user    install via pipx for current user
	echo.  uninstall-user  uninstall via pipx for current user
	echo.  install-uv      install uv via pipx for current user
	goto end
)

if "%1" == "install-user" (
	echo. python -m venv %VENV%
	python -m venv %VENV%
	%PYTHON% -m ensurepip
	%PYTHON% -m pip install pipx
	%PYTHON% -m pipx install --force .
	%PYTHON% -m pipx ensurepath
	goto end
)

if "%1" == "uninstall-user" (
	echo. py -m venv %VENV%
	py -m venv %VENV%
	%PYTHON% -m ensurepip
	%PYTHON% -m pip install pipx
	%PYTHON% -m pipx uninstall lufah
	goto end
)

if "%1" == "install-uv" (
	echo. python -m venv %VENV%
	python -m venv %VENV%
	%PYTHON% -m ensurepip
	%PYTHON% -m pip install pipx
	%PYTHON% -m pipx install uv
	%PYTHON% -m pipx ensurepath
	echo. You may need to open a new terminal to use uv
	goto end
)

:end
