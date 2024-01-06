# lufah

Little Utility for FAH v8

This is a python command line utility script that should
work on macOS, Linux, and Windows.


## Requirements

- python 3.8 or later
- pip3 install websockets --user


## Usage

Note that lufah uses unencrypted, direct websocket connections.
This is what Web Control uses to connect to the local client.
This has security implications if you enable direct remote access on a client.
See [HOWTO: Allow v8 Client Remote Control](https://foldingforum.org/viewtopic.php?t=39050)

```
usage: lufah [-h] [-v] [-d] [--version] peer command ...

Little Utility for FAH v8

positional arguments:
  peer           [host][:port][/group] Use "." for localhost
  command
    status       show json snapshot of client state
    units        show table of all units by group
    fold
    finish
    pause
    unpause      alias for fold
    config       get or set config values
    groups       show json array of resource group names
    log          show log; use control-c to exit
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

All commands except "/group config key value" are supported for fah 8.3.
Command config may not behave as expected for fah 8.3.

Group names for fah 8.1 must:
  begin "/", have only letters, numbers, period, underscore, hyphen
Group names on 8.3 can have spaces and special chars.
Web Control 8.3 trims leading and trailing white space.
Group "/" is taken to mean the default group, which is "".
For a group actually named "/", use "//".

An error may not be shown if the initial connection times out.
If group does not exist on 8.1, this script may hang until silent timeout.
Config priority does not seem to work. Cores are probably setting priority.
Commands start and stop are macOS-only.
```

On Windows, usage resembles
```
python .\somewhere\lufah.py . pause
```
If you put `lufah.py` and `lufah.bat` together in a directory
in your command `PATH`, you can use
```
lufah . pause
```

## Tricks

On macOS (and probably Linux), if you have [Homebrew](https://brew.sh/) installed, you can install `watch` to have an inefficient top-like units display:

```
brew install watch

watch -d -n 10 lufah $(hostname) units
```

## Example Output

```
lufah frotz.local units
```
```
--------------------------------------------------------------------
Project  CPUs  GPUs  Status     Progress  PPD       ETA
--------------------------------------------------------------------
frotz/
19230    8     0     Running     0.129    143845    5 hours 33 mins
frotz//two
18419    8     0     Finishing   0.965    170848    45 mins 34 secs
frotz//tree
```
