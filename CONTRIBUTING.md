# Contributing to AutoType

Thank you for your interest in improving AutoType!

## Development Guidelines

1. **Prerequisites**: Python 3.10+, GTK3 (`gir1.2-gtk-3.0`, `python3-gi`), and PortAudio (`libportaudio2`) on an X11 desktop environment.
2. **Environment Setup**: See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for full setup instructions.
3. **Tests**: Run `pytest` before submitting changes. Ensure all test cases pass.
4. **Code Style**:
   - Follow PEP 8 standards.
   - Use Conventional Commits (`feat:`, `fix:`, `docs:`, `build:`, `ci:`, `chore:`).
   - Keep system tool invocations to a minimum by leveraging native Python libraries (`python-xlib`, `Gtk.Clipboard`).
5. **Pull Requests**:
   - Branch from `main`.
   - Provide a concise summary of changes and reference relevant issues.
