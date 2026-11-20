# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Package scaffold: `pip install erdify-studio` installs the `erdify-studio` command
  (`--help`, `--version`) with erdify as a dependency; `erdify-studio[sql]` pulls in
  `erdify[sql]`. The browser frontend is built in CI and shipped inside the wheel, so no
  Node is needed on the user's machine.
