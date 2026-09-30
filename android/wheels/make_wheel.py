"""Package a cross-compiled pydantic-core as a wheel Chaquopy's pip will install.

Usage: make_wheel.py <sdist dir> <compiled .so> <output .whl path>

The wheel holds the sdist's Python files, the extension as `_pydantic_core.so` (Chaquopy loads
extensions by their plain `.so` name), and dist-info with the tag taken from the file name.
"""
from __future__ import annotations

import base64
import hashlib
import sys
import zipfile
from pathlib import Path


def _record_line(name: str, data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"{name},sha256={digest},{len(data)}"


def main(src: Path, so: Path, out: Path) -> None:
    name, version, py, abi, platform = out.stem.split("-")
    tag = f"{py}-{abi}-{platform}"
    dist_info = f"{name}-{version}.dist-info"

    files: dict[str, bytes] = {}
    package = src / "python" / "pydantic_core"
    for path in sorted(package.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            files[f"pydantic_core/{path.relative_to(package).as_posix()}"] = path.read_bytes()
    files["pydantic_core/_pydantic_core.so"] = so.read_bytes()
    files[f"{dist_info}/METADATA"] = (src / "PKG-INFO").read_bytes()
    files[f"{dist_info}/WHEEL"] = (
        f"Wheel-Version: 1.0\nGenerator: passbook make_wheel.py\nRoot-Is-Purelib: false\nTag: {tag}\n"
    ).encode()

    record = [_record_line(n, d) for n, d in files.items()] + [f"{dist_info}/RECORD,,"]
    files[f"{dist_info}/RECORD"] = ("\n".join(record) + "\n").encode()

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as whl:
        for n, d in files.items():
            whl.writestr(n, d)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
