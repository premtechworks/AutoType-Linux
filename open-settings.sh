#!/bin/bash
# Launch the AutoType Settings GUI (Linux Mint XFCE).
cd "$(dirname "$0")" || exit 1
exec .venv/bin/python settings_gui.py
