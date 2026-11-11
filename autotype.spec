Name:           autotype
Version:        1.1.0
Release:        1%{?dist}
Summary:        Voice-typing daemon for Linux Mint XFCE on X11

License:        MIT
URL:            https://github.com/premtechworks/AutoType-Linux
Source0:        autotype-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel

Requires:       python3 >= 3.10
Requires:       python3-gobject
Requires:       gtk3
Requires:       portaudio
Recommends:     xdotool
Recommends:     libnotify
Suggests:       pulseaudio-utils

%description
AutoType is an open-source voice typing daemon and assistant designed for Linux
Mint XFCE and other X11 desktop environments. It features double-tap Right Alt
activation, cloud speech-to-text (Deepgram, OpenAI Whisper, Groq, NVIDIA NIM)
and offline STT (Parakeet), LLM text cleaning, and clipboard preservation.

%prep
%autosetup

%build
# Pure Python: the modules are installed as-is, nothing to compile.

%install
mkdir -p %{buildroot}%{python3_sitelib}
cp -a autotype audio context desktop llm stt ui utils %{buildroot}%{python3_sitelib}/
install -m 0644 app.py config.py settings_gui.py %{buildroot}%{python3_sitelib}/
find %{buildroot}%{python3_sitelib} -type d -name __pycache__ -prune -exec rm -rf {} +
find %{buildroot}%{python3_sitelib} -type f -name '*.pyc' -delete

mkdir -p %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/autotype <<'PYEOF'
#!/usr/bin/env python3
import sys

from autotype.cli import main

if __name__ == "__main__":
    sys.exit(main())
PYEOF
chmod 0755 %{buildroot}%{_bindir}/autotype

install -D -m 0644 io.github.premtechworks.AutoType.desktop %{buildroot}%{_datadir}/applications/io.github.premtechworks.AutoType.desktop
install -D -m 0644 io.github.premtechworks.AutoType.metainfo.xml %{buildroot}%{_metainfodir}/io.github.premtechworks.AutoType.metainfo.xml
install -D -m 0644 icons/hicolor/scalable/apps/io.github.premtechworks.AutoType.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.premtechworks.AutoType.svg

%files
%license LICENSE
%doc README.md
%{_bindir}/autotype
%{python3_sitelib}/autotype/
%{python3_sitelib}/audio/
%{python3_sitelib}/context/
%{python3_sitelib}/desktop/
%{python3_sitelib}/llm/
%{python3_sitelib}/stt/
%{python3_sitelib}/ui/
%{python3_sitelib}/utils/
%{python3_sitelib}/app.py
%{python3_sitelib}/config.py
%{python3_sitelib}/settings_gui.py
%{_datadir}/applications/io.github.premtechworks.AutoType.desktop
%{_metainfodir}/io.github.premtechworks.AutoType.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/io.github.premtechworks.AutoType.svg

%changelog
* Wed Nov 11 2026 Prem kumar Gara <premtechworks@gmail.com> - 1.1.0-1
- Add keep_in_clipboard option and the autotype launch subcommand

* Tue Oct 13 2026 Prem kumar Gara <premtechworks@gmail.com> - 1.0.0-1
- Initial package release
