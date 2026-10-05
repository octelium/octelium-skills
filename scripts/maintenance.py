from __future__ import annotations

import os
import tempfile
from pathlib import Path


def replace_files(contents: dict[Path, bytes]) -> None:
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    replaced: list[Path] = []
    rollback_failed = False
    try:
        for dest, content in contents.items():
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink():
                raise OSError(f"refusing to replace symlink: {dest}")
            original = dest.read_bytes() if dest.exists() else None
            mode = dest.stat().st_mode & 0o777 if original is not None else 0o644
            for data, paths in ((content, staged), (original, backups)):
                if data is None:
                    paths[dest] = None
                    continue
                with tempfile.NamedTemporaryFile(dir=dest.parent, prefix=".octelium-stage-", delete=False) as f:
                    paths[dest] = Path(f.name)
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
                paths[dest].chmod(mode)
        for dest, path in staged.items():
            os.replace(path, dest)
            replaced.append(dest)
    except BaseException as failure:
        failures = []
        for dest in reversed(replaced):
            backup = backups[dest]
            try:
                if backup is None:
                    dest.unlink()
                else:
                    os.replace(backup, dest)
            except OSError:
                failures.append(f"{dest} (backup: {backup})")
        if failures:
            rollback_failed = True
            raise OSError(f"update failed; restore manually from retained backups: {', '.join(failures)}") from failure
        raise
    finally:
        for path in [*staged.values(), *([] if rollback_failed else backups.values())]:
            if path is not None:
                path.unlink(missing_ok=True)
