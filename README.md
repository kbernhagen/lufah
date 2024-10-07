# lufah

Little Utility for FAH v8

This is a python command line utility script that should
work on macOS, Linux, and Windows.


## Requirements

- python 3.8 or later


## Install from PyPI

Install in isolated user environment (preferred):
```
pip install pipx
pipx install lufah
```

Or
```
pip install lufah
```

## Uninstall

```
pip install pipx
pipx uninstall lufah
```

Or
```
pip uninstall lufah
```

## Install from source

macOS / Linux / Windows
```
git clone https://github.com/kbernhagen/lufah.git
cd lufah
make install-user
```

## Uninstall from source

```
git clone https://github.com/kbernhagen/lufah.git
cd lufah
make uninstall-user
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
    state               Show json snapshot of client state.
    status              alias for state
    units               Show table of all units by machine name and group.
    fold                Start folding in specified group or all groups.
    finish              Finish folding and pause specified group or all groups.
    pause               Pause folding in specified group or all groups.
    unpause             alias for fold
    config              Get or set config values.
    groups              Show json array of resource group names.
    create-group        Create group if it does not exist.
    info                Show host and client info.
    log                 Show client log. Use control-c to exit.
    watch               Show incoming messages. Use control-c to exit.
    get                 Show json value at dot-separated key path in client state.
    unlink-account      Unlink account. Requires client 8.3.1 thru 8.3.16.
    link-account        Link to account by token.
    restart-account     Restart account/node connection.
    wait-until-paused   Run until specified group or all groups are paused.
    enable-all-gpus     Enable all unclaimed gpus in specified group.
    dump-all            Dump all paused units in specified group or all groups.
    top                 Show top-like updating units table. Type 'q' to quit, space to force redraw.
    start               Start local client service.
    stop                Stop local client service.

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose
  -d, --debug
  --version             show program's version number and exit
  -a ADDRESS, --address ADDRESS
                        [host][:port][/group] or [host][:port],[host][:port]...
                        Use "." for localhost.
                        Group name must not be url-encoded, but may need escaping from shell.
                        Can be a comma-separated list of hosts for commands
                        units, info, fold, finish, pause

Examples

lufah units
lufah -a //rg2 finish
lufah -a other.local state
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
Example: lufah -a somehost//rg1 finish

An error may not be shown if the initial connection times out.
If group does not exist on 8.1, this script may hang until silent timeout.
Commands start and stop are macOS-only.
```

The `top` command is glitchy on Windows when the window is resized.
Type space to force a redraw.

## Example Output

```
lufah -a .,panda.local units
```
```
--------------------------------------------------------------------------------
Project  CPUs  GPUs  Core  Status          Progress  PPD       ETA      Deadline
--------------------------------------------------------------------------------
Panda/                     Run 
18494    4     0     0xa8  Running          89.0%    178413    26m 39s  3d 8h   
Sanctuary/                 Paused
Sanctuary/tcore            Run Wait 16m 21s
11901    2     0     0xfe  Dumped            0.0%    0         28m 48s  5h 59m  
Sanctuary/aux              Finish 
12421    8     0     0xa8  Finishing        48.1%    237945    14h 15m  4d 10h  
```
