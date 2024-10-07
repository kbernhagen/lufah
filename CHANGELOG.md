# Changelog

## [Unreleased]

### Added

- Added Uninstall to docs and Makefile
- Added `top` command

---

## [0.7.0] - 2024-09-24

This may be the last release to support FAH v8.1 and v8.2.

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


[unreleased]: https://github.com/kbernhagen/lufah/compare/0.7.0...HEAD
[0.7.0]: https://github.com/kbernhagen/lufah/compare/0.6.0...0.7.0
[0.6.0]: https://github.com/kbernhagen/lufah/compare/0.5.0...0.6.0
