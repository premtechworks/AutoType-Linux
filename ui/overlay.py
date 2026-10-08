"""Floating glassmorphism voice assistant widget above the taskbar (GTK3, X11).

States: hidden | recording (live waveform) | processing (pulse animation)
        | error (message, auto-hides). All methods are thread-safe -
        they schedule work on the GTK main loop via GLib.idle_add.

Redesigned to a premium dark glassmorphism floating voice assistant widget:
- Row 1: Microphone indicator, status text, dynamic audio waveform, elapsed timer, stop button
- Row 2: Inset glass live transcript strip with smooth marquee scrolling
"""
import math
import time

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo

# -----------------------------------------------------------------------------
# Constants & Geometry
# -----------------------------------------------------------------------------

TARGET_WIDTH = 800
TARGET_HEIGHT = 132
BARS = 42

# Palette (RGBA normalized 0.0 - 1.0)
COLOR_BG_CARD = (7 / 255, 16 / 255, 23 / 255, 0.94)
COLOR_BORDER_CARD = (37 / 255, 230 / 255, 195 / 255, 0.22)
COLOR_BG_TRANSCRIPT = (10 / 255, 22 / 255, 31 / 255, 0.65)
COLOR_BORDER_TRANSCRIPT = (1.0, 1.0, 1.0, 0.08)

COLOR_TEAL = (37 / 255, 230 / 255, 195 / 255)       # #25E6C3
COLOR_CYAN = (56 / 255, 189 / 255, 248 / 255)      # #38BDF8
COLOR_INDIGO = (129 / 255, 140 / 255, 248 / 255)   # #818CF8
COLOR_STOP_RED = (255 / 255, 79 / 255, 94 / 255)   # #FF4F5E
COLOR_ORANGE = (249 / 255, 115 / 255, 22 / 255)    # #F97316

COLOR_TEXT_PRIMARY = (244 / 255, 248 / 255, 250 / 255)    # #F4F8FA
COLOR_TEXT_SECONDARY = (142 / 255, 165 / 255, 178 / 255)  # #8EA5B2
COLOR_TEXT_PLACEHOLDER = (92 / 255, 116 / 255, 128 / 255) # #5C7480

CSS = b"""
.overlay-card {
    background-color: rgba(7, 16, 23, 0.94);
    border-radius: 26px;
    border: 1px solid rgba(37, 230, 195, 0.22);
}

.status-title {
    color: #F4F8FA;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.2px;
}

.status-sub {
    color: #8EA5B2;
    font-size: 12px;
    font-weight: 500;
}

.timer-label {
    color: #8EA5B2;
    font-family: monospace, "DejaVu Sans Mono", monospace;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

.stop-btn {
    background-color: rgba(255, 79, 94, 0.16);
    border: 1px solid rgba(255, 79, 94, 0.35);
    border-radius: 12px;
    min-width: 44px;
    min-height: 44px;
    padding: 0px;
    box-shadow: none;
    outline: none;
}

.stop-btn:hover {
    background-color: rgba(255, 79, 94, 0.35);
    border-color: rgba(255, 79, 94, 0.70);
}

.stop-icon {
    color: #FF4F5E;
    font-size: 13px;
    font-weight: 900;
}
"""


class Overlay:
    """Floating glassmorphism voice assistant widget above the taskbar."""

    def __init__(self, get_level=None, on_cancel=None):
        self.get_level = get_level or (lambda: 0.0)
        self.on_cancel = on_cancel

        self.state = "hidden"
        self.status_title = ""
        self.status_subtitle = ""

        # Waveform state
        self._bar_heights = [0.0] * BARS
        self._current_mic_level = 0.0

        # Transcript & Caret state
        self._transcript_text = ""
        self._scroll_offset = 0.0
        self._caret_visible = True
        self._caret_timer = 0.0

        # Timer state
        self._recording_start_time = 0.0
        self._tick_id = None
        self._hide_id = None

        # --- Window Configuration --------------------------------------------
        self.win = Gtk.Window(type=Gtk.WindowType.POPUP)
        self.win.set_default_size(TARGET_WIDTH, TARGET_HEIGHT)
        self.win.set_size_request(TARGET_WIDTH, TARGET_HEIGHT)
        self.win.set_decorated(False)
        self.win.set_resizable(False)
        self.win.set_keep_above(True)
        self.win.set_skip_taskbar_hint(True)
        self.win.set_skip_pager_hint(True)
        self.win.stick()
        self.win.set_accept_focus(False)
        self.win.set_focus_on_map(False)

        # Transparent RGBA visual
        screen = self.win.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.win.set_visual(visual)

        # CSS provider
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.win.get_style_context().add_class("overlay-card")

        # --- Main Layout -----------------------------------------------------
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(14)
        main_box.set_margin_bottom(14)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        self.win.add(main_box)

        # --- ROW 1: Controls, Status & Waveform ------------------------------
        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        row1.set_size_request(-1, 52)
        row1.set_valign(Gtk.Align.CENTER)
        main_box.pack_start(row1, False, False, 0)

        # Microphone indicator (Cairo)
        self.mic_area = Gtk.DrawingArea()
        self.mic_area.set_size_request(42, 42)
        self.mic_area.set_valign(Gtk.Align.CENTER)
        self.mic_area.connect("draw", self._on_draw_mic)
        row1.pack_start(self.mic_area, False, False, 0)

        # Status text box
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        status_box.set_valign(Gtk.Align.CENTER)

        self.title_label = Gtk.Label(label="")
        self.title_label.set_xalign(0.0)
        self.title_label.get_style_context().add_class("status-title")
        status_box.pack_start(self.title_label, False, False, 0)

        self.subtitle_label = Gtk.Label(label="")
        self.subtitle_label.set_xalign(0.0)
        self.subtitle_label.get_style_context().add_class("status-sub")
        status_box.pack_start(self.subtitle_label, False, False, 0)

        row1.pack_start(status_box, False, False, 0)

        # Audio Waveform (Cairo)
        self.waveform_area = Gtk.DrawingArea()
        self.waveform_area.set_hexpand(True)
        self.waveform_area.set_size_request(150, 42)
        self.waveform_area.set_valign(Gtk.Align.CENTER)
        self.waveform_area.connect("draw", self._on_draw_waveform)
        row1.pack_start(self.waveform_area, True, True, 0)

        # Elapsed Timer
        self.timer_label = Gtk.Label(label="0:00")
        self.timer_label.set_size_request(48, -1)
        self.timer_label.set_xalign(0.5)
        self.timer_label.set_valign(Gtk.Align.CENTER)
        self.timer_label.get_style_context().add_class("timer-label")
        row1.pack_start(self.timer_label, False, False, 0)

        # Stop Button
        self.stop_btn = Gtk.Button()
        self.stop_btn.get_style_context().add_class("stop-btn")
        self.stop_btn.set_tooltip_text("Cancel dictation")
        self.stop_btn.set_focus_on_click(False)
        self.stop_btn.set_can_focus(False)
        self.stop_btn.set_valign(Gtk.Align.CENTER)

        stop_icon = Gtk.Label(label="■")  # Solid square
        stop_icon.get_style_context().add_class("stop-icon")
        self.stop_btn.add(stop_icon)
        self.stop_btn.connect("clicked", self._on_stop_clicked)
        row1.pack_end(self.stop_btn, False, False, 0)

        # --- ROW 2: Live Transcript Strip ------------------------------------
        self.transcript_area = Gtk.DrawingArea()
        self.transcript_area.set_size_request(-1, 38)
        self.transcript_area.connect("draw", self._on_draw_transcript)
        main_box.pack_start(self.transcript_area, False, False, 0)

        # Position and initial state
        self._place_above_taskbar()
        self.win.hide()

    # -------------------------------------------------------------------------
    # Window Placement
    # -------------------------------------------------------------------------

    def _place_above_taskbar(self):
        display = Gdk.Display.get_default()
        if not display:
            return
        monitor = display.get_primary_monitor()
        if not monitor:
            monitors = display.get_n_monitors()
            if monitors > 0:
                monitor = display.get_monitor(0)
        if not monitor:
            return

        work = monitor.get_workarea()
        actual_w = min(TARGET_WIDTH, max(360, work.width - 40))
        actual_h = TARGET_HEIGHT
        x = work.x + (work.width - actual_w) // 2
        y = work.y + work.height - actual_h - 20

        self.win.move(x, y)
        self.win.resize(actual_w, actual_h)

    # -------------------------------------------------------------------------
    # Public API (Thread-Safe)
    # -------------------------------------------------------------------------

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
        """Update live transcript strip with partial transcription."""
        GLib.idle_add(self._do_partial, text)

    # -------------------------------------------------------------------------
    # Internals (Run on the GTK main thread)
    # -------------------------------------------------------------------------

    def _do_show(self, state, text):
        self.state = state
        now = time.monotonic()

        if state == "recording":
            self.status_title = "Listening..."
            self.status_subtitle = "Speak naturally..."
            self._recording_start_time = now
            self.timer_label.set_text("0:00")
            self._bar_heights = [0.0] * BARS
            self._current_mic_level = 0.0
            self._transcript_text = ""
            self._scroll_offset = 0.0
            self.stop_btn.set_visible(True)

        elif state == "processing":
            lower = text.lower()
            if "clean" in lower:
                self.status_title = "Cleaning..."
                self.status_subtitle = "Formatting your text"
            elif "transcrib" in lower:
                self.status_title = "Transcribing..."
                self.status_subtitle = "Converting speech to text"
            else:
                self.status_title = text
                self.status_subtitle = "Processing dictation..."
            self.stop_btn.set_visible(True)

        elif state == "error":
            self.status_title = "Error"
            self.status_subtitle = text
            self.timer_label.set_text("")
            self.stop_btn.set_visible(False)

        self.title_label.set_text(self.status_title)
        self.subtitle_label.set_text(self.status_subtitle)

        self._place_above_taskbar()
        self.win.show_all()

        if state == "error":
            self.stop_btn.set_visible(False)

        self.win.present()

        if self._tick_id is None:
            self._tick_id = GLib.timeout_add(33, self._tick)

        return False

    def _do_partial(self, text: str):
        """Update dedicated transcript strip while keeping status untouched."""
        self._transcript_text = text.strip()
        self.transcript_area.queue_draw()
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

    def _on_stop_clicked(self, button):
        if self.on_cancel:
            try:
                self.on_cancel()
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Animation Ticker (~30 FPS)
    # -------------------------------------------------------------------------

    def _tick(self):
        if self.state == "hidden":
            self._tick_id = None
            return False

        now = time.monotonic()

        # Update audio waveform levels
        if self.state == "recording":
            try:
                raw_level = max(0.0, min(1.0, float(self.get_level())))
            except Exception:
                raw_level = 0.0

            # Smooth incoming mic level
            self._current_mic_level += (raw_level - self._current_mic_level) * 0.45

            # Dynamic bar heights with bell-curve envelope
            center = (BARS - 1) / 2
            for i in range(BARS):
                norm_x = (i - center) / center
                env = math.exp(-2.2 * norm_x ** 2)
                # Subtle organic variation across bars during speech
                variation = 0.85 + 0.15 * math.sin(i * 0.65 + now * 7.0)
                target_h = min(1.0, self._current_mic_level * 1.6 * variation) * env
                # Resting baseline so bars remain visible
                target_h = max(0.05 * env, target_h)
                self._bar_heights[i] += (target_h - self._bar_heights[i]) * 0.38

            # Update timer
            elapsed = int(now - self._recording_start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60
            self.timer_label.set_text(f"{minutes}:{seconds:02d}")

        # Caret blinking (~1.5 Hz)
        self._caret_timer += 0.033
        if self._caret_timer >= 0.45:
            self._caret_visible = not self._caret_visible
            self._caret_timer = 0.0

        # Redraw dynamic areas
        self.mic_area.queue_draw()
        self.waveform_area.queue_draw()
        self.transcript_area.queue_draw()

        return True

    # -------------------------------------------------------------------------
    # Cairo Drawing: Microphone Indicator
    # -------------------------------------------------------------------------

    def _on_draw_mic(self, area, cr):
        cx, cy = 21.0, 21.0
        now = time.monotonic()

        if self.state == "recording":
            accent_color = COLOR_TEAL
            # Subtle breathing pulse ring
            pulse_r = 19.0 + 1.6 * math.sin(now * 4.5)
            pulse_a = 0.14 + 0.14 * math.sin(now * 4.5)
            cr.set_source_rgba(*accent_color, pulse_a)
            cr.set_line_width(1.8)
            cr.arc(cx, cy, pulse_r, 0, 2 * math.pi)
            cr.stroke()
        elif self.state == "processing":
            accent_color = COLOR_CYAN
        else:
            accent_color = COLOR_ORANGE

        # Outer ring
        cr.set_source_rgba(*accent_color, 0.85)
        cr.set_line_width(1.8)
        cr.arc(cx, cy, 16.5, 0, 2 * math.pi)
        cr.stroke()

        # Inner dark core
        cr.set_source_rgba(11 / 255, 26 / 255, 36 / 255, 0.95)
        cr.arc(cx, cy, 15.5, 0, 2 * math.pi)
        cr.fill()

        # Microphone glyph
        cr.set_source_rgba(*accent_color, 1.0)
        # Capsule
        cr.arc(cx, cy - 2.5, 3.2, math.pi, 2 * math.pi)
        cr.arc(cx, cy + 1.5, 3.2, 0, math.pi)
        cr.close_path()
        cr.fill()

        # U-shaped cradle
        cr.set_line_width(1.4)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.arc(cx, cy + 0.5, 6.0, 0, math.pi)
        cr.stroke()

        # Stem & Foot
        cr.move_to(cx, cy + 6.5)
        cr.line_to(cx, cy + 9.5)
        cr.stroke()

        cr.move_to(cx - 3.5, cy + 9.5)
        cr.line_to(cx + 3.5, cy + 9.5)
        cr.stroke()

        return False

    # -------------------------------------------------------------------------
    # Cairo Drawing: Waveform
    # -------------------------------------------------------------------------

    def _on_draw_waveform(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        now = time.monotonic()

        slot = w / BARS
        bar_w = min(3.8, max(2.5, slot * 0.45))
        cr.set_line_width(bar_w)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)

        center = (BARS - 1) / 2

        if self.state == "recording":
            # Teal -> Sky Blue gradient
            grad = cairo.LinearGradient(0, 0, w, 0)
            grad.add_color_stop_rgba(0, *COLOR_TEAL, 0.95)
            grad.add_color_stop_rgba(1, *COLOR_CYAN, 0.95)
            cr.set_source(grad)

            for i in range(BARS):
                v = self._bar_heights[i]
                bh = max(4.0, v * (h - 6.0))
                x = i * slot + slot / 2
                cr.move_to(x, (h - bh) / 2)
                cr.line_to(x, (h + bh) / 2)
                cr.stroke()

        elif self.state == "processing":
            # Traveling sine wave in cyan/indigo
            grad = cairo.LinearGradient(0, 0, w, 0)
            grad.add_color_stop_rgba(0, *COLOR_CYAN, 0.95)
            grad.add_color_stop_rgba(1, *COLOR_INDIGO, 0.95)
            cr.set_source(grad)

            for i in range(BARS):
                norm_x = (i - center) / center
                env = math.exp(-2.0 * norm_x ** 2)
                phase = (i / BARS) * 3.5 - now * 4.5
                pulse = 0.25 + 0.55 * (0.5 + 0.5 * math.sin(phase))
                bh = max(4.0, (pulse * env) * (h - 6.0))
                x = i * slot + slot / 2
                cr.move_to(x, (h - bh) / 2)
                cr.line_to(x, (h + bh) / 2)
                cr.stroke()

        else:  # Error state
            cr.set_source_rgba(*COLOR_ORANGE, 0.6)
            for i in range(BARS):
                x = i * slot + slot / 2
                cr.move_to(x, (h - 4.0) / 2)
                cr.line_to(x, (h + 4.0) / 2)
                cr.stroke()

        return False

    # -------------------------------------------------------------------------
    # Cairo Drawing: Live Transcript Strip
    # -------------------------------------------------------------------------

    def _on_draw_transcript(self, area, cr):
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        r = 19.0

        # --- Inset Glass Pill Background -------------------------------------
        cr.set_source_rgba(*COLOR_BG_TRANSCRIPT)
        cr.arc(r, r, r, math.pi / 2, 3 * math.pi / 2)
        cr.line_to(w - r, 0)
        cr.arc(w - r, r, r, -math.pi / 2, math.pi / 2)
        cr.line_to(r, h)
        cr.close_path()
        cr.fill()

        # Inset Border
        cr.set_source_rgba(*COLOR_BORDER_TRANSCRIPT)
        cr.set_line_width(1.0)
        cr.arc(r, r, r, math.pi / 2, 3 * math.pi / 2)
        cr.line_to(w - r, 0)
        cr.arc(w - r, r, r, -math.pi / 2, math.pi / 2)
        cr.line_to(r, h)
        cr.close_path()
        cr.stroke()

        # --- Right Circular Chevron Badge (>) --------------------------------
        bx, by = w - 22.0, h / 2
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.05)
        cr.arc(bx, by, 9.5, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgba(1.0, 1.0, 1.0, 0.12)
        cr.set_line_width(1.0)
        cr.arc(bx, by, 9.5, 0, 2 * math.pi)
        cr.stroke()

        # Vector Chevron
        cr.set_source_rgba(*COLOR_TEXT_SECONDARY, 0.9)
        cr.set_line_width(1.4)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.move_to(bx - 2.5, by - 3.5)
        cr.line_to(bx + 1.5, by)
        cr.line_to(bx - 2.5, by + 3.5)
        cr.stroke()

        # --- Transcript Text & Caret -----------------------------------------
        text = self._transcript_text
        is_placeholder = not text
        if is_placeholder:
            if self.state == "recording":
                text = "Listening for speech..."
            else:
                text = ""

        layout = PangoCairo.create_layout(cr)
        desc = Pango.FontDescription.from_string("Sans 11")
        layout.set_font_description(desc)
        layout.set_text(text, -1)
        tw, th = layout.get_pixel_size()

        pad_l = 18.0
        pad_r = 42.0
        avail_w = max(50.0, w - pad_l - pad_r)

        # Smooth horizontal scrolling so latest text is always visible
        content_w = tw + 10.0
        if content_w <= avail_w:
            target_scroll = 0.0
        else:
            target_scroll = content_w - avail_w + 4.0

        self._scroll_offset += (target_scroll - self._scroll_offset) * 0.28
        self._scroll_offset = max(0.0, min(self._scroll_offset, target_scroll + 1.0))

        # Viewport clipping
        cr.save()
        cr.rectangle(pad_l, 0, avail_w, h)
        cr.clip()

        tx = pad_l - self._scroll_offset
        ty = (h - th) / 2

        if is_placeholder:
            cr.set_source_rgba(*COLOR_TEXT_PLACEHOLDER, 0.8)
        else:
            cr.set_source_rgba(*COLOR_TEXT_PRIMARY, 1.0)

        cr.move_to(tx, ty)
        PangoCairo.show_layout(cr, layout)

        # Blinking caret
        if self._caret_visible and (not is_placeholder or self.state == "recording"):
            cx = tx + tw + 2.0
            cr.set_source_rgba(*COLOR_TEAL, 0.95)
            cr.set_line_width(1.4)
            cr.move_to(cx, ty + 1.0)
            cr.line_to(cx, ty + th - 1.0)
            cr.stroke()

        # Left edge fade mask when text has scrolled off
        if self._scroll_offset > 2.0:
            fade_w = 28.0
            fade_grad = cairo.LinearGradient(pad_l, 0, pad_l + fade_w, 0)
            fade_grad.add_color_stop_rgba(0.0, *COLOR_BG_TRANSCRIPT)
            fade_grad.add_color_stop_rgba(1.0, COLOR_BG_TRANSCRIPT[0], COLOR_BG_TRANSCRIPT[1], COLOR_BG_TRANSCRIPT[2], 0.0)
            cr.set_source(fade_grad)
            cr.rectangle(pad_l, 0, fade_w, h)
            cr.fill()

        cr.restore()
        return False
