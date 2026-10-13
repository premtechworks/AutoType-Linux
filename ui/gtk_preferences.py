"""Plain GTK3 drop-in replacements for libhandy preference widgets.

Provides:
- ActionRow: Gtk.ListBoxRow with title, subtitle, icon, and right-aligned action widget.
- ExpanderRow: Gtk.ListBoxRow with collapsible child container using Gtk.Revealer.
- PreferencesGroup: Gtk.Box with header labels and a rounded Gtk.ListBox card.
- PreferencesPage: Gtk.ScrolledWindow with centered margins.
- PreferencesWindow: Gtk.Window with Gtk.HeaderBar and Gtk.StackSwitcher.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, GObject, Gtk

_CSS_INITIALIZED = False


def _init_css():
    global _CSS_INITIALIZED
    if _CSS_INITIALIZED:
        return
    css = """
    .pref-group-box {
        border-radius: 8px;
        border: 1px solid alpha(currentColor, 0.15);
    }
    .pref-group-box row {
        border-bottom: 1px solid alpha(currentColor, 0.08);
    }
    .pref-group-box row:last-child {
        border-bottom: none;
    }
    """
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        _CSS_INITIALIZED = True
    except Exception:
        pass


class ActionRow(Gtk.ListBoxRow):
    """Two-column preference row (title + subtitle on left; control/action on right)."""

    __gsignals__ = {
        "activated": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, title: str = "", subtitle: str | None = None):
        super().__init__()
        self.set_activatable(False)
        self.set_selectable(False)
        self.connect("activate", self._on_activated)

        self._box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._box.set_margin_start(12)
        self._box.set_margin_end(12)
        self._box.set_margin_top(8)
        self._box.set_margin_bottom(8)
        super().add(self._box)

        self._icon: Gtk.Image | None = None

        # Text container (vertical box with title + subtitle)
        self._text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._text_box.set_valign(Gtk.Align.CENTER)
        self._title_label = Gtk.Label(xalign=0)
        self._title_label.set_line_wrap(True)
        self._text_box.pack_start(self._title_label, False, False, 0)
        self._title_label.set_no_show_all(True)

        self._subtitle_label = Gtk.Label(xalign=0)
        self._subtitle_label.set_line_wrap(True)
        self._subtitle_label.get_style_context().add_class("dim-label")
        self._text_box.pack_start(self._subtitle_label, False, False, 0)
        self._subtitle_label.set_no_show_all(True)

        self._box.pack_start(self._text_box, True, True, 0)
        self._text_box.set_no_show_all(True)

        # Right-aligned control container
        self._action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._action_box.set_valign(Gtk.Align.CENTER)
        self._box.pack_end(self._action_box, False, False, 0)

        self._activatable_widget: Gtk.Widget | None = None

        if title:
            self.set_title(title)
        else:
            self._title_label.hide()
            self._text_box.hide()
        if subtitle:
            self.set_subtitle(subtitle)

    def set_title(self, title: str):
        if title:
            self._title_label.set_text(title)
            self._title_label.set_no_show_all(False)
            self._title_label.show()
            self._text_box.set_no_show_all(False)
            self._text_box.show()
        else:
            self._title_label.set_text("")
            self._title_label.set_no_show_all(True)
            self._title_label.hide()
            if not self._subtitle_label.get_text():
                self._text_box.set_no_show_all(True)
                self._text_box.hide()

    def get_title(self) -> str:
        return self._title_label.get_text()

    def set_subtitle(self, subtitle: str | None):
        if subtitle:
            self._subtitle_label.set_text(subtitle)
            self._subtitle_label.set_no_show_all(False)
            self._subtitle_label.show()
            self._text_box.set_no_show_all(False)
            self._text_box.show()
        else:
            self._subtitle_label.set_text("")
            self._subtitle_label.set_no_show_all(True)
            self._subtitle_label.hide()
            if not self._title_label.get_text():
                self._text_box.set_no_show_all(True)
                self._text_box.hide()

    def get_subtitle(self) -> str:
        return self._subtitle_label.get_text()

    def set_icon_name(self, icon_name: str | None):
        if self._icon is not None:
            self._box.remove(self._icon)
            self._icon = None
        if icon_name:
            self._icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON)
            self._icon.set_valign(Gtk.Align.CENTER)
            self._box.pack_start(self._icon, False, False, 0)
            self._box.reorder_child(self._icon, 0)
            self._icon.show()

    def add(self, widget: Gtk.Widget):
        """ActionRow.add() places the control right-aligned, or fills row if no title."""
        if not self._title_label.get_text() and not self._subtitle_label.get_text():
            self._box.pack_start(widget, True, True, 0)
        else:
            self._action_box.pack_end(widget, False, False, 0)

    def set_activatable_widget(self, widget: Gtk.Widget):
        self._activatable_widget = widget
        self.set_activatable(True)

    def _on_activated(self, _row):
        if isinstance(self._activatable_widget, Gtk.Switch):
            self._activatable_widget.set_active(not self._activatable_widget.get_active())
        elif self._activatable_widget:
            self._activatable_widget.grab_focus()
        self.emit("activated")


class ExpanderRow(Gtk.ListBoxRow):
    """Expandable disclosure container for nested settings rows."""

    def __init__(self, title: str = "", subtitle: str | None = None):
        super().__init__()
        self.set_activatable(True)
        self.set_selectable(False)

        self._main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        super().add(self._main_vbox)

        # Header row
        self._header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._header_box.set_margin_start(12)
        self._header_box.set_margin_end(12)
        self._header_box.set_margin_top(8)
        self._header_box.set_margin_bottom(8)
        self._main_vbox.pack_start(self._header_box, False, False, 0)

        # Title/subtitle
        self._text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._text_box.set_valign(Gtk.Align.CENTER)
        self._title_label = Gtk.Label(xalign=0)
        self._title_label.set_line_wrap(True)
        self._text_box.pack_start(self._title_label, False, False, 0)

        self._subtitle_label = Gtk.Label(xalign=0)
        self._subtitle_label.set_line_wrap(True)
        self._subtitle_label.get_style_context().add_class("dim-label")
        self._text_box.pack_start(self._subtitle_label, False, False, 0)
        self._subtitle_label.set_no_show_all(True)

        self._header_box.pack_start(self._text_box, True, True, 0)

        # Chevron arrow
        self._arrow = Gtk.Image.new_from_icon_name("pan-end-symbolic", Gtk.IconSize.BUTTON)
        self._arrow.set_valign(Gtk.Align.CENTER)
        self._header_box.pack_end(self._arrow, False, False, 0)

        # Revealer for child rows
        self._revealer = Gtk.Revealer()
        self._revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._revealer.set_reveal_child(False)
        self._main_vbox.pack_start(self._revealer, False, False, 0)

        # Children ListBox inside revealer
        self._child_box = Gtk.ListBox()
        self._child_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._child_box.set_margin_start(16)
        self._child_box.set_margin_end(12)
        self._child_box.set_margin_bottom(8)
        self._revealer.add(self._child_box)

        self._enable_expansion = True
        self.connect("activate", self._toggle_expanded)

        if title:
            self.set_title(title)
        if subtitle:
            self.set_subtitle(subtitle)

    def set_title(self, title: str):
        self._title_label.set_text(title or "")

    def get_title(self) -> str:
        return self._title_label.get_text()

    def set_subtitle(self, subtitle: str | None):
        if subtitle:
            self._subtitle_label.set_text(subtitle)
            self._subtitle_label.set_no_show_all(False)
            self._subtitle_label.show()
        else:
            self._subtitle_label.set_text("")
            self._subtitle_label.set_no_show_all(True)
            self._subtitle_label.hide()

    def get_subtitle(self) -> str:
        return self._subtitle_label.get_text()

    def add(self, widget: Gtk.Widget):
        if isinstance(widget, Gtk.ListBoxRow):
            self._child_box.add(widget)
        else:
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            row.set_activatable(False)
            row.add(widget)
            self._child_box.add(row)

    def set_expanded(self, expanded: bool):
        self._revealer.set_reveal_child(expanded)
        icon = "pan-down-symbolic" if expanded else "pan-end-symbolic"
        self._arrow.set_from_icon_name(icon, Gtk.IconSize.BUTTON)

    def get_expanded(self) -> bool:
        return self._revealer.get_reveal_child()

    def set_enable_expansion(self, enable: bool):
        self._enable_expansion = enable
        self.set_activatable(enable)
        self._arrow.set_visible(enable)

    def _toggle_expanded(self, _row):
        if self._enable_expansion:
            self.set_expanded(not self.get_expanded())


class PreferencesGroup(Gtk.Box):
    """Wraps a set of rows into a card with a header title and descriptive subtitle."""

    def __init__(self, title: str = "", description: str | None = None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        _init_css()

        self._title_label = Gtk.Label(xalign=0)
        self._title_label.get_style_context().add_class("heading")
        self._title_label.set_no_show_all(True)
        self.pack_start(self._title_label, False, False, 0)

        self._desc_label = Gtk.Label(xalign=0)
        self._desc_label.get_style_context().add_class("dim-label")
        self._desc_label.set_line_wrap(True)
        self._desc_label.set_no_show_all(True)
        self.pack_start(self._desc_label, False, False, 0)

        # Rounded card ListBox
        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self._listbox.get_style_context().add_class("frame")
        self._listbox.get_style_context().add_class("pref-group-box")
        self.pack_start(self._listbox, False, False, 0)

        if title:
            self.set_title(title)
        if description:
            self.set_description(description)

    def set_title(self, title: str):
        if title:
            self._title_label.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
            self._title_label.set_no_show_all(False)
            self._title_label.show()
        else:
            self._title_label.set_no_show_all(True)
            self._title_label.hide()

    def set_description(self, desc: str | None):
        if desc:
            self._desc_label.set_text(desc)
            self._desc_label.set_no_show_all(False)
            self._desc_label.show()
        else:
            self._desc_label.set_no_show_all(True)
            self._desc_label.hide()

    def add(self, widget: Gtk.Widget):
        if isinstance(widget, Gtk.ListBoxRow):
            self._listbox.add(widget)
        else:
            self.pack_start(widget, False, False, 0)


class PreferencesPage(Gtk.ScrolledWindow):
    """Represents one category/tab and groups vertical preference groups."""

    def __init__(self, title: str = "", icon_name: str | None = None):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._box.set_margin_start(24)
        self._box.set_margin_end(24)
        self._box.set_margin_top(24)
        self._box.set_margin_bottom(24)
        super().add(self._box)

        self._title = title
        self._icon_name = icon_name

    def set_title(self, title: str):
        self._title = title

    def get_title(self) -> str:
        return self._title

    def set_icon_name(self, icon_name: str | None):
        self._icon_name = icon_name

    def get_icon_name(self) -> str | None:
        return self._icon_name

    def add(self, widget: Gtk.Widget):
        if widget is not self._box:
            self._box.pack_start(widget, False, False, 0)


class PreferencesWindow(Gtk.Window):
    """Window shell providing page switching tabs and responsive layout."""

    def __init__(self):
        super().__init__()
        self.set_title("AutoType Settings")
        self.set_default_size(640, 576)

        self._headerbar = Gtk.HeaderBar()
        self._headerbar.set_show_close_button(True)
        self._headerbar.set_title("AutoType Settings")
        self.set_titlebar(self._headerbar)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_transition_duration(200)

        self._switcher = Gtk.StackSwitcher()
        self._switcher.set_stack(self._stack)
        self._headerbar.set_custom_title(self._switcher)

        super().add(self._stack)

    def set_search_enabled(self, _enabled: bool):
        pass  # compatibility no-op

    def add(self, page: Gtk.Widget):
        if isinstance(page, PreferencesPage):
            title = page.get_title() or "Page"
            name = title.lower().replace(" ", "_")
            self._stack.add_titled(page, name, title)
        elif page is not self._stack:
            super().add(page)
