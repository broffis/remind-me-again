"""Build a versioned, self-contained ZIP and SHA-256 checksum for GitHub Releases."""

import argparse
import hashlib
from pathlib import Path
import re
import sys
import zipfile

from install import PAYLOAD


def build(version, output_directory):
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Version must use vMAJOR.MINOR.PATCH.")
    root = Path(__file__).resolve().parent
    filenames = ["install.py", "README.md", "LICENSE"]
    filenames.extend(f"session-summary/{filename}" for filename in PAYLOAD)
    for filename in filenames:
        if not (root / filename).is_file():
            raise ValueError(f"Release is incomplete: missing {filename}")
    output_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / f"session-summary-skill-{version}.zip"
    checksum = destination.with_suffix(".zip.sha256")
    if destination.exists() or checksum.exists():
        raise ValueError("Release output already exists; choose a clean output directory.")
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in filenames:
            archive.write(root / filename, f"session-summary-skill/{filename}")
    checksum.write_text(
        f"{hashlib.sha256(destination.read_bytes()).hexdigest()}  {destination.name}\n",
        encoding="utf-8",
    )
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    try:
        print(build(args.version, args.output_dir))
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        parser.exit(1, f"Cannot build release: {error}\n")


if __name__ == "__main__":
    main()
