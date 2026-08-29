#!/usr/bin/env python3
"""Serialize Patpat lock-file acquisition, release, and recovery."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Type


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _is_reparse_point(metadata: os.stat_result) -> bool:
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(flag and getattr(metadata, "st_file_attributes", 0) & flag)


def bounded_file_binding(
    path: Path,
    *,
    max_bytes: int,
    error_type: Type[Exception],
    label: str,
) -> dict[str, Any]:
    """Hash one bounded stable regular file through a held descriptor."""
    if max_bytes < 1:
        raise error_type("evidence byte limit must be positive")
    try:
        canonical = path.resolve(strict=True)
        before_path = path.lstat()
    except OSError as error:
        raise error_type(f"could not inspect {label}: {error}") from error
    if not path.is_absolute() or path != canonical:
        raise error_type(
            f"{label} must be an existing absolute canonical regular file without symlinks"
        )
    if (
        not stat.S_ISREG(before_path.st_mode)
        or before_path.st_nlink != 1
        or _is_reparse_point(before_path)
    ):
        raise error_type(f"{label} must be a unique regular file without symlinks")

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise error_type(f"could not read {label}: {error}") from error
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or _is_reparse_point(before)
        ):
            raise error_type(f"{label} must be a unique regular file without symlinks")
        if (before_path.st_dev, before_path.st_ino) != (before.st_dev, before.st_ino):
            raise error_type(f"{label} changed while it was read")
        if before.st_size > max_bytes:
            raise error_type(f"{label} exceeds the {max_bytes}-byte limit")
        digest = hashlib.sha256()
        size = 0
        while size <= max_bytes:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - size))
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        if size > max_bytes:
            raise error_type(f"{label} exceeds the {max_bytes}-byte limit")
        after = os.fstat(descriptor)
    except OSError as error:
        raise error_type(f"could not read {label}: {error}") from error
    finally:
        os.close(descriptor)

    try:
        after_path = path.lstat()
        after_canonical = path.resolve(strict=True)
    except OSError as error:
        raise error_type(f"{label} changed while it was read") from error
    if (
        _file_identity(before) != _file_identity(after)
        or size != after.st_size
        or path != after_canonical
        or not stat.S_ISREG(after_path.st_mode)
        or after_path.st_nlink != 1
        or _is_reparse_point(after_path)
        or (after_path.st_dev, after_path.st_ino) != (after.st_dev, after.st_ino)
    ):
        raise error_type(f"{label} changed while it was read")
    return {"path": str(path), "sha256": digest.hexdigest(), "size": size}


def process_is_alive(pid: int) -> bool:
    """Return false only when the current host proves that a process is absent."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        open_process.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL
        handle = open_process(process_query_limited_information, False, pid)
        if handle:
            close_handle(handle)
            return True
        return ctypes.get_last_error() != 87
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock_record(path: Path, max_bytes: int) -> tuple[dict[str, Any] | None, tuple[int, int] | None]:
    """Read bounded JSON from a unique regular lock file without following symlinks."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None, None
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > max_bytes
        ):
            return None, None
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > max_bytes:
            return None, None
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, dict):
            return None, None
        return value, (metadata.st_dev, metadata.st_ino)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, None
    finally:
        os.close(descriptor)


def path_has_identity(path: Path, identity: tuple[int, int] | None) -> bool:
    if identity is None:
        return False
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return not stat.S_ISLNK(metadata.st_mode) and (metadata.st_dev, metadata.st_ino) == identity


@contextmanager
def path_guard(
    directory: Path,
    error_type: Type[Exception] = RuntimeError,
    timeout_seconds: float = 5.0,
) -> Iterator[None]:
    """Hold a process-scoped OS lock while changing `.lock` in a store directory."""
    if timeout_seconds <= 0:
        raise error_type("lock guard timeout must be positive")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".lock.guard"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as error:
        raise error_type(f"lock guard is not a safe regular file: {path}") from error
    acquired = False
    try:
        try:
            descriptor_stat = os.fstat(descriptor)
            path_stat = path.lstat()
            if (
                not stat.S_ISREG(descriptor_stat.st_mode)
                or descriptor_stat.st_nlink != 1
                or (descriptor_stat.st_dev, descriptor_stat.st_ino)
                != (path_stat.st_dev, path_stat.st_ino)
            ):
                raise error_type(f"lock guard is not a unique regular file: {path}")
            deadline = time.monotonic() + timeout_seconds
            while True:
                try:
                    if os.name == "nt":
                        import msvcrt

                        if descriptor_stat.st_size == 0:
                            os.write(descriptor, b"0")
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, OSError) as error:
                    if time.monotonic() >= deadline:
                        raise error_type(
                            f"lock guard acquisition timed out after {timeout_seconds:.3f}s: {path}"
                        ) from error
                    time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            current_stat = path.lstat()
            if (
                (descriptor_stat.st_dev, descriptor_stat.st_ino)
                != (current_stat.st_dev, current_stat.st_ino)
            ):
                raise error_type(f"lock guard identity changed during acquisition: {path}")
        except OSError as error:
            raise error_type(f"lock guard could not be acquired safely: {path}") from error
        acquired = True
        yield
    finally:
        if acquired:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)
