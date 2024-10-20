""" lufah __main__ """

try:
    from lufah.cli_typer import main
except ImportError:
    from lufah.cli_argparse import main

main()
