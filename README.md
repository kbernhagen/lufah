# lufah

Little Utility for FAH v8

This is a python command line utility script that should
work on macOS, Linux, and Windows.


## Requirements

- python3
- pip3 install websockets


## Usage

```
usage: lufah.py [-h] [-v] [-d] [--version] peer command ...

Little Utility for FAH v8

positional arguments:
  peer           [host][:port][/group] Use "." for localhost
  command
    status
    pause
    unpause
    finish
    log
    config       get or set config values
    start        start local client service; peer must be "."
    stop         stop local client service; peer must be "."

options:
  -h, --help     show this help message and exit
  -v, --verbose
  -d, --debug
  --version      show program's version number and exit

Examples

lufah.py . finish
lufah.py other.local/rg1 status
lufah.py /my-p-cores config priority normal

Bugs

An error may not be shown if initial connection times out.
If group does not exist, script will hang until silent timeout.
Command log may not notice a disconnect.
```

Note: commands start and stop are macOS-only.
