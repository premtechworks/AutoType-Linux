#!/bin/bash
# Start the AutoType daemon (if it is not running) and open the settings window.
# Safe to run from a terminal, from the file manager, or from a shortcut:
# an already-running daemon only raises an "already running" dialog.
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/autotype" ]; then
    exec .venv/bin/autotype launch "$@"
elif [ -x ".venv/bin/python" ]; then
    exec .venv/bin/python -m autotype.cli launch "$@"
else
    exec python3 -m autotype.cli launch "$@"
fi