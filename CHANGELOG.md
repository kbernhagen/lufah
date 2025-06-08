# Changelog

## [Unreleased]

### Changed

- Added units columns PRCG, TPF, Timeout; removed Project column
- Added --force option to finish command,
 which tries to change paused groups with active units directly to Finishing on fah 8.4+.
 This may break in the future.

---

## [0.9.1] - 2025-05-09

### Fixed

- Fixed intermittent bugs with timeout, deadline display

---

## [0.9.0] - 2025-03-31

### Changed

- Builds osx start/stop notification strings from launchd.plist values
- Updated user name validation to match Web Control
- Added --force option to config user to allow legacy names
- Added PPD total after units table when multiple units
- Added thousands separator to PPD
- Added CPU and GPU PPD totals when both are greater than 0
- Added group config hip

---

## [0.8.2] - 2024-12-17

### Changed

- Removed `windows-curses` as a required dependency

---

## [0.8.1] - 2024-11-27

### Fixed

- Use websockets.asyncio.client for websockets 14 compatability

---

## [0.8.0] - 2024-10-27

### Added

- Added Uninstall to docs and Makefile
- Added `top` command
- Optional shell command completion via Typer

### Changed

- Uses Typer instead of Argparse for cli parsing
- Client update processing uses translated code from FAH Web Control

---

## [0.7.0] - 2024-09-24

Support for FAH older than v8.3 is deprecated.

### Changed

- Units table shows group run/wait status
- Units table status strings closely match Web Control v8.4.5
- Units table shows deadline 'Expired' instead of negative time
- Updated help text and argument validation
- Improved keyboard interrupt handling (no delay exiting)
- Command 'get' handles array indexes
- Simplified console logging format, and allowed option -dv

---

## [0.6.0] - 2024-08-24

### Breaking Changes

- Changed required argument PEER to option --address
- Allow configuring group options without specifying group if there is only one group


[unreleased]: https://github.com/kbernhagen/lufah/compare/0.9.1...HEAD
[0.9.1]: https://github.com/kbernhagen/lufah/compare/0.9.0...0.9.1
[0.9.0]: https://github.com/kbernhagen/lufah/compare/0.8.2...0.9.0
[0.8.2]: https://github.com/kbernhagen/lufah/compare/0.8.1...0.8.2
[0.8.1]: https://github.com/kbernhagen/lufah/compare/0.8.0...0.8.1
[0.8.0]: https://github.com/kbernhagen/lufah/compare/0.7.0...0.8.0
[0.7.0]: https://github.com/kbernhagen/lufah/compare/0.6.0...0.7.0
[0.6.0]: https://github.com/kbernhagen/lufah/compare/0.5.0...0.6.0
