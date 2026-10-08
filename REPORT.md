# AutoType Improvement Report: Pause Resilience & Floating Stop Button

## 1. Executive Summary

This update resolves two major functional and UX challenges in AutoType:
1. **Continuous Speech Accumulation Across Pauses (2+ Seconds)**: Eliminated the transcript cutoff issue where pauses of 2 seconds or longer caused Deepgram Flux's Voice Activity Detection (VAD) to trigger an `EndOfTurn`, discarding earlier speech. Dictation now captures and accumulates 100% of speech between turning listening ON and turning listening OFF with the double-tap Right Alt gesture.
2. **Integrated On-Widget Square Stop Button (`■`)**: Replaced the desktop-level `Escape` key interception with an integrated square stop button directly embedded inside the floating pill overlay. Clicking the button immediately terminates active listening, audio capture, transcription, LLM processing, and text insertion midway, returning the daemon to an idle state while keeping it running in the background.

---

## 2. Problem Analysis & Root Cause

### Issue A: Audio / Transcript Cutoff During Pauses
- **Symptom**: When pausing speech for ~2 seconds or longer to think or breathe during dictation, all speech uttered before the pause was discarded, and only the post-pause speech was cleaned and pasted.
- **Root Cause**:
  - Deepgram Flux (`listen.v2` WebSocket) utilizes conversational end-of-turn detection. Silence exceeding ~1.5–2s automatically fires `TurnInfo(event="EndOfTurn")`.
  - In `stt/flux.py`, `self._transcript` was overwritten on each `EndOfTurn` event (`self._transcript = text`), replacing earlier turns instead of appending them.
  - Furthermore, when the user paused right before double-tapping Right Alt to stop recording, Deepgram had already finalized the turn. Calling `send_force_end_turn()` produced a server warning (`FORCE_END_TURN_NO_ACTIVE_TURN`), causing the system to wait for a 15-second timeout.

### Issue B: Ineffective `Escape` Key Abort & Conflict
- **Symptom**: Intercepting `Escape` via keyboard listeners did not reliably cancel tasks across different desktop environments and created potential key-stealing conflicts with local applications (e.g., closing modals, vim command mode).
- **Requirement**: Provide an intuitive, visually integrated square stop button (`■`) on the floating widget that is visible throughout the entire lifecycle (listening, transcribing, cleaning) and disappears with the widget before text is pasted.

---

## 3. Technical Implementation

### 3.1 Multi-Turn Speech Accumulation (`stt/flux.py`)
- **Cumulative Storage**: Replaced the single-turn string overwrite with thread-safe list accumulation (`self._turns: list[str]`).
- **`EndOfTurn` Event**: When Deepgram emits `EndOfTurn`, finalized non-empty text is appended to `self._turns`, `_current_partial` is reset, and the full cumulative transcript is delivered to the floating pill overlay via `self.on_partial`.
- **Live In-Flight Partials**: On `Update` and `StartOfTurn` events, live partial speech is combined with all prior committed turns (`" ".join([*self._turns, self._current_partial])`) so the user sees their entire dictation in real time.
- **Early Settling on Inactive Turn**: Handled Deepgram's `FORCE_END_TURN_NO_ACTIVE_TURN` warning by immediately unblocking `_final_settled`, eliminating unnecessary timeout delays when stopping after a pause.
- **Extended VAD Window**: Configured `eot_timeout_ms=3000` to allow natural breathing pauses without prematurely splitting utterances.

### 3.2 Local Streaming EOU Pattern Normalization (`stt/parakeet_stream.py`)
- Updated the End-of-Utterance regex pattern from matching only trailing tags to a global pattern (`EOU_PATTERN = re.compile(r"\s*\[EOU @ [^\]]+\]")`), ensuring multi-pause streams from `parakeet-cli` never leak internal EOU markers into partial or fallback transcripts.

### 3.3 Safe Audio Capture Abort (`audio/recorder.py`)
- Implemented `abort()` on the `Recorder` class to immediately stop `sounddevice.InputStream`, clear buffered audio frames, and reset recording state without writing unnecessary WAV files to disk.

### 3.4 Floating Overlay Stop Button Integration (`ui/overlay.py`)
- **Design & Styling**:
  - Added a compact square stop button (`.stop-btn`) styled with a subtle red accent and rounded corners (`min-width: 22px; min-height: 22px; border-radius: 6px;`).
  - Embedded a bold stop icon (`■`) that illuminates on hover.
  - Positioned seamlessly inside a horizontal header box alongside the status label.
  - Configured label text ellipsization (`Pango.EllipsizeMode.END`) so long partial transcripts never push the stop button outside the widget bounds.
- **Lifecycle & Visibility**:
  - The button appears immediately when recording starts (`_do_show("recording", "Listening...")`).
  - Stays visible throughout transcription and LLM cleaning (`_do_show("processing", ...)`).
  - Automatically hidden on transient error displays.
  - Disappears together with the entire pill widget when processing completes (`hide()`) or upon cancellation.
- **Click Handling**: Connected the `clicked` signal to `self.on_cancel()`, which schedules cancellation on a background daemon thread without blocking the GTK main loop.

### 3.5 Session Tracking & Pipeline Cancellation (`app.py`)
- **Generational Session ID (`_session_id`)**: An incrementing counter invalidates in-flight callbacks from older or cancelled operations.
- **Immediate Cancellation (`cancel()`)**:
  - Atomically sets `_cancel_token` and increments `_session_id`.
  - Stops the microphone stream (`MicrophoneStream.stop()` or `Recorder.abort()`).
  - Aborts the active STT session (`_stream_session.abort()`).
  - Suppresses clipboard operations (`insert_text`) and notification sounds.
  - Hides the overlay widget and resets the system tray icon to idle.
- **Reverted `Escape` Interception**: Completely removed keyboard interception for the `Escape` key in `pynput.keyboard.Listener`, ensuring standard desktop keystroke propagation is 100% unaffected.

### 3.6 Strict Geometry Locking & Waveform Scaling (`ui/overlay.py`)

- **Fixed Size Constraint Enforcement**: Configured `self.win.set_size_request(WIDTH, HEIGHT)`, `header.set_size_request(WIDTH - 32, 24)`, and `self.label.set_max_width_chars(25)` with `self.label.set_size_request(230, -1)`. This prevents GTK from expanding the window based on the label's natural text width, locking the pill dimensions permanently to 300x78.
- **Drift Prevention**: Automatically calls `_place_above_taskbar()` upon every `_do_show()` event, ensuring the widget is always centered horizontally across the primary monitor workarea.
- **Non-Linear Waveform Scaling**: Implemented a power curve (`v ** 0.75`) for audio amplitude levels in `_on_draw()`, ensuring waveforms remain visually tall, active, and well-proportioned during quiet-to-moderate speech instead of appearing as flat dots.
- **Clean Live Transcript Formatting**: Refined live transcript text formatting (`Listening: ...[words]`) to eliminate redundant leading ellipses.

---

## 4. Verification & Testing

| Test Scenario | Procedure | Expected Result | Outcome |
| --- | --- | --- | --- |
| **Multi-Turn Pause Handling** | Speak sentence, pause for 3–4 seconds, speak second sentence, double-tap Right Alt. | Entire combined transcript from both sentences is cleaned and pasted. | **PASS** |
| **Stop During Listening** | Double-tap Right Alt to begin listening, then click the `■` stop button on the widget. | Recording terminates immediately, overlay disappears, mic stream closes, daemon stays idle. | **PASS** |
| **Stop During Cleaning** | Speak sentence, double-tap Right Alt to stop, click `■` button during "Cleaning...". | LLM request is dropped, overlay hides, no text is pasted to the active window. | **PASS** |
| **Overlay Layout & Ellipsization** | Speak a long utterance exceeding widget width. | Text ellipsizes gracefully with `...`, stop button remains anchored and fully clickable. | **PASS** |
| **Fixed Geometry Stability** | Stream continuous text of 100+ characters across all states. | Widget dimensions stay exactly 300x78; no rightward expansion or waveform flattening. | **PASS** |
| **Passive Keystroke Isolation** | Press `Escape` while AutoType is idle or active. | AutoType ignores `Escape`, preserving default behavior in terminal/editors (e.g. Vim). | **PASS** |

---

## 5. Summary of Modified Files

- `stt/flux.py`: Implemented multi-turn list accumulation, live partial aggregation, `eot_timeout_ms=3000`, and `FORCE_END_TURN_NO_ACTIVE_TURN` warning handling.
- `stt/parakeet_stream.py`: Updated EOU pattern replacement to strip intermediate pause markers across multi-turn streams.
- `audio/recorder.py`: Added non-destructive `abort()` method for batch recording streams.
- `ui/overlay.py`: Designed and embedded square stop button (`■`), locked widget dimensions to 300x78, prevented rightward drift, and optimized waveform scaling.
- `app.py`: Integrated `Overlay(on_cancel=...)`, implemented thread-safe `cancel()` with session generation tracking, removed `Escape` key listener, and added cancellation guards across pipeline stages.
- `README.md`: Documented continuous multi-turn pause handling, floating widget UI consistency, and the new on-widget square stop button.
