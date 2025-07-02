# lufah

Little Utility for FAH v8

A python command line utility for macOS, Linux, Windows

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
lufah -h
```

```
Usage: lufah [OPTIONS] COMMAND [ARGS]...

  Little Utility for FAH v8

Options:
  -a, --address ADDRESS  [host][:port][/group] or
                         [host][:port],[host][:port]... Use "." for localhost.
                         Group name must not be url-encoded, but may need
                         escaping from shell. Can be a comma-separated list of
                         hosts for commands units, info, fold, finish, pause
                         [default: localhost:7396]
  -v, --verbose
  -d, --debug
  --version              Show version and exit.
  --install-completion   Install completion for the current shell.
  --show-completion      Show completion for the current shell, to copy it or
                         customize the installation.
  -h, --help             Show this message and exit.

Commands:
  fold               Start folding in specified group or all groups.
  finish             Finish folding and pause specified group or all groups.
  pause              Pause folding in specified group or all groups.
  unpause            (Deprecated) alias for fold
  wait-until-paused  Run until specified group or all groups are paused.
  config             Get or set config values.
  create-group       Create group if it does not exist.
  delete-group       Delete group if it exists, is not "", is paused, and...
  dump-all           Dump all paused units in specified group or all groups.
  enable-all-gpus    Enable all unclaimed gpus in specified group.
  state              Show json snapshot of client state.
  status             (Deprecated) alias for state
  get                Show json value at dot-separated key path in client...
  groups             Show json array of resource group names.
  info               Show host and client info.
  log                Show client log.
  top                Show top-like updating units table.
  units              Show table of all units by machine name and group.
  watch              Show incoming messages.
  link-account       Link to account by token.
  unlink-account     Unlink account.
  restart-account    Restart account/node connection.
  start              Start local client service.
  stop               Stop local client service.
```

```
lufah config -h
```

```
Usage: lufah config [OPTIONS] COMMAND [ARGS]...

  Get or set config values.

  Other than for account settings (user, team, passkey, cause), a group must
  be specified if there is more than one group.

  Example: lufah -a / config cpus 0

Options:
  -h, --help  Show this message and exit.

Commands:
  beta        Enable beta work units.
  cause       Set cause preference.
  checkpoint  (Deprecated) Set requested CPU WU checkpoint frequency in
              minutes.
  cpus        Set number of cpus to allocate to resource group.
  cuda        Enable CUDA for WUs in specified group.
  fold-anon   (Deprecated) Fold anonymously.
  hip         Enable HIP for WUs in specified group.
  keep-awake  Prevent system sleep while folding and not on battery.
  key         Set project key for internal beta testing of new projects.
  on-battery  Fold even if on battery.
  on-idle     Only fold while user is idle.
  passkey     Set passkey token for quick return bonus points.
  priority    (Deprecated) Set preferred core task priority.
  team        Set team number.
  user        Set folding user name, "" or 2 to 100 bytes.
```

## Examples

```
lufah units
lufah -a //rg2 finish
lufah -a /mygpu1 config cpus 0
lufah -a host1,host2,host3 units
lufah -a host1,host2,host3 info
```

## Notes

If not given, the default command is "units".

If there are multiple groups, config requires a group name,
except for account settings (user, team, passkey, cause).

For command `lufah -a /groupname config cpus N`, N is not limited to unused cpus across groups.

Group "/" is taken to mean the default group, which is "".

For a group name actually starting with "/", use prefix "//".
Example: `lufah -a somehost//rg1 finish`

An error may not be shown if connection times out.

Commands start and stop are macOS-only.

The `top` command is glitchy on Windows when the window is resized.
Type space to force a redraw.
To use `lufah top` on Windows, you may need to manually install `windows-curses`.

## Example Output

```
lufah -a .,panda.local units
```
```
----------------------------------------------------------------------------------------------------------
PRCG                 CPUs GPUs Core Status          Progress PPD         TPF      ETA     Timeout Deadline
----------------------------------------------------------------------------------------------------------
Panda/                              Run 
18240 1190,0,463     4    0    0xa8 Running          12.8%   156,073     01m 30s  2h 11m   1d 23h   4d 23h 
Sanctuary/                          Paused
Sanctuary/aux                       Run 
18806 17,14,474      12   0    0xa9 Running          62.7%   397,835     03m 33s  2h 12m   2d 20h   2d 22h 

Total PPD: 553,908
```
