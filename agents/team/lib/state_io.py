"""Atomic JSON storage shared by task, delivery and communication controllers.

Callers own directory creation, locking and schema validation. Replacement and
immutable publication are separate operations; both publish complete UTF-8 files
with private permissions and clean up temporary files after failures.
"""
import json
import os
from pathlib import Path
import tempfile


def _commit(path, value, *, replace, indent, newline, sync_directory, prefix):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=prefix, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=indent)
            if newline:
                stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            # A competing publisher must never overwrite the original receipt.
            os.link(temporary, path)
        if sync_directory:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def write_json(path, value, *, indent=2, newline=True, sync_directory=False,
               prefix='.pending-'):
    """Replace a state file atomically, using a unique temporary file per writer."""
    _commit(path, value, replace=True, indent=indent, newline=newline,
            sync_directory=sync_directory, prefix=prefix)


def publish_json(path, value):
    """Publish an immutable receipt; an existing destination raises FileExistsError."""
    _commit(path, value, replace=False, indent=2, newline=True,
            sync_directory=False, prefix='.pending-')
