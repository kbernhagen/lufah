""" lufah __main__ """

try:
    from lufah.cli_typer import main
except ImportError:
    from lufah.cli import main

main()
