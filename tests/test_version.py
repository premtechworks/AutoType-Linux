import autotype
from autotype.__version__ import __version__


def test_version_value():
    assert __version__ == "1.0.0"
    assert autotype.__version__ == "1.0.0"
