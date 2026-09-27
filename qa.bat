@echo off
REM baby-agent: `qa` command shim — `qa <args>` runs the repo CLI.
REM One-time setup: add this file's directory to your PATH (or copy
REM this file into a directory already on PATH). Your current
REM directory is kept (per-project stores resolve there); the repo is
REM found via PYTHONPATH. Equivalent when run from the repo root:
REM   python -m qacompanion <args>
set "QA_HOME=%~dp0"
set "PYTHONPATH=%QA_HOME%;%PYTHONPATH%"
python -m qacompanion %*
