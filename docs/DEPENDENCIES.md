# AutoType Dependency Architecture & Packaging Guide

This document specifies the system-level and runtime dependencies for **AutoType** (an X11 voice-typing daemon for Linux Mint XFCE and other X11 desktop environments), detailing the reduction of external system-tool binaries and providing target packaging specifications for `.deb`, `.rpm`, `AppImage`, and `Flatpak`.

---

## 1. Dependency Inventory: Before vs. After

| Dependency / Component | Initial State (Before) | Current State (After) | Role & Implementation Details |
|---|---|---|---|
| **`xclip`** | **Required** system binary (`subprocess.run`) | **Legacy Fallback Only** (Optional) | Replaced by pure GTK3 `Gtk.Clipboard` (`Gdk.SELECTION_CLIPBOARD` and `Gdk.SELECTION_PRIMARY`). Captures previous clipboard state, pastes dictation, and safely restores prior text or image payloads without external processes. |
| **`xdotool`** | **Required** system binary (`subprocess.run`) | **Fallback Only** (Optional) | Active window title/class introspection and keystroke synthesis (`Ctrl+V` / `Ctrl+Shift+V`) now use direct X11 protocol calls via `python-xlib` and the X11 `XTEST` extension. `xdotool` is retained purely as a fallback. |
| **`libhandy` (`gir1.2-handy-1`)** | **Required** C/GObject library | **Eliminated** (0 dependencies) | Fully replaced by native GTK3 widgets (`ActionRow`, `ExpanderRow`, `PreferencesGroup`, `PreferencesPage`, `PreferencesWindow`) in `ui/gtk_preferences.py`. Settings GUI now runs on vanilla GTK3. |
| **`notify-send`** | Hard subprocess invocation | **Optional** (0 hard dependency) | Dispatches notifications via `notify-send` if present on `$PATH`. If absent, gracefully skips notification bubbles and logs a `DEBUG` trace without error. |
| **`pactl`** | Subprocess invocation | **Optional** (Bluetooth helper only) | Default audio input device queries now use PortAudio (`sounddevice.query_devices`). `pactl` is retained solely for optional Bluetooth headset profile auto-switching (A2DP ↔ HSP/HFP). |
| **`portaudio` (`libportaudio2`)** | Required C library | **Required** | Low-latency audio stream capture via `sounddevice`. |
| **`python-xlib`** | Transitive pip dependency (via `pynput`) | **Direct Runtime Component** | Native X11 protocol library used for window queries and XTest keystroke injection over the X11 Unix socket. |
| **`python3-gi` / `gir1.2-gtk-3.0`** | Required | **Required** | GTK3 widget toolkit and event loop for floating overlay, tray icon, settings GUI, and clipboard management. |

---

## 2. Technical Evaluation & Implementation

### 2.1. Clipboard Management (`xclip` → `Gtk.Clipboard`)
- **Primary Mechanism**: AutoType integrates with the GTK3 main loop. It interfaces directly with `Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)` and `Gtk.Clipboard.get(Gdk.SELECTION_PRIMARY)` using PyGObject.
- **Safety & Resilience**:
  - Non-text payloads (e.g., image `GdkPixbuf`, custom mime types) are checked via `clip.wait_is_text_available()` and `clip.wait_is_image_available()`.
  - Empty or non-text payloads return `None` or image objects rather than raising unhandled exceptions or triggering subprocess errors.
  - Restoration handles `None` (`clip.clear()`), strings/bytes (`clip.set_text()`), and images (`clip.set_image()`), followed by `clip.store()`.
- **Fallback**: If GTK clipboard calls fail (e.g., uninitialized display in pure headless test harness), AutoType falls back to `xclip` if present.

### 2.2. Window Introspection and Keystrokes (`xdotool` vs. `python-xlib`)
- **Trade-off Analysis**:
  - *Option A (`xdotool`)*: Simple external binary, but incurs process spawning overhead (`fork`/`exec`), fails when the binary is missing, and is problematic inside restricted container sandboxes (Flatpak).
  - *Option B (`python-xlib`)*: Pure Python implementation communicating directly over the X11 Unix domain socket (`/tmp/.X11-unix/X0`). Already present in the runtime environment as a transitive dependency of `pynput`.
- **Implementation**:
  - **Window Title & Class**: Interrogates the X11 root window for atom `_NET_ACTIVE_WINDOW`, reads `_NET_WM_NAME` (`UTF8_STRING`) or `WM_NAME` for the window title, and reads `WM_CLASS` tuples for application class matching.
  - **Keystroke Synthesis**: Translates keysyms (`XK_Control_L`, `XK_Shift_L`, `XK_v`) to keycodes via `Display.keysym_to_keycode()`, injects `KeyPress` and `KeyRelease` events using `Xlib.ext.xtest.fake_input`, and flushes via `Display.sync()`.
  - **Adaptive Style Profiles**: The window title and class matching logic in `desktop/profiles.py` (`code`, `email`, `chat`, `prose`) functions identically without subprocesses.
  - **Fallback**: If `python-xlib` or the `XTEST` extension is unavailable, AutoType falls back to `xdotool key --clearmodifiers <keys>`.

### 2.3. Audio Device Handling (`pactl` Reduction)
- **Primary Mechanism**: Querying audio capture devices and default microphone names is handled via PortAudio (`sounddevice.query_devices(kind="input")`).
- **Bluetooth Headset Profiles**:
  - AutoType supports auto-switching Bluetooth headsets from high-latency A2DP playback to HSP/HFP bidirectional voice mode during recording.
  - Controlling sound-server card profiles requires communication with PulseAudio/PipeWire. `pactl` is used when available to run `set-card-profile`.
  - If `pactl` is absent, audio capture continues using the default PortAudio source, logging a debug notice that Bluetooth profile auto-switching was skipped.

### 2.4. Desktop Notifications (`notify-send`)
- Dispatches notifications via `notify-send` if found on `$PATH`.
- If missing, logs a `DEBUG` message (`log.debug("notify-send not found; skipping notification: %s - %s", title, message)`) and returns without raising an exception. No extra third-party notification dependencies are added.

### 2.5. Settings GUI (`libhandy` Removal)
- **Problem**: `libhandy-1` (`gir1.2-handy-1`) is not installed by default on XFCE/MATE and non-GNOME environments, causing launch failures on Linux Mint XFCE unless manually installed.
- **Solution**: Implemented native GTK3 drop-in widgets in `ui/gtk_preferences.py`:
  - `ActionRow`: Subclasses `Gtk.ListBoxRow` with title, subtitle, icon, right-aligned action widget, and support for `"activated"` signal and switch toggling.
  - `ExpanderRow`: Subclasses `Gtk.ListBoxRow` with disclosure chevron and `Gtk.Revealer` containing a nested `Gtk.ListBox` for child rows.
  - `PreferencesGroup`: Subclasses `Gtk.Box` with section title, description, and rounded card styling (`.pref-group-box`).
  - `PreferencesPage`: Subclasses `Gtk.ScrolledWindow` wrapping vertical groups with 24px margins.
  - `PreferencesWindow`: Subclasses `Gtk.Window` with `Gtk.HeaderBar` and centered `Gtk.StackSwitcher`.
- **Result**: `libhandy` (`Handy.init()`, `gir1.2-handy-1`) is 100% removed. The GUI maintains identical visual layout, grouping, and expander functionality on standard GTK3.

---

## 3. Remaining External Runtime Dependencies

The mandatory system dependencies are now reduced to:

1. **GTK3 & GObject Introspection (`python3-gi`, `gir1.2-gtk-3.0`)**:
   - *Reason*: Powers the floating glassmorphic overlay widget, the system tray icon, the Settings GUI, and clipboard management.
2. **PortAudio (`libportaudio2`)**:
   - *Reason*: Underlies `sounddevice` for low-latency microphone audio streaming and capture.
3. **Python 3.10+ & X11 Server**:
   - *Reason*: Host Python runtime and active X11 display server (`DISPLAY`).

### Optional / Fallback System Binaries
- **`xdotool`** *(Optional Fallback)*: Used only if `python-xlib` or XTest extension encounters an unexpected error.
- **`xclip`** *(Optional Fallback)*: Used only if Gtk clipboard fails in a non-GUI headless environment.
- **`pactl`** *(Optional Feature)*: Required only for Bluetooth HSP/HFP profile switching.
- **`notify-send`** *(Optional Feature)*: Required only for displaying native desktop notification bubbles.

---

## 4. Packaging Guidelines

### 4.1. Debian / Ubuntu / Linux Mint (`.deb`)
- **Package Architecture**: `all` (pure Python with C-library bindings).
- **Required Dependencies (`Depends`)**:
  ```control
  Depends: python3 (>= 3.10),
           python3-gi,
           python3-gi-cairo,
           gir1.2-gtk-3.0,
           libportaudio2,
           python3-pip | python3-venv
  ```
- **Recommended / Suggested Dependencies (`Recommends` / `Suggests`)**:
  ```control
  Recommends: xdotool, libnotify-bin
  Suggests: pulseaudio-utils, xclip
  ```
- *Note*: `gir1.2-handy-1` is **no longer required** in `Depends`.

### 4.2. Fedora / RHEL (`.rpm`)
- **Package Architecture**: `noarch`.
- **Requires**:
  ```spec
  Requires: python3 >= 3.10
  Requires: python3-gobject
  Requires: gtk3
  Requires: portaudio
  Recommends: xdotool
  Recommends: libnotify
  Suggests: pulseaudio-utils
  ```

### 4.3. AppImage
- Bundle Python 3.10+, PyGObject (`gi`), GTK3 libraries, PortAudio (`libportaudio2.so`), and Python wheels.
- Because `python-xlib` communicates directly with `/tmp/.X11-unix/X0`, keystroke injection and window inspection function out of the box without bundling `xdotool`.

### 4.4. Flatpak
- **Runtime**: `org.gnome.Platform` (version 45 or 46) or `org.freedesktop.Platform`.
- **Permissions (`finish-args`)**:
  - `--socket=x11`: Required for X11 protocol access, active window introspection, and XTest keystroke injection.
  - `--socket=pulseaudio`: Required for microphone capture via PulseAudio / PipeWire.
  - `--talk-name=org.freedesktop.Notifications`: DBus notification portal (eliminates need for `notify-send` binary).
- *Advantage of Dependency Reduction*: Flatpak sandboxes previously broke with `xdotool` and `xclip` because child subprocesses could not access host binaries. By moving to `python-xlib` and `Gtk.Clipboard`, AutoType operates self-contained inside the Flatpak sandbox.
