"""System tray icon (pystray): state colors + mode menu.

States: gray idle, red recording, orange processing, green ready flash,
pink error. Runs detached in its own thread; all methods are thread-safe.
"""
import threading

from PIL import Image, ImageDraw
import pystray

COLORS = {
    "idle": (130, 130, 130, 255),
    "recording": (220, 60, 60, 255),
    "processing": (240, 150, 40, 255),
    "ready": (70, 180, 90, 255),
    "error": (210, 60, 140, 255),
}


def _image(color) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([10, 10, 54, 54], fill=color)
    draw.ellipse([24, 24, 40, 40], fill=(20, 20, 20, 255))
    return img


class TrayController:
    def __init__(self, get_mode, set_mode, backend: str, on_quit,
                 on_settings=None):
        self._get_mode = get_mode
        self._set_mode = set_mode
        self._on_settings = on_settings
        self._get_mode = get_mode
        self._set_mode = set_mode
        self._state = "idle"
        self._ready_timer: threading.Timer | None = None
        self.icon = pystray.Icon(
            "autotype", _image(COLORS["idle"]),
            f"AutoType ({backend})", menu=self._menu(),
        )
        self._on_quit = on_quit

    # -- menu ----------------------------------------------------------
    def _pick(self, mode):
        def _inner(icon, item):
            self._set_mode(mode)
            icon.update_menu()
        return _inner

    def _menu(self):
        modes = (
            ("raw", "Raw — paste verbatim"),
            ("clean", "Clean — tidy up (default)"),
            ("smart", "Smart — adapt to app"),
            ("professional", "Professional — formal"),
            ("casual", "Casual — conversational"),
            ("email", "Email — greeting/body/close"),
            ("chat", "Chat — short + casual"),
            ("code", "Code — literal"),
        )
        return pystray.Menu(
            pystray.MenuItem(
                "Mode", pystray.Menu(*[
                    pystray.MenuItem(
                        label, self._pick(mode),
                        checked=lambda item, m=mode: self._get_mode() == m)
                    for mode, label in modes
                ]),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings…", self._open_settings),
            pystray.MenuItem("Quit", self._quit),
        )

    def _open_settings(self, icon, item):
        import subprocess
        import sys
        from pathlib import Path
        gui = Path(__file__).resolve().parent.parent / "settings_gui.py"
        try:
            subprocess.Popen([sys.executable, str(gui)],
                             start_new_session=True,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _quit(self, icon, item):
        try:
            icon.stop()
        finally:
            self._on_quit()

    # -- state ----------------------------------------------------------
    def set_state(self, state: str):
        if state not in COLORS:
            return
        self._cancel_ready_timer()
        self._state = state
        try:
            self.icon.icon = _image(COLORS[state])
        except Exception:
            pass

    def flash_ready(self):
        self.set_state("ready")
        self._cancel_ready_timer()
        self._ready_timer = threading.Timer(1.5, self._back_to_idle)
        self._ready_timer.daemon = True
        self._ready_timer.start()

    def _back_to_idle(self):
        self.set_state("idle")

    def _cancel_ready_timer(self):
        if self._ready_timer is not None:
            self._ready_timer.cancel()
            self._ready_timer = None

    def refresh_menu(self):
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def run(self):
        self.icon.run_detached()
