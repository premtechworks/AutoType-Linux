"""Unit tests for ui/gtk_preferences.py (pure GTK3 libhandy replacements)."""
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
import pytest

from ui.gtk_preferences import (
    ActionRow,
    ExpanderRow,
    PreferencesGroup,
    PreferencesPage,
    PreferencesWindow,
)


def test_action_row_title_and_subtitle():
    row = ActionRow(title="Test Row", subtitle="Test Subtitle")
    assert row.get_title() == "Test Row"
    assert row.get_subtitle() == "Test Subtitle"

    row.set_title("Updated Title")
    row.set_subtitle("Updated Subtitle")
    assert row.get_title() == "Updated Title"
    assert row.get_subtitle() == "Updated Subtitle"

    # Clearing subtitle hides it
    row.set_subtitle(None)
    assert row.get_subtitle() == ""


def test_action_row_icon():
    row = ActionRow("Icon Row")
    row.set_icon_name("audio-input-microphone-symbolic")
    assert row._icon is not None

    row.set_icon_name(None)
    assert row._icon is None


def test_action_row_activatable_switch():
    row = ActionRow("Switch Row")
    switch = Gtk.Switch()
    switch.set_active(False)
    row.add(switch)
    row.set_activatable_widget(switch)

    activated_events = []
    row.connect("activated", lambda r: activated_events.append(True))

    assert switch.get_active() is False
    row.activate()
    assert switch.get_active() is True
    assert len(activated_events) == 1

    row.activate()
    assert switch.get_active() is False
    assert len(activated_events) == 2


def test_action_row_empty_title_embeds_widget():
    """Inner ActionRow without title/subtitle should pack widget as full-width child."""
    inner = ActionRow()
    scrolled = Gtk.ScrolledWindow()
    inner.add(scrolled)
    # ScrolledWindow should be packed in main box
    assert scrolled in inner._box.get_children()


def test_expander_row_expansion():
    expander = ExpanderRow("Expander", "Subtitle")
    assert expander.get_title() == "Expander"
    assert expander.get_subtitle() == "Subtitle"
    assert expander.get_expanded() is False

    child1 = ActionRow("Child 1")
    expander.add(child1)
    assert child1 in expander._child_box.get_children()

    expander.set_expanded(True)
    assert expander.get_expanded() is True

    expander.set_expanded(False)
    assert expander.get_expanded() is False

    # Toggle via activate
    expander.activate()
    assert expander.get_expanded() is True

    # Disable expansion
    expander.set_enable_expansion(False)
    expander.activate()
    # Stays True because expansion is disabled
    assert expander.get_expanded() is True


def test_preferences_group():
    group = PreferencesGroup("Group Title", "Group Description")
    row = ActionRow("Row 1")
    group.add(row)
    assert row in group._listbox.get_children()

    btn = Gtk.Button(label="Test Button")
    group.add(btn)
    # Non-row widgets are packed into the group box below the listbox
    assert btn in group.get_children()


def test_preferences_page_and_window():
    win = PreferencesWindow()
    page1 = PreferencesPage("General", "preferences-system-symbolic")
    page2 = PreferencesPage("Speech", "audio-volume-high-symbolic")

    group = PreferencesGroup("Behavior")
    group.add(ActionRow("Row 1"))
    page1.add(group)

    win.add(page1)
    win.add(page2)

    children = win._stack.get_children()
    assert len(children) == 2
    assert page1 in children
    assert page2 in children
