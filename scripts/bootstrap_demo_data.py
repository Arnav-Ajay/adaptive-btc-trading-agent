"""Copy the bundled parquet demo lake into the active data_lake path."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "demo_assets" / "data_lake"
DEFAULT_TARGET = REPO_ROOT / "data_lake"


def _clear_directory_contents(path: Path) -> None:
    """Remove all children of a directory without removing the directory itself."""
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def main(argv: list[str] | None = None) -> int:
    """Copy the bundled demo lake into place for local or Docker demo mode."""
    parser = argparse.ArgumentParser(description="Bootstrap bundled parquet demo data into data_lake/")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Bundled demo data source directory")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="Destination data lake directory")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing target directory")
    args = parser.parse_args(argv)

    source = args.source.resolve()
    target = args.target.resolve()
    if not source.exists():
        raise FileNotFoundError(f"demo_data_source_missing:{source}")

    if target.exists():
        if not args.force:
            raise FileExistsError(f"demo_data_target_exists:{target}")
        _clear_directory_contents(target)
    else:
        target.mkdir(parents=True, exist_ok=True)

    for child in source.iterdir():
        destination = target / child.name
        if child.is_dir():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)
    print(f"Bootstrapped demo data: {source} -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
