"""Hotkey debug: verifies double-tap Right-Alt is seen by pynput.

Run: .venv/bin/python test_hotkey.py
Then double-tap Right Alt. Expect: "DOUBLE-TAP detected -> toggle would fire".
Press Ctrl+C to quit.
"""
import time

from pynput import keyboard

DOUBLE_TAP_WINDOW = 0.4
RIGHT_ALT_KEYS = {keyboard.Key.alt_r, keyboard.Key.alt_gr}
last_tap = [0.0]
held = set()


def on_press(key):
    print(f"press: {key}")
    if key in RIGHT_ALT_KEYS:
        if key in held:
            return
        held.add(key)
        now = time.monotonic()
        if now - last_tap[0] < DOUBLE_TAP_WINDOW:
            last_tap[0] = 0.0
            print("DOUBLE-TAP detected -> toggle would fire")
        else:
            last_tap[0] = now
            print("single Right-Alt tap (tap again quickly)")


def on_release(key):
    held.discard(key)


print("Double-tap Right Alt now (Ctrl+C to quit)...")
with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
    listener.join()
