"""Virtual File System abstraction for SQLite database files."""

import os
import threading
import ctypes
from .constants import (
    LOCK_NONE, LOCK_SHARED, LOCK_RESERVED, LOCK_PENDING, LOCK_EXCLUSIVE,
    SQLITE_OPEN_READONLY, SQLITE_OPEN_READWRITE, SQLITE_OPEN_CREATE,
    SYNC_NORMAL, SYNC_FULL, SYNC_DATAONLY, HEADER_SIZE,
)
from .errors import DatabaseError, CantOpenError, ReadOnlyError, BusyError


class FileHandle:
    """Opaque wrapper around a file descriptor or memory buffer."""

    def __init__(self, fd: int, path: str):
        self.fd = fd
        self.path = path
        self.lock_state = LOCK_NONE
        self.is_memory = False
        self.mem_buffer: bytearray | None = None


class VFS:
    """Abstract Virtual File System interface.

    Subclasses must implement open, close, read, write, truncate,
    sync, file_size, lock, unlock, check_reserved_lock, sector_size,
    delete, and file_exists.
    """

    def open(self, path: str, flags: int) -> FileHandle:
        raise NotImplementedError

    def close(self, handle: FileHandle):
        raise NotImplementedError

    def read(self, handle: FileHandle, offset: int, amount: int) -> bytes:
        raise NotImplementedError

    def write(self, handle: FileHandle, offset: int, data: bytes):
        raise NotImplementedError

    def truncate(self, handle: FileHandle, size: int):
        raise NotImplementedError

    def sync(self, handle: FileHandle, flags: int = SYNC_FULL):
        raise NotImplementedError

    def file_size(self, handle: FileHandle) -> int:
        raise NotImplementedError

    def lock(self, handle: FileHandle, lock_type: int) -> bool:
        raise NotImplementedError

    def unlock(self, handle: FileHandle, lock_type: int):
        raise NotImplementedError

    def check_reserved_lock(self, handle: FileHandle) -> bool:
        raise NotImplementedError

    def sector_size(self, handle: FileHandle) -> int:
        raise NotImplementedError

    def delete(self, path: str):
        raise NotImplementedError

    def file_exists(self, path: str) -> bool:
        raise NotImplementedError


class OSVFS(VFS):
    """Real filesystem VFS using OS system calls.

    On Windows, uses LockFileEx/UnlockFileEx for byte-range locking
    and os.lseek+os.read/write for positional I/O.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._has_ctypes = False
        self._kernel32 = None
        self._init_windows_locking()

    def _init_windows_locking(self):
        try:
            import ctypes
            self._kernel32 = ctypes.windll.kernel32
            self._has_ctypes = True
        except (ImportError, AttributeError):
            self._has_ctypes = False

    def _to_handle(self, fd: int):
        import msvcrt
        return msvcrt.get_osfhandle(fd)

    def _make_overlapped(self, offset):
        class OVERLAPPED(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_ulong),
                ("InternalHigh", ctypes.c_ulong),
                ("Offset", ctypes.c_ulong),
                ("OffsetHigh", ctypes.c_ulong),
                ("hEvent", ctypes.c_void_p),
            ]
        o = OVERLAPPED()
        o.Offset = offset & 0xFFFFFFFF
        o.OffsetHigh = (offset >> 32) & 0xFFFFFFFF
        o.hEvent = None
        return o

    def _win_lock_byte(self, handle, start, length, exclusive):
        if not self._has_ctypes:
            return False
        overlapped = self._make_overlapped(start)
        flags = 0 if not exclusive else 2
        result = self._kernel32.LockFileEx(
            handle, flags, 0, length, 0, ctypes.byref(overlapped)
        )
        return result != 0

    def _win_unlock_byte(self, handle, start, length):
        if not self._has_ctypes:
            return
        overlapped = self._make_overlapped(start)
        self._kernel32.UnlockFileEx(
            handle, 0, length, 0, ctypes.byref(overlapped)
        )

    def _os_open_flags(self, flags: int):
        os_flags = os.O_BINARY | os.O_NOINHERIT
        if flags & SQLITE_OPEN_READONLY:
            os_flags |= os.O_RDONLY
        if flags & SQLITE_OPEN_READWRITE:
            os_flags |= os.O_RDWR
        if flags & SQLITE_OPEN_CREATE:
            os_flags |= os.O_CREAT
        return os_flags

    def open(self, path: str, flags: int) -> FileHandle:
        os_flags = self._os_open_flags(flags)
        if flags & SQLITE_OPEN_CREATE:
            os_flags |= os.O_CREAT
        try:
            fd = os.open(path, os_flags)
        except PermissionError:
            raise CantOpenError(f"Cannot open {path}: permission denied")
        except FileNotFoundError:
            raise CantOpenError(f"Cannot open {path}: file not found")
        except OSError as e:
            raise CantOpenError(f"Cannot open {path}: {e}")
        return FileHandle(fd, path)

    def close(self, handle: FileHandle):
        if handle.fd >= 0:
            try:
                os.close(handle.fd)
            except OSError:
                pass
            handle.fd = -1

    def read(self, handle: FileHandle, offset: int, amount: int) -> bytes:
        if handle.is_memory:
            buf = handle.mem_buffer
            if buf is None:
                return b'\x00' * amount
            available = max(0, len(buf) - offset)
            if available >= amount:
                return bytes(buf[offset:offset + amount])
            result = bytearray(amount)
            if available > 0:
                result[:available] = buf[offset:offset + available]
            return bytes(result)
        with self._lock:
            os.lseek(handle.fd, offset, os.SEEK_SET)
            data = os.read(handle.fd, amount)
            if len(data) < amount:
                data += b'\x00' * (amount - len(data))
            return data

    def write(self, handle: FileHandle, offset: int, data: bytes):
        if handle.is_memory:
            buf = handle.mem_buffer
            if buf is None:
                return
            end = offset + len(data)
            if end > len(buf):
                buf.extend(b'\x00' * (end - len(buf)))
            buf[offset:end] = data
            return
        with self._lock:
            os.lseek(handle.fd, offset, os.SEEK_SET)
            os.write(handle.fd, data)

    def truncate(self, handle: FileHandle, size: int):
        if handle.is_memory:
            buf = handle.mem_buffer
            if size < len(buf):
                del buf[size:]
            elif size > len(buf):
                buf.extend(b'\x00' * (size - len(buf)))
            return
        with self._lock:
            os.ftruncate(handle.fd, size)

    def sync(self, handle: FileHandle, flags: int = SYNC_FULL):
        if handle.fd < 0 or handle.is_memory:
            return
        try:
            os.fsync(handle.fd)
        except OSError:
            pass

    def file_size(self, handle: FileHandle) -> int:
        if handle.is_memory:
            return len(handle.mem_buffer)
        with self._lock:
            old = os.lseek(handle.fd, 0, os.SEEK_CUR)
            size = os.lseek(handle.fd, 0, os.SEEK_END)
            os.lseek(handle.fd, old, os.SEEK_SET)
            return size

    def lock(self, handle: FileHandle, lock_type: int) -> bool:
        if handle.is_memory:
            handle.lock_state = lock_type
            return True
        if lock_type <= handle.lock_state:
            return True
        if lock_type == LOCK_SHARED:
            ok = self._win_lock_byte(self._to_handle(handle.fd), 0, 1, False)
            if not ok:
                return False
            handle.lock_state = LOCK_SHARED
            return True
        if lock_type == LOCK_RESERVED:
            ok = self._win_lock_byte(self._to_handle(handle.fd), 1, 1, True)
            if not ok:
                return False
            handle.lock_state = LOCK_RESERVED
            return True
        if lock_type == LOCK_PENDING:
            ok = self._win_lock_byte(self._to_handle(handle.fd), 2, 1, True)
            if not ok:
                return False
            handle.lock_state = LOCK_PENDING
            return True
        if lock_type == LOCK_EXCLUSIVE:
            ok = self._win_lock_byte(self._to_handle(handle.fd), 3, 1, True)
            if not ok:
                return False
            handle.lock_state = LOCK_EXCLUSIVE
            return True
        return False

    def unlock(self, handle: FileHandle, lock_type: int):
        if handle.is_memory:
            handle.lock_state = lock_type
            return
        current = handle.lock_state
        if current >= LOCK_EXCLUSIVE and lock_type < LOCK_EXCLUSIVE:
            self._win_unlock_byte(self._to_handle(handle.fd), 3, 1)
        if current >= LOCK_PENDING and lock_type < LOCK_PENDING:
            self._win_unlock_byte(self._to_handle(handle.fd), 2, 1)
        if current >= LOCK_RESERVED and lock_type < LOCK_RESERVED:
            self._win_unlock_byte(self._to_handle(handle.fd), 1, 1)
        if current >= LOCK_SHARED and lock_type < LOCK_SHARED:
            self._win_unlock_byte(self._to_handle(handle.fd), 0, 1)
        handle.lock_state = lock_type

    def check_reserved_lock(self, handle: FileHandle) -> bool:
        if handle.is_memory:
            return False
        try:
            ok = self._win_lock_byte(self._to_handle(handle.fd), 1, 1, True)
            if ok:
                self._win_unlock_byte(self._to_handle(handle.fd), 1, 1)
                return False
            return True
        except Exception:
            return True

    def sector_size(self, handle: FileHandle) -> int:
        return 512

    def delete(self, path: str):
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            raise DatabaseError(f"Cannot delete {path}")

    def file_exists(self, path: str) -> bool:
        return os.path.exists(path)


class MemoryVFS(VFS):
    """In-memory VFS for :memory: databases.

    All data is stored in bytearray buffers keyed by path name.
    Buffers start empty and grow as data is written.
    """

    def __init__(self):
        self.buffers: dict[str, bytearray] = {}
        self._handles: dict[str, FileHandle] = {}

    def open(self, path: str, flags: int) -> FileHandle:
        if path not in self.buffers:
            self.buffers[path] = bytearray()
        handle = FileHandle(-1, path)
        handle.is_memory = True
        handle.mem_buffer = self.buffers[path]
        self._handles[path] = handle
        return handle

    def close(self, handle: FileHandle):
        if handle.path in self._handles:
            del self._handles[handle.path]
        handle.mem_buffer = None

    def read(self, handle: FileHandle, offset: int, amount: int) -> bytes:
        buf = handle.mem_buffer
        if buf is None:
            return b'\x00' * amount
        available = max(0, len(buf) - offset)
        if available >= amount:
            return bytes(buf[offset:offset + amount])
        result = bytearray(amount)
        if available > 0:
            result[:available] = buf[offset:offset + available]
        return bytes(result)

    def write(self, handle: FileHandle, offset: int, data: bytes):
        buf = handle.mem_buffer
        if buf is None:
            return
        end = offset + len(data)
        if end > len(buf):
            buf.extend(b'\x00' * (end - len(buf)))
        buf[offset:end] = data

    def truncate(self, handle: FileHandle, size: int):
        buf = handle.mem_buffer
        if buf is None:
            return
        if size < len(buf):
            del buf[size:]
        elif size > len(buf):
            buf.extend(b'\x00' * (size - len(buf)))

    def sync(self, handle: FileHandle, flags: int = SYNC_FULL):
        pass

    def file_size(self, handle: FileHandle) -> int:
        if handle.mem_buffer is None:
            return 0
        return len(handle.mem_buffer)

    def lock(self, handle: FileHandle, lock_type: int) -> bool:
        handle.lock_state = lock_type
        return True

    def unlock(self, handle: FileHandle, lock_type: int):
        handle.lock_state = lock_type

    def check_reserved_lock(self, handle: FileHandle) -> bool:
        return False

    def sector_size(self, handle: FileHandle) -> int:
        return 512

    def delete(self, path: str):
        if path in self.buffers:
            del self.buffers[path]

    def file_exists(self, path: str) -> bool:
        return path in self.buffers
