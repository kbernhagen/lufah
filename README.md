# lufah

Little Utility for FAH v8

This is a python command line utility script that should
work on macOS, Linux, and Windows.


## Requirements

- python 3.8 or later


## Install from PyPI

```
pip install lufah
```

## Install from source

macOS / Linux / Windows
```
git clone https://github.com/kbernhagen/lufah.git
cd lufah
make install-user
```

## Usage

Note that lufah uses unencrypted, direct websocket connections.
This is what Web Control uses to connect to the local client.
This has security implications if you enable direct remote access on a client.
See [HOWTO: Allow v8 Client Remote Control](https://foldingforum.org/viewtopic.php?t=39050)

```
usage: lufah [-h] [-v] [-d] [--version] [-a ADDRESS] COMMAND ...

Little Utility for FAH v8

positional arguments:
  COMMAND
    status              show json snapshot of client state
    state               alias for status
    units               show table of all units by group
    fold
    finish
    pause
    unpause             alias for fold
    config              get or set config values
    groups              show json array of resource group names
    create-group        create group if it does not exist
    info                show peer host and client info
    log                 show log; use control-c to exit
    watch               show incoming messages; use control-c to exit
    get                 show json value at dot-separated key path in client state
    unlink-account
    link-account        account-token [machine-name]
    restart-account     restart account/node connection
    wait-until-paused   run until all target groups seem paused
    enable-all-gpus     enable all unclaimed gpus in specified group
    dump-all            dump all paused units in specified group or all groups
    start               start local client service
    stop                stop local client service

options:
  -h, --help            show this help message and exit
  -v, --verbose
  -d, --debug
  --version             show program's version number and exit
  -a ADDRESS, --address ADDRESS
                        [host][:port][/group]
                        Use "." for localhost.
                        Can be a comma-separated list of hosts for commands
                        units, info, fold, finish, pause:
                        host[:port],host[:port],...

Examples

lufah units
lufah -a /rg2 finish
lufah -a other.local/rg1 status
lufah -a /mygpu1 config cpus 0
lufah config -h
lufah -a host1,host2,host3 units
lufah -a host1,host2,host3 info

Notes

If not given, the default command is 'units'.

In 8.3+, if there are multiple groups, config requires a group name,
except for account settings (user, team, passkey, cause).
In 8.3, -a /group config cpus <n> is not limited to unused cpus across groups.

Group names for fah 8.1 must:
  begin "/", have only letters, numbers, period, underscore, hyphen
Group names on 8.3 can have spaces and special chars.
Web Control 8.3 trims leading and trailing white space when creating groups.
Group "/" is taken to mean the default group, which is "".
For a group name actually starting with "/", use prefix "//".

An error may not be shown if the initial connection times out.
If group does not exist on 8.1, this script may hang until silent timeout.
Config priority does not seem to work. Cores are probably setting priority.
It sometimes takes 30 seconds to exit after a control-c.
Commands start and stop are macOS-only.
```

## Tricks

On macOS, if you have [Homebrew](https://brew.sh/) installed,
you can install `watch` to have an inefficient top-like units display.
On Linux, you probably already have `watch` installed.

```
brew install watch

watch -n 10 lufah -a $(hostname) units
```

## Example Output

```
lufah -a .,panda units
```
```
--------------------------------------------------------------------------------
Project  CPUs  GPUs  Core  Status          Progress  PPD       ETA      Deadline
--------------------------------------------------------------------------------
Panda/
12417    4     0     0xa8  Running          25.4%    162364    4h 7m    4d 22h  
Sanctuary/
18806    8     0     0xa9  Running          63.1%    261999    2h 53m   2d 21h  
```
