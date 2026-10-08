"""Floating pill widget above the taskbar (GTK3, X11).

States: hidden | recording (live waveform) | processing (animated dots)
        | error (message, auto-hides). All methods are thread-safe —
they schedule work on the GTK main loop via GLib.idle_add.
"""
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango

WIDTH, HEIGHT = 300, 76
BARS = 30

CSS = b"""
.window-pill {
    background-color: rgba(18, 20, 26, 0.93);
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.18);
}
.status-label { color: #ffffff; font-size: 13px; font-weight: bold; }
.stop-btn {
    background-color: rgba(239, 68, 68, 0.18);
    border: 1px solid rgba(239, 68, 68, 0.45);
    border-radius: 6px;
    padding: 0px;
    min-width: 22px;
    min-height: 22px;
    box-shadow: none;
    outline: none;
}
.stop-btn:hover {
    background-color: rgba(239, 68, 68, 0.45);
    border-color: rgba(239, 68, 68, 0.85);
}
.stop-icon {
    color: #ef4444;
    font-size: 10px;
    font-weight: bold;
}
"""


class Overlay:
    def __init__(self, get_level=None, on_cancel=None):
        self.get_level = get_level or (lambda: 0.0)
        self.on_cancel = on_cancel
        self.state = "hidden"
        self.status_text = ""
        self.levels = [0.0] * BARS
        self._tick_id = None
        self._hide_id = None

        self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_default_size(WIDTH, HEIGHT)
        self.win.set_decorated(False)
        self.win.set_resizable(False)
        self.win.set_keep_above(True)
        self.win.set_skip_taskbar_hint(True)
        self.win.set_skip_pager_hint(True)
        self.win.stick()
        self.win.set_accept_focus(False)
        self.win.set_focus_on_map(False)

        screen = self.win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.win.set_visual(visual)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.win.get_style_context().add_class("window-pill")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_top(10)
        box.set_margin_bottom(8)
        box.set_margin_start(16)
        box.set_margin_end(16)
        self.win.add(box)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.label = Gtk.Label(label="")
        self.label.set_xalign(0.0)
        self.label.set_ellipsize(Pango.EllipsizeMode.END)
        self.label.get_style_context().add_class("status-label")
        header.pack_start(self.label, True, True, 0)

        self.stop_btn = Gtk.Button()
        self.stop_btn.get_style_context().add_class("stop-btn")
        self.stop_btn.set_tooltip_text("Cancel dictation")
        stop_icon = Gtk.Label(label="■")
        stop_icon.get_style_context().add_class("stop-icon")
        self.stop_btn.add(stop_icon)
        self.stop_btn.connect("clicked", self._on_stop_clicked)
        header.pack_end(self.stop_btn, False, False, 0)
        box.pack_start(header, False, False, 0)

        self.bars = Gtk.DrawingArea()
        self.bars.set_size_request(WIDTH - 32, 34)
        self.bars.connect("draw", self._on_draw)
        box.pack_start(self.bars, True, True, 0)

        self._place_above_taskbar()
        self.win.hide()

    def _on_stop_clicked(self, button):
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass

    # -- geometry -----------------------------------------------------
    def _place_above_taskbar(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor()
        work = monitor.get_workarea()
        x = work.x + (work.width - WIDTH) // 2
        y = work.y + work.height - HEIGHT - 16
        self.win.move(x, y)

    # -- public API (thread-safe) --------------------------------------
    def show_recording(self):
        GLib.idle_add(self._do_show, "recording", "Listening...")

    def show_processing(self, text="Working..."):
        GLib.idle_add(self._do_show, "processing", text)

    def show_error(self, text="Something went wrong"):
        GLib.idle_add(self._do_show, "error", text)
        if self._hide_id:
            GLib.source_remove(self._hide_id)
        self._hide_id = GLib.timeout_add(2500, self._auto_hide)

    def hide(self):
        GLib.idle_add(self._do_hide)

    def update_partial(self, text: str):
        """Live partial transcript in the pill (Flux hold-to-talk)."""
        GLib.idle_add(self._do_partial, text)

    # -- internals (run on the GTK thread) ------------------------------
    def _do_show(self, state, text):
        self.state = state
        self.status_text = text
        self.label.set_text(text)
        if state == "recording":
            self.levels = [0.0] * BARS
        self.win.show_all()
        if state == "error":
            self.stop_btn.set_visible(False)
        else:
            self.stop_btn.set_visible(True)
        self.win.present()
        if self._tick_id is None:
            self._tick_id = GLib.timeout_add(66, self._tick)
        return False

    def _do_partial(self, text: str):
        if self.state == "recording":
            short = text.strip()
            if len(short) > 60:
                short = "..." + short[-57:]
            self.label.set_text(f"Listening... {short}" if short else "Listening...")
        return False

    def _do_hide(self):
        if self._tick_id:
            GLib.source_remove(self._tick_id)
            self._tick_id = None
        self.state = "hidden"
        self.win.hide()
        return False

    def _auto_hide(self):
        self._hide_id = None
        self._do_hide()
        return False

    def _tick(self):
        if self.state == "hidden":
            self._tick_id = None
            return False
        if self.state == "recording":
            try:
                level = max(0.0, min(1.0, float(self.get_level())))
            except Exception:
                level = 0.0
            self.levels.append(level)
            self.levels.pop(0)
        self.bars.queue_draw()
        return True

    def _on_draw(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        now = time.monotonic()

        if self.state == "recording":
            color = (0.95, 0.30, 0.30)  # red
            values = self.levels
        elif self.state == "processing":
            color = (0.35, 0.65, 1.0)  # blue pulse
            # Traveling sine wave while busy.
            values = [
                0.25 + 0.55 * abs(((i / BARS) + (now * 1.5)) % 1.0 - 0.5) * 2
                for i in range(BARS)
            ]
        else:  # error
            color = (1.0, 0.55, 0.2)  # orange
            values = [0.15] * BARS

        slot = w / BARS
        bar_w = max(2.0, slot * 0.55)
        cr.set_source_rgb(*color)
        cr.set_line_width(bar_w)
        cr.set_line_cap(1)  # round caps
        for i, v in enumerate(values):
            bh = max(3.0, v * h)
            x = i * slot + slot / 2
            cr.move_to(x, (h - bh) / 2)
            cr.line_to(x, (h + bh) / 2)
            cr.stroke()
        return False
