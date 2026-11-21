#!/usr/bin/env python3
"""Read-only EFS view: stream ntfsdecrypt output, never store decrypted files.

Uses the system ntfs-3g implementation for all cryptography. A root-only local
socket accepts the PFX password from a private terminal; it is held in memory.
"""
import errno
import getpass
import itertools
import json
import os
from pathlib import Path
import resource
import select
import socket
import stat
import subprocess
import sys
import threading

SOURCE = Path('/mnt/filebrowser/BitLocker')
MOUNT = Path('/mnt/filebrowser/BitLocker-Decrypted')
PFX = '/mnt/filebrowser/SSK/cloud-backup/onedrive/Documents/encryption_key_certs_for_linuxfour_backup.pfx'
DEVICE = '/dev/mapper/filebrowser-bitlocker'
RUNTIME = Path('/run/filebrowser-efs')
SOCKET = RUNTIME / 'unlock.sock'
FINGERPRINT = '6549B2CD28B2C0562ECFDD5A1A3B3E23A45C148C'
SAMPLE = '/linuxfour_backup/iso_backup/vlc-record-2020-04-13-15h06m25s-MOVI0033.avi-.avi'
WINDOW = 1024 * 1024
DECRYPTOR = '/usr/local/sbin/filebrowser-ntfsdecrypt'


def require_readonly():
    """Fail closed unless the raw source device is physically write-protected."""
    if subprocess.check_output(['blockdev', '--getro', DEVICE], text=True).strip() != '1':
        raise OSError(errno.EROFS, 'BitLocker mapping must be read-only')


def source_path(path):
    """Reject traversal and symbolic links before accessing the source tree."""
    parts = Path(path.lstrip('/')).parts
    if '..' in parts:
        raise OSError(errno.EACCES, 'Path outside source')
    full = SOURCE.joinpath(*parts)
    if not full.resolve().is_relative_to(SOURCE.resolve()):
        raise OSError(errno.EACCES, 'Path outside source')
    for index in range(1, len(parts) + 1):
        if SOURCE.joinpath(*parts[:index]).is_symlink():
            raise OSError(errno.EACCES, 'Symbolic links are not exposed')
    return full


class DecryptedStream:
    """Bounded-memory sequential reader with restart support for backward seeks."""
    def __init__(self, path, size, password):
        self.path, self.size, self.password = path, size, password
        self.process = None
        self.position = 0
        self.window = b''
        self.lock = threading.Lock()

    def start(self):
        require_readonly()
        self.process = subprocess.Popen(
            [DECRYPTOR, '-f', '-q', '-k', PFX, DEVICE, self.path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            start_new_session=True, bufsize=0)
        # With no controlling tty, glibc getpass reads from this private pipe.
        # The password is never in argv, the environment, a file, or a log.
        self.process.stdin.write(self.password + b'\n')
        self.process.stdin.close()
        self.position, self.window = 0, b''

    def stop(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()
            self.process.stdout.close()
            self.process = None

    def pull(self, size):
        readable, _, _ = select.select([self.process.stdout], [], [], 60)
        if not readable:
            self.stop()
            raise OSError(errno.ETIMEDOUT, 'EFS reader timed out')
        data = self.process.stdout.read(min(size, WINDOW))
        if not data:
            self.stop()
            raise OSError(errno.EIO, 'EFS decryption failed or ended early')
        self.position += len(data)
        self.window = (self.window + data)[-WINDOW:]
        return data

    def read(self, size, offset):
        with self.lock:
            if offset < 0:
                raise OSError(errno.EINVAL, 'Negative offset')
            size = min(size, max(0, self.size - offset))
            if not size:
                return b''
            if self.process is None:
                self.start()
            if offset < self.position - len(self.window):
                self.stop()
                self.start()
            while self.position < offset:
                self.pull(offset - self.position)
            result = bytearray()
            if offset < self.position:
                start = offset - (self.position - len(self.window))
                result.extend(self.window[start:start + size])
            while len(result) < size:
                result.extend(self.pull(size - len(result)))
            return bytes(result)

    def close(self):
        with self.lock:
            self.stop()
            self.password = None
            self.window = b''


class UnlockState:
    """Hold a verified password and serve root-only unlock/status requests."""
    def __init__(self):
        self.password = None
        self.lock = threading.Lock()
        self.active_streams = 0
        self.phase = 'locked'

    def verify(self, password):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.serialization import pkcs12
        self.phase = 'checking_pfx_password'
        key, cert, _ = pkcs12.load_key_and_certificates(Path(PFX).read_bytes(), password or None)
        self.phase = 'checking_certificate'
        if key is None or cert is None or cert.fingerprint(hashes.SHA1()).hex().upper() != FINGERPRINT:
            raise ValueError('PFX does not match the verified EFS certificate')
        fmt = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        if key.public_key().public_bytes(*fmt) != cert.public_key().public_bytes(*fmt):
            raise ValueError('Certificate and private key do not match')
        # A real decryption probe validates tool compatibility before accepting.
        self.phase = 'testing_decryption'
        stream = DecryptedStream(SAMPLE, source_path(SAMPLE).stat().st_size, password)
        try:
            head = stream.read(12, 0)
            if head[:4] != b'RIFF' or head[8:12] != b'AVI ':
                raise ValueError('Sample video did not decrypt to a valid AVI header')
        finally:
            stream.close()
        self.password = password
        self.phase = 'unlocked'

    def serve(self):
        RUNTIME.mkdir(mode=0o700, exist_ok=True)
        SOCKET.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX) as server:
            server.bind(str(SOCKET))
            os.chmod(SOCKET, 0o600)
            server.listen(2)
            while True:
                connection, _ = server.accept()
                with connection:
                    connection.settimeout(30)
                    data = bytearray()
                    try:
                        while not data.endswith(b'\n'):
                            chunk = connection.recv(4096)
                            if not chunk or len(data) + len(chunk) > 8192:
                                raise ValueError('Invalid request')
                            data.extend(chunk)
                        request = json.loads(data)
                        if request.get('command') == 'unlock':
                            password = request.pop('password').encode()
                            if b'\n' in password or b'\x00' in password:
                                raise ValueError('Unsupported password encoding')
                            with self.lock:
                                self.verify(password)
                            password = None
                        elif request.get('command') != 'status':
                            raise ValueError('Unknown command')
                        reply = {'unlocked': self.password is not None,
                                 'active_streams': self.active_streams, 'phase': self.phase}
                    except Exception:
                        # Never echo request data or exception text containing it.
                        message = ('PFX password was not accepted.' if self.phase == 'checking_pfx_password'
                                   else 'Unlock failed after password validation; reader setup needs checking.')
                        reply = {'error': message, 'phase': self.phase}
                    finally:
                        password = None
                        data[:] = b'\0' * len(data)
                    connection.sendall(json.dumps(reply).encode() + b'\n')


def client(command):
    """Prompt locally over SSH; send only to the daemon's root-only UNIX socket."""
    for attempt in range(1, 6):
        request = {'command': command}
        if command == 'unlock':
            if not sys.stdin.isatty():
                raise RuntimeError('Use your own private interactive terminal')
            request['password'] = getpass.getpass(f'PFX password (attempt {attempt}/5): ')
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(90)
            connection.connect(str(SOCKET))
            connection.sendall(json.dumps(request).encode() + b'\n')
            request.clear()
            reply = json.loads(connection.makefile('rb').readline(8192))
        print(json.dumps(reply))
        if 'error' not in reply:
            return 0
        if command == 'status' or reply.get('phase') != 'checking_pfx_password':
            return 1
    return 1


def mount_view():
    """Expose normal reads plus EFS streams through a kernel-enforced ro mount."""
    from fusepy import FUSE, FuseOSError, Operations
    state = UnlockState()

    class View(Operations):
        def __init__(self):
            self.handles = {}
            self.ids = itertools.count(1)
            self.handle_lock = threading.Lock()

        def init(self, path):
            threading.Thread(target=state.serve, daemon=True).start()

        def getattr(self, path, fh=None):
            st = source_path(path).stat()
            if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                raise FuseOSError(errno.EACCES)
            result = {name: getattr(st, name) for name in
                      ('st_size', 'st_atime', 'st_mtime', 'st_ctime', 'st_nlink', 'st_ino')}
            result.update(st_uid=100000, st_gid=100000,
                          st_mode=stat.S_IFMT(st.st_mode) | (0o555 if stat.S_ISDIR(st.st_mode) else 0o444))
            return result

        def readdir(self, path, fh):
            return ['.', '..'] + os.listdir(source_path(path))

        def statfs(self, path):
            st = os.statvfs(SOURCE)
            return {name: getattr(st, name) for name in
                    ('f_bavail', 'f_bfree', 'f_blocks', 'f_bsize', 'f_favail', 'f_ffree',
                     'f_files', 'f_frsize', 'f_namemax')}

        def open(self, path, flags):
            if flags & (os.O_ACCMODE | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
                raise FuseOSError(errno.EROFS)
            full = source_path(path)
            st = full.stat()
            if not stat.S_ISREG(st.st_mode):
                raise FuseOSError(errno.EACCES)
            encrypted = int.from_bytes(os.getxattr(full, 'system.ntfs_attrib'), 'little') & 0x4000
            with self.handle_lock:
                if encrypted:
                    if state.password is None:
                        raise FuseOSError(errno.EACCES)
                    if state.active_streams >= 8:
                        raise FuseOSError(errno.EMFILE)
                    handle = DecryptedStream(path, st.st_size, state.password)
                    try:
                        # Fail before the HTTP server emits download headers.
                        handle.read(min(512, st.st_size), 0)
                    except Exception:
                        handle.close()
                        raise
                    state.active_streams += 1
                else:
                    handle = os.open(full, os.O_RDONLY | os.O_NOFOLLOW)
                ident = next(self.ids)
                self.handles[ident] = handle
                return ident

        def read(self, path, size, offset, fh):
            handle = self.handles[fh]
            return os.pread(handle, size, offset) if isinstance(handle, int) else handle.read(size, offset)

        def release(self, path, fh):
            with self.handle_lock:
                handle = self.handles.pop(fh)
                if isinstance(handle, int):
                    os.close(handle)
                else:
                    handle.close()
                    state.active_streams -= 1
            return 0

    MOUNT.mkdir(mode=0o755, exist_ok=True)
    FUSE(View(), str(MOUNT), foreground=True, ro=True, allow_other=True,
         default_permissions=True, nothreads=False, nodev=True, nosuid=True,
         noexec=True, fsname='efs-on-demand', attr_timeout=1, entry_timeout=1)


if __name__ == '__main__':
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.umask(0o077)
    if len(sys.argv) != 2 or sys.argv[1] not in ('mount', 'unlock', 'status'):
        raise SystemExit('Usage: efs-view.py mount|unlock|status')
    if sys.argv[1] == 'mount':
        mount_view()
    else:
        raise SystemExit(client(sys.argv[1]))
