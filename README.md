# lufah

Little Utility for FAH v8

This is a python command line utility script that should
work on macOS, Linux, and Windows.


## Requirements

- python 3.8 or later
- pip3 install websockets --user


## Usage

```
usage: lufah.py [-h] [-v] [-d] [--version] peer command ...

Little Utility for FAH v8

positional arguments:
  peer           [host][:port][/group] Use "." for localhost
  command
    status       default command if none is specified
    pause
    unpause      alias for fold
    fold
    finish
    log          show log; use control-c to exit
    config       get or set config values
    groups       show resource group names
    watch        show incoming messages; use control-c to exit
    start        start local client service; peer must be "."
    stop         stop local client service; peer must be "."

options:
  -h, --help     show this help message and exit
  -v, --verbose
  -d, --debug
  --version      show program's version number and exit

Examples

lufah . finish
lufah other.local/rg1 status
lufah /mygpu1 config cpus 0

Notes

All commands except `/group config key value` are supported for fah 8.3.
Command config may not behave as expected for fah 8.3.

Group names should preferably conform to fah 8.1 restrictions:
  begins "/", has only letters, numbers, period, underscore, hyphen
For 8.3, group names can contain spaces and special chars.
Group "/" is taken to mean the default group, which is actually named "".
For a group named "/" on 8.3, use "//".

An error may not be shown if the initial connection times out.
If group does not exist on 8.1, this script may hang until silent timeout.
Config priority does not seem to work. Cores are probably setting priority.
Commands start and stop are macOS-only.
```

On Windows, usage resembles
```
python .\somewhere\lufah.py . pause
```
