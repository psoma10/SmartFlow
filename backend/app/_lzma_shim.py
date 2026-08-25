"""Guards against Python builds missing the optional `_lzma` C extension.

Some pyenv-built interpreters skip liblzma at compile time (no system dev
headers). torchvision imports the stdlib `lzma` module unconditionally at
import time, even though SmartFlow never touches .xz archives. Rather than
requiring a full Python rebuild just to satisfy that unused import, install a
harmless stub so the import succeeds; any actual use of the stub raises
loudly instead of silently doing the wrong thing.
"""
from __future__ import annotations

import sys
import types


def ensure_lzma_importable() -> None:
    try:
        import lzma  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    stub = types.ModuleType("lzma")

    class LZMAError(Exception):
        pass

    def _unsupported(*_args, **_kwargs):
        raise RuntimeError(
            "lzma support unavailable in this Python build (missing liblzma); "
            "SmartFlow does not use .xz archives, this stub only exists to "
            "satisfy torchvision's unconditional import"
        )

    stub.LZMAError = LZMAError
    stub.LZMAFile = _unsupported
    stub.LZMACompressor = _unsupported
    stub.LZMADecompressor = _unsupported
    stub.open = _unsupported
    stub.compress = _unsupported
    stub.decompress = _unsupported
    stub.FORMAT_XZ = 1
    stub.FORMAT_ALONE = 2
    stub.FORMAT_RAW = 3
    stub.CHECK_NONE = 0
    stub.CHECK_CRC32 = 1
    stub.CHECK_CRC64 = 4
    stub.CHECK_SHA256 = 10
    stub.PRESET_DEFAULT = 6
    sys.modules["lzma"] = stub
