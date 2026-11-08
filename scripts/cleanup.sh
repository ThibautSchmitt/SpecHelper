#!/bin/sh
# Administrative command; no Docker-wide pruning or host-directory removal.
set -eu
exec python3 "$(dirname "$0")/cleanup.py" "$@"
