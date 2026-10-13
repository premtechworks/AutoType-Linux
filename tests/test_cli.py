import io
import sys
import pytest
from autotype import cli
from autotype.__version__ import __version__


def test_cli_no_args_shows_help(capsys):
    ret = cli.main([])
    assert ret == 0
    captured = capsys.readouterr()
    assert "usage: autotype" in captured.out.lower() or "subcommands" in captured.out.lower()


def test_cli_version_flag(capsys):
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_cli_version_subcommand(capsys):
    ret = cli.main(["version"])
    assert ret == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == __version__


def test_cli_download_model_no_args(capsys):
    ret = cli.main(["download-model"])
    assert ret == 2
    captured = capsys.readouterr()
    assert "usage error" in captured.err.lower()


def test_cli_download_model_list(capsys):
    ret = cli.main(["download-model", "--list"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "parakeet-eou-120m" in captured.out
    assert "parakeet-cli" in captured.out
    assert "transcribe-cli" in captured.out
    assert "unverified" in captured.out


def test_cli_download_model_install_unknown(capsys):
    ret = cli.main(["download-model", "--install", "unknown-model-xyz"])
    assert ret == 2
    captured = capsys.readouterr()
    assert "Unknown model ID" in captured.err


def test_cli_download_model_install_unverified(capsys):
    ret = cli.main(["download-model", "--install", "transcribe-cli"])
    assert ret == 2
    captured = capsys.readouterr()
    assert "cannot be installed" in captured.err


def test_cli_download_model_install_success(capsys, monkeypatch, tmp_path):
    fake_path = tmp_path / "installed_model.gguf"
    fake_path.write_bytes(b"data")

    monkeypatch.setattr(
        "autotype.downloader.download_item",
        lambda item, progress_callback=None, cancel_event=None: fake_path,
    )

    ret = cli.main(["download-model", "--install", "parakeet-eou-120m"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Successfully installed" in captured.out


def test_cli_download_model_install_checksum_mismatch(capsys, monkeypatch):
    from autotype.downloader import ChecksumMismatchError

    def fake_mismatch(*args, **kwargs):
        raise ChecksumMismatchError("checksum mismatch: bad digest")

    monkeypatch.setattr("autotype.downloader.download_item", fake_mismatch)

    ret = cli.main(["download-model", "--install", "parakeet-eou-120m"])
    assert ret == 3
    captured = capsys.readouterr()
    assert "checksum mismatch" in captured.err.lower()


def test_cli_download_model_install_failure(capsys, monkeypatch):
    from autotype.downloader import DownloaderError

    def fake_fail(*args, **kwargs):
        raise DownloaderError("network connection reset")

    monkeypatch.setattr("autotype.downloader.download_item", fake_fail)

    ret = cli.main(["download-model", "--install", "parakeet-eou-120m"])
    assert ret == 1
    captured = capsys.readouterr()
    assert "network connection reset" in captured.err.lower()


def test_cli_download_model_remove(capsys, monkeypatch):
    monkeypatch.setattr("autotype.manifest.is_item_installed", lambda item: True)
    monkeypatch.setattr("autotype.downloader.remove_item", lambda item: True)

    ret = cli.main(["download-model", "--remove", "parakeet-eou-120m"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Successfully removed" in captured.out


def test_cli_download_model_all_recommended(capsys, monkeypatch, tmp_path):
    fake_path = tmp_path / "fake"
    monkeypatch.setattr(
        "autotype.downloader.download_item",
        lambda item, progress_callback=None, cancel_event=None: fake_path,
    )

    ret = cli.main(["download-model", "--all-recommended"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "All recommended items successfully installed" in captured.out


def test_cli_doctor_command(capsys, monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    ret = cli.main(["doctor"])
    captured = capsys.readouterr()
    assert "Doctor" in captured.out
    assert "Summary:" in captured.out
    assert ret in (0, 1)


def test_cli_doctor_json_command(capsys, monkeypatch):
    import json
    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    ret = cli.main(["doctor", "--json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "version" in data
    assert "ok" in data
    assert "checks" in data
    assert ret in (0, 1)


def test_cli_daemon_debug_flag(monkeypatch):
    called = []

    def fake_run_daemon(debug: bool = False):
        called.append(debug)
        return 0

    monkeypatch.setattr(cli, "run_daemon", fake_run_daemon)
    cli.main(["daemon", "--debug"])
    assert called == [True]

