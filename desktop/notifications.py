"""Desktop notifications via libnotify."""
import subprocess

APP_NAME = "AutoType"


def notify(title: str, message: str) -> None:
    subprocess.run(
        ["notify-send", title, message, "--app-name", APP_NAME],
        check=False,
    )
