"""Mic device discovery + Bluetooth headset profile handling (PipeWire/PulseAudio).

Two real bugs were found on this machine (Oct 2026, Linux Mint XFCE,
PipeWire 1.0.5, realme Buds Wireless 5 ANC) — both are handled here:

1. **ALSA ``default`` capture does not follow PipeWire's default source.**
   PortAudio (sounddevice) with ``device=None`` opens ALSA ``default``,
   which on this system is a dsnoop/hw:0 path yielding digital silence
   (verified: ``arecord -D default`` peak 0.002 while ``arecord
   -D pipewire`` on the same machine captured the live mic at peak 0.29).
   Fix: the app's default capture device is now the ALSA ``pipewire`` PCM,
   which *does* track PipeWire's default source, so it follows Internal
   mic <-> BT headset switches automatically.

2. **mSBC decoding is broken for this headset/adapter combo.**
   With ``headset-head-unit-msbc`` active, WirePlumber logs
   ``sbc_decode failed: -3`` continuously and the mic delivers silence.
   ``headset-head-unit-cvsd`` (8 kHz) captures cleanly with zero errors.
   Fix: ``switch_bt_for_voice()`` verifies mSBC by forcing the SCO link up
   and scanning the journal for decode failures, automatically falling back
   to CVSD when mSBC is broken. (PipeWire resamples CVSD 8 kHz -> 16 kHz
   for us, so the rest of the pipeline is unchanged.)
"""
from __future__ import annotations

import re
import shutil
import subprocess
import time

SAMPLE_RATE = 16000

# Preference order for voice (mic) profiles, best first.
# NOTE: mSBC is tried first but verified — see switch_bt_for_voice().
VOICE_PROFILES = (
    "headset-head-unit-msbc",
    "headset-head-unit-cvsd",
    "headset-head-unit",
)
MUSIC_PROFILES = ("a2dp-sink", "a2dp-sink-sbc_xq")

# ALSA PCM that tracks PipeWire's default source. Hard-won: ALSA "default"
# capture on Mint XFCE is a dsnoop/hw path that yields silence even when a
# working PipeWire source exists.
PIPEWIRE_ALSA_DEVICE = "pipewire"


def _run(cmd: list[str], timeout: float = 10.0) -> str:
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    out.check_returncode()
    return out.stdout


# -- sounddevice inputs -----------------------------------------------

def list_input_devices() -> list[dict]:
    """All sounddevice devices with inputs. Never raises (returns [])."""
    try:
        import sounddevice as sd
    except Exception:
        return []
    try:
        devices = sd.query_devices()
    except Exception:
        return []
    found = []
    for i, d in enumerate(devices):
        try:
            if int(d.get("max_input_channels", 0) or 0) > 0:
                name = str(d.get("name", f"device {i}"))
                found.append({
                    "index": i,
                    "name": name,
                    "channels": int(d.get("max_input_channels", 0)),
                    "rate": d.get("default_samplerate"),
                    "is_pipewire": name.strip().lower() == "pipewire",
                    "bluetooth_hint": bool(re.search(
                        r"blue|bt|headset|handsfree|hfp|hsp|buds|airpods",
                        name, re.IGNORECASE)),
                })
        except Exception:
            continue
    return found


def resolve_mic_device(preference: str | None):
    """Map the MIC_DEVICE setting to a sounddevice ``device`` argument.

    ""/None/"default"/"auto" -> the ALSA "pipewire" PCM when present
        (tracks PipeWire's default source, i.e. follows Internal <-> BT
        switches); otherwise None (PortAudio default).
    "7"  -> int 7 (device index).
    anything else -> substring match against device names
        (case-insensitive); returns the index, or the raw string so
        PortAudio can try it directly.
    """
    if preference is None:
        preference = ""
    pref = str(preference).strip()
    if pref == "" or pref.lower() in ("default", "auto", "system", "none"):
        for d in list_input_devices():
            if d.get("is_pipewire"):
                return d["index"]
        return PIPEWIRE_ALSA_DEVICE  # try by name; harmless if missing
    if re.fullmatch(r"\d+", pref):
        return int(pref)
    for d in list_input_devices():
        if pref.lower() in d["name"].lower():
            return d["index"]
    return pref  # let PortAudio try it as a name


# -- PipeWire / PulseAudio ---------------------------------------------

# -- explicit capture target (the monitor-linking fix) -------------------

def resolve_capture_target(preference: str | int | None) -> str:
    """Map a mic preference to a PipeWire *source node name*.

    PortAudio sets no target, and on this system WirePlumber then links the
    capture stream to the default sink's *monitor* (output loopback) instead
    of the default source — yielding digital silence. Pinning
    ``target.object`` to the intended source bypasses that entirely.
    Returns "" when no explicit target is needed/possible.
    """
    pref = str(preference or "").strip().lower()
    if pref in ("", "default", "auto", "system", "none", "pipewire"):
        target = default_source_name()
        return "" if target.endswith(".monitor") else target
    if any(k in pref for k in
           ("blue", "buds", "headset", "handsfree", "hfp", "hsp")):
        for s in list_pipewire_sources():
            if s["is_bluez"] and not s["is_monitor"] and "input" in s["name"]:
                return s["name"]
        return ""
    if any(k in pref for k in
           ("built", "internal", "analog", "hda", "hw:0", "sysdefault")):
        for s in list_pipewire_sources():
            if not s["is_bluez"] and not s["is_monitor"]:
                return s["name"]
        return ""
    if pref.isdigit():
        for d in list_input_devices():
            if str(d["index"]) == pref and d.get("is_pipewire"):
                target = default_source_name()
                return "" if target.endswith(".monitor") else target
        return ""
    return ""


def capture_target_for(configured=None) -> str:
    """Target source for a Recorder/MicrophoneStream instance."""
    if configured is None:
        try:
            import config
            pref = config.mic_device()
        except Exception:
            pref = ""
        return resolve_capture_target(pref)
    if isinstance(configured, int):
        for d in list_input_devices():
            if d["index"] == configured:
                return resolve_capture_target(d["name"])
        return ""
    return resolve_capture_target(str(configured))


import contextlib as _contextlib


@_contextlib.contextmanager
def pipewire_capture_target(target: str):
    """Pin PipeWire-ALSA capture to ``target`` source while opening a stream.

    The pipewire ALSA plugin reads PIPEWIRE_PROPS at PCM open time; setting
    target.object there overrides WirePlumber's (broken, here) auto-linking.
    No-op when target is empty or already pinned by the user.
    """
    import os
    key = "PIPEWIRE_PROPS"
    if not target:
        yield
        return
    old = os.environ.get(key, "")
    if "target.object" in old:
        yield
        return
    inner = old.strip()
    if inner.startswith("{") and inner.endswith("}"):
        inner = inner[1:-1].strip()
    piece = f'target.object="{target}"'
    os.environ[key] = "{ " + (inner + " " + piece if inner else piece) + " }"
    try:
        yield
    finally:
        if old:
            os.environ[key] = old
        else:
            os.environ.pop(key, None)

def _have_pactl() -> bool:
    return shutil.which("pactl") is not None


def default_source_name() -> str:
    """PipeWire default source (e.g. bluez_input.... or alsa_input...)."""
    if not _have_pactl():
        return ""
    try:
        return _run(["pactl", "get-default-source"]).strip()
    except Exception:
        return ""


def list_pipewire_sources() -> list[dict]:
    """Parse ``pactl list sources short``. Never raises."""
    if not _have_pactl():
        return []
    try:
        out = _run(["pactl", "list", "sources", "short"])
    except Exception:
        return []
    sources = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            sources.append({
                "name": parts[1],
                "raw": line.strip(),
                "is_monitor": ".monitor" in parts[1],
                "is_bluez": "bluez" in parts[1].lower(),
            })
    return sources


def list_bt_cards() -> list[dict]:
    """Parse ``pactl list cards`` for bluez (Bluetooth) cards. Never raises."""
    if not _have_pactl():
        return []
    try:
        out = _run(["pactl", "list", "cards"])
    except Exception:
        return []
    cards: list[dict] = []
    current: dict | None = None
    in_profiles = False
    for line in out.splitlines():
        m = re.match(r"Card #(\d+)", line)
        if m:
            if current is not None:
                cards.append(current)
            current = {"id": m.group(1), "name": "", "alias": "",
                       "active_profile": "", "profiles": []}
            in_profiles = False
            continue
        if current is None:
            continue
        m = re.match(r"\s*Name:\s*(.+)", line)
        if m:
            current["name"] = m.group(1).strip()
            continue
        if "device.alias" in line:
            m = re.search(r'=\s*"?(.*?)"?\s*$', line)
            if m:
                current["alias"] = m.group(1).strip().strip('"')
            continue
        if re.match(r"\s*Profiles:", line):
            in_profiles = True
            continue
        if re.match(r"\s*Active Profile:\s*(.+)", line):
            m = re.match(r"\s*Active Profile:\s*(.+)", line)
            current["active_profile"] = (m.group(1).strip() if m else "")
            in_profiles = False
            continue
        if in_profiles:
            m = re.match(r"\s*([\w\-+]+):\s*(.+?)\s*\(sinks:", line)
            if m:
                current["profiles"].append({
                    "name": m.group(1),
                    "description": m.group(2).strip(),
                })
            continue
        if re.match(r"\s*Ports:", line):
            in_profiles = False
    if current is not None:
        cards.append(current)
    return [c for c in cards if "bluez" in c.get("name", "").lower()]


def bt_codec_info() -> dict:
    """Active codec per BT input node from pw-dump. Never raises."""
    info: dict[str, dict] = {}
    try:
        import json
        out = subprocess.run(["pw-dump"], capture_output=True, text=True,
                             timeout=10).stdout
        for n in json.loads(out):
            o = n.get("info", {}).get("props", {})
            name = o.get("node.name", "")
            if "bluez" in name:
                info[name] = {
                    "codec": o.get("api.bluez5.codec", ""),
                    "profile": o.get("api.bluez5.profile", ""),
                    "transport": o.get("api.bluez5.transport", ""),
                    "state": n.get("info", {}).get("state"),
                }
    except Exception:
        pass
    return info


def sbc_decode_errors_since(epoch: float) -> int:
    """Count 'sbc_decode failed' journal lines since epoch. -1 = unknown."""
    try:
        out = subprocess.run(
            ["journalctl", "--user", "-b", "-u", "pipewire", "-u", "wireplumber",
             "--no-pager", "--since", f"@{int(epoch)}"],
            capture_output=True, text=True, timeout=15).stdout
        return sum(1 for line in out.splitlines()
                   if "sbc_decode failed" in line)
    except Exception:
        return -1


def bt_voice_ready() -> tuple[bool, str]:
    """(ready, message): is any BT card exposing an input profile right now?"""
    cards = list_bt_cards()
    if not cards:
        return False, "No Bluetooth audio card found in PipeWire."
    for card in cards:
        active = card.get("active_profile", "")
        if active.startswith("headset-head-unit"):
            return True, (
                f"{card.get('alias') or card['name']}: voice profile "
                f"'{active}' active — mic should work.")
    names = ", ".join(
        f"{c.get('alias') or c['name']} [{c.get('active_profile')}]"
        for c in cards)
    return False, (
        f"BT card(s) on output-only profile ({names}). "
        "Switch to HSP/HFP to use the headset mic.")


def set_bt_profile(card: str, profile: str) -> str:
    """Switch a BT card's profile. Raises RuntimeError on failure."""
    if not _have_pactl():
        raise RuntimeError("pactl not found (install pulseaudio-utils).")
    try:
        _run(["pactl", "set-card-profile", card, profile])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Could not switch {card} to '{profile}': "
            f"{(exc.stderr or '').strip()[-300:]}") from exc
    return profile


def set_default_source(source: str) -> None:
    """Point PipeWire's default source at ``source`` (best effort)."""
    if not _have_pactl() or not source:
        return
    try:
        _run(["pactl", "set-default-source", source])
    except Exception:
        pass


def _probe_source(source: str, seconds: float = 2.5) -> dict:
    """Capture briefly and return signal stats. Never raises.

    Returns {samples, peak, rms, nonzero_ratio}. A live mic — even in a
    quiet room — always shows *some* nonzero floor (ADC/codec noise); a
    dead SCO/mSBC stream is ~100% exact zeros.
    """
    import tempfile
    stats = {"samples": 0, "peak": 0.0, "rms": 0.0, "nonzero_ratio": 0.0}
    raw = None
    if shutil.which("parec") and source:
        try:
            with tempfile.NamedTemporaryFile(suffix=".raw",
                                             delete=False) as tmp:
                raw = tmp.name
            subprocess.run(
                ["parec", "-d", source,
                 "--rate=16000", "--channels=1", "--format=s16le", raw],
                capture_output=True, timeout=seconds)
            import numpy as np
            a = np.fromfile(raw, dtype=np.int16).astype(np.float64)
            if len(a):
                stats = {"samples": len(a),
                         "peak": float(np.abs(a).max() / 32768.0),
                         "rms": float(np.sqrt(np.mean(a ** 2)) / 32768.0),
                         "nonzero_ratio": float((a != 0).sum() / len(a))}
        except Exception:
            pass
        finally:
            try:
                import os
                if raw:
                    os.unlink(raw)
            except Exception:
                pass
    return stats


def _force_sco_up(source: str, seconds: float = 2.5) -> dict:
    """Open the BT source so the SCO link + decoder run; return probe stats."""
    stats = _probe_source(source, seconds)
    if stats["samples"] == 0:
        try:
            import sounddevice as sd
            frames: list = []
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                dtype="int16", device=resolve_mic_device(""),
                                blocksize=1280,
                                callback=lambda i, f, t, s: frames.append(True)):
                time.sleep(seconds)
        except Exception:
            pass
    return stats


def _bluez_input_name() -> str:
    for s in list_pipewire_sources():
        if s["is_bluez"] and not s["is_monitor"] and "input" in s["name"]:
            return s["name"]
    return ""


# -- remembered working codec ---------------------------------------------

def _bt_state_path():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent / "data" / "bt_audio.json"


def remembered_voice_profile() -> str:
    """Last verified-working voice profile ('...msbc' / '...cvsd' / '')."""
    try:
        import json
        return str(json.loads(_bt_state_path().read_text(
            encoding="utf-8")).get("voice_profile", ""))
    except Exception:
        return ""


def remember_voice_profile(profile: str) -> None:
    try:
        import json
        p = _bt_state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"voice_profile": profile}),
                     encoding="utf-8")
    except Exception:
        pass


def switch_bt_for_voice(card: str | None = None, prefer: str = "auto",
                        verify: bool = True) -> tuple[str, str, str]:
    """Put the (first) BT card on a working HSP/HFP profile.

    ``prefer``: "auto" (remembered-good codec first, else mSBC verified
    with CVSD fallback), "msbc" or "cvsd".
    Returns (card, profile, note). Raises RuntimeError if nothing worked.

    Verification matters because mSBC is flaky on some headset/adapter
    combos (seen here: sometimes ``sbc_decode failed: -3`` storms, sometimes
    a silent SCO link with zero errors). A candidate passes only if it
    decodes with no errors AND delivers a nonzero mic floor. The working
    choice is remembered so later switches skip the broken codec.
    """
    cards = list_bt_cards()
    if not cards:
        raise RuntimeError("No Bluetooth audio card found.")
    targets = [c for c in cards
               if card in (None, c["id"], c["name"], c.get("alias"))]
    if not targets:
        raise RuntimeError(f"BT card {card!r} not found.")
    c = targets[0]
    ident = c["name"] or c["id"]
    available = {p["name"] for p in c.get("profiles", [])}

    if prefer == "msbc":
        order = ["headset-head-unit-msbc"]
    elif prefer == "cvsd":
        order = ["headset-head-unit-cvsd"]
    else:
        remembered = remembered_voice_profile()
        order = [p for p in VOICE_PROFILES if p in available]
        if remembered in order:
            order.remove(remembered)
            order.insert(0, remembered)
        order += [p for p in sorted(available)
                  if p.startswith("headset-") and p not in order]
    if not order:
        raise RuntimeError("Card offers no HSP/HFP (headset-*) profile.")
    errors = []
    fallback_note = ""
    for prof in order:
        try:
            mark = time.time()
            set_bt_profile(ident, prof)
            time.sleep(1.0)
            src = _bluez_input_name()
            set_default_source(src)
            note = f"profile '{prof}' active."
            if verify and "msbc" in prof:
                stats = _force_sco_up(src or default_source_name())
                if stats["samples"] < 8000:
                    # First capture right after a switch can fail while
                    # SCO settles — one retry before calling it dead.
                    time.sleep(1.5)
                    stats = _probe_source(src or default_source_name())
                bad = sbc_decode_errors_since(mark)
                reasons = []
                if bad > 0:
                    reasons.append(f"{bad} decoder errors")
                # Liveness: a live mic always carries ADC/codec floor.
                # Measured references: dead mSBC link -> 0 samples or
                # rms <= 1e-5; quiet-room CVSD -> rms ~5e-4, 12% nonzero.
                if stats["samples"] < 8000:
                    reasons.append(
                        f"no audio flowing ({stats['samples']} samples)")
                elif (stats["rms"] < 0.0002
                        or stats["nonzero_ratio"] < 0.01):
                    reasons.append(
                        f"silent SCO link (rms {stats['rms']:.5f}, "
                        f"nonzero {stats['nonzero_ratio'] * 100:.1f}%)")
                if bad is None or bad < 0:
                    note += " (decode health unknown — journal unreadable)."
                    remember_voice_profile(prof)
                    return ident, prof, fallback_note + note
                if reasons:
                    fallback_note = (
                        f"mSBC unusable on this headset "
                        f"({' + '.join(reasons)}) — fell back. ")
                    continue  # try next profile (CVSD)
                note += (f" mSBC verified (decoder clean, mic floor "
                         f"rms {stats['rms']:.4f}).")
                remember_voice_profile(prof)
            elif verify:
                remember_voice_profile(prof)
                time.sleep(0.5)
                note += " (CVSD needs no verification.)"
            return ident, prof, fallback_note + note
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError(
        fallback_note
        + ("; ".join(errors) or "No working HSP/HFP profile available."))


def switch_bt_for_music(card: str | None = None) -> tuple[str, str]:
    """Put the BT card back on A2DP (high-quality output, no mic)."""
    cards = list_bt_cards()
    if not cards:
        raise RuntimeError("No Bluetooth audio card found.")
    targets = [c for c in cards
               if card in (None, c["id"], c["name"], c.get("alias"))]
    if not targets:
        raise RuntimeError(f"BT card {card!r} not found.")
    errors = []
    for c in targets:
        available = {p["name"] for p in c.get("profiles", [])}
        for prof in MUSIC_PROFILES:
            if prof in available:
                try:
                    set_bt_profile(c["name"] or c["id"], prof)
                    return c["name"] or c["id"], prof
                except RuntimeError as exc:
                    errors.append(str(exc))
    raise RuntimeError("; ".join(errors) or "No A2DP profile available.")


def route_diagnosis() -> dict:
    """Describe the exact route the app will record from. Never raises."""
    diag: dict = {}
    try:
        import config
        pref = config.mic_device()
    except Exception:
        pref = ""
    try:
        diag["resolved"] = str(resolve_mic_device(pref))
    except Exception as exc:
        diag["resolved"] = f"(resolve failed: {exc})"
    diag["mic_setting"] = pref or "(empty = follow system via pipewire)"
    diag["default_source"] = default_source_name()
    try:
        diag["capture_target"] = capture_target_for(None)
    except Exception as exc:
        diag["capture_target"] = f"(failed: {exc})"
    cards = list_bt_cards()
    diag["bt_profile"] = (cards[0].get("active_profile", "") if cards
                          else "(no BT card)")
    diag["codec"] = ""
    try:
        for name, ci in bt_codec_info().items():
            if "input" in name:
                diag["codec"] = ci.get("codec", "")
    except Exception:
        pass
    try:
        diag["sbc_errors_10min"] = sbc_decode_errors_since(time.time() - 600)
    except Exception:
        diag["sbc_errors_10min"] = -1
    return diag


# -- quick mic self-test -----------------------------------------------

def quick_test(device=None, seconds: float = 3.0) -> dict:
    """Record a few seconds and report peak/RMS. Raises on silence/failure.

    ``device=None`` means "whatever the app would use" (config + pipewire
    routing), so this tests the real capture path.
    """
    import numpy as np
    import sounddevice as sd

    if device is None:
        try:
            import config
            device = resolve_mic_device(config.mic_device())
            target = capture_target_for(None)
        except Exception:
            device = resolve_mic_device("")
            target = capture_target_for("")
    else:
        target = capture_target_for(device)

    frames: list = []

    def _cb(indata, _frames, _time, _status):
        frames.append(indata.copy())

    try:
        with pipewire_capture_target(target):
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                                dtype="int16", device=device, callback=_cb):
                time.sleep(seconds)
    except Exception as exc:
        raise RuntimeError(
            f"Could not open mic ({device!r}): {exc}.") from exc
    if not frames:
        raise RuntimeError("No audio captured (empty stream).")
    audio = np.concatenate(frames, axis=0).astype(np.float32)
    peak = float(np.abs(audio).max() / 32768.0)
    rms = float(np.sqrt(np.mean(audio ** 2)) / 32768.0)
    if peak < 0.01:
        raise RuntimeError(
            f"Mic captured only silence (peak {peak:.3f} on {device!r}). "
            "If this is a Bluetooth headset, its card must be on HSP/HFP "
            "(not A2DP) — use Settings → Microphone → Headset voice mode.")
    return {"peak": round(peak, 3), "rms": round(rms, 4),
            "seconds": seconds, "device": str(device)}
