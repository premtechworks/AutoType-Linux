Name:           autotype
Version:        1.0.0
Release:        1%{?dist}
Summary:        Voice-typing daemon for Linux Mint XFCE on X11

License:        MIT
URL:            https://github.com/premtechworks/AutoType-Linux
Source0:        autotype-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-pip

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
%py3_build

%install
%py3_install
install -D -m 0644 io.github.premtechworks.AutoType.desktop %{buildroot}%{_datadir}/applications/io.github.premtechworks.AutoType.desktop
install -D -m 0644 io.github.premtechworks.AutoType.metainfo.xml %{buildroot}%{_metainfodir}/io.github.premtechworks.AutoType.metainfo.xml
install -D -m 0644 icons/hicolor/scalable/apps/io.github.premtechworks.AutoType.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.premtechworks.AutoType.svg

%files
%license LICENSE
%doc README.md
%{_bindir}/autotype
%{python3_sitelib}/autotype/
%{python3_sitelib}/autotype-%{version}-py%{python3_version}.egg-info/
%{_datadir}/applications/io.github.premtechworks.AutoType.desktop
%{_metainfodir}/io.github.premtechworks.AutoType.metainfo.xml
%{_datadir}/icons/hicolor/scalable/apps/io.github.premtechworks.AutoType.svg

%changelog
* Tue Oct 13 2026 Prem kumar Gara <premtechworks@gmail.com> - 1.0.0-1
- Initial package release
