#!/bin/bash
# Launch the AutoType Settings GUI (Linux Mint XFCE).
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/autotype" ]; then
    exec .venv/bin/autotype settings "$@"
else
    exec .venv/bin/python -m autotype.cli settings "$@"
fi
