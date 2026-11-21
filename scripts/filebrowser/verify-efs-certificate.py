#!/usr/bin/env python3
"""Verify the candidate PFX against a file's EFS metadata without exporting keys.

EFS structures: tuxera/ntfs-3g include/ntfs-3g/layout.h (EFS_ATTR_HEADER,
EFS_DF_HEADER, EFS_DF_CREDENTIAL_HEADER, EFS_DF_CERTIFICATE_THUMBPRINT_HEADER).
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

PFX = Path('/mnt/filebrowser/SSK/cloud-backup/onedrive/Documents/encryption_key_certs_for_linuxfour_backup.pfx')
TARGET = '/linuxfour_backup/iso_backup/vlc-record-2020-04-13-15h06m25s-MOVI0033.avi-.avi'
DEVICE = '/dev/mapper/filebrowser-bitlocker'
RESULT = Path('/run/filebrowser-efs-verification/result.json')


def efs_thumbprints(data: bytes) -> list[dict[str, str]]:
    """Extract certificate SHA-1 fingerprints from bounded DDF/DRF records."""
    def require(offset: int, size: int, end: int) -> None:
        if offset < 0 or size < 0 or offset + size > end:
            raise ValueError('Invalid EFS metadata bounds')

    def u32(offset: int, end: int) -> int:
        require(offset, 4, end)
        return struct.unpack_from('<I', data, offset)[0]

    require(0, 76, len(data))
    total = u32(0, len(data))
    if not 76 <= total <= len(data):
        raise ValueError('Invalid EFS metadata length')
    found = []
    for kind, header_offset in [('decryption', 64), ('recovery', 68)]:
        offset = u32(header_offset, total)
        if not offset:
            continue
        count = u32(offset, total)
        if count > 128:
            raise ValueError('Unexpected EFS credential count')
        cursor = offset + 4
        for _ in range(count):
            require(cursor, 20, total)
            length = u32(cursor, total)
            if length < 20:
                raise ValueError('Invalid EFS credential record length')
            require(cursor, length, total)
            end = cursor + length
            cred = cursor + u32(cursor + 4, end)
            require(cred, 28, end)
            cred_length = u32(cred, end)
            require(cred, cred_length, end)
            cred_end = cred + cred_length
            if u32(cred + 8, cred_end) == 3:
                thumb = cred + u32(cred + 16, cred_end)
                require(thumb, 20, cred_end)
                start = thumb + u32(thumb, cred_end)
                size = u32(thumb + 4, cred_end)
                require(start, size, cred_end)
                if size != 20:
                    raise ValueError('Unsupported EFS certificate fingerprint size')
                found.append({'kind': kind, 'sha1': data[start:start + size].hex().upper()})
            cursor = end
    if not found:
        raise ValueError('No supported EFS certificate fingerprints found')
    return found


def read_metadata() -> list[dict[str, str]]:
    """Read only the EFS logged-utility attribute from the read-only mapper."""
    readonly = subprocess.check_output(['blockdev', '--getro', DEVICE], text=True).strip()
    if readonly != '1':
        raise RuntimeError('BitLocker mapping must be read-only')
    # ntfscat always uses NTFS_MNT_RDONLY. Force bypasses its mounted-volume
    # exclusion; the block-device read-only guard above also prevents writes.
    result = subprocess.run(['ntfscat', '-f', '-a', '256', '-n', '$EFS', DEVICE, TARGET],
                            capture_output=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace').strip())
    return efs_thumbprints(result.stdout)


def main() -> int:
    """Prompt privately, verify key/certificate, and save a non-secret result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--metadata-only', action='store_true')
    args = parser.parse_args()
    expected = read_metadata()
    if args.metadata_only:
        print(json.dumps({'expected_certificates': expected}, indent=2))
        return 0
    if not sys.stdin.isatty():
        raise RuntimeError('Run in your own interactive terminal; password input must be hidden')
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509 import ExtensionNotFound, ExtendedKeyUsage, ObjectIdentifier

    os.umask(0o077)
    RESULT.parent.mkdir(mode=0o700, exist_ok=True)
    # Clear only this verifier's old result, preventing a stale PASS after failure.
    RESULT.write_text(json.dumps({'status': 'awaiting_password'}) + '\n')
    bundle = PFX.read_bytes()
    print('Verifying:', PFX.name)
    print('The password is hidden and is not saved. Up to five attempts are allowed.')
    for attempt in range(1, 6):
        password = getpass.getpass(f'PFX password (attempt {attempt}/5): ')
        try:
            key, certificate, _ = pkcs12.load_key_and_certificates(bundle, password.encode() or None)
            break
        except ValueError:
            print('Password not accepted, or the PFX is invalid. Try again.')
        finally:
            password = None
    else:
        RESULT.write_text(json.dumps({'status': 'password_not_verified'}) + '\n')
        print('Not verified. You can rerun this script for more attempts.')
        return 1
    if key is None or certificate is None:
        raise ValueError('The PFX must contain both a private key and its certificate')
    public_format = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    key_matches = key.public_key().public_bytes(*public_format) == certificate.public_key().public_bytes(*public_format)
    fingerprint = certificate.fingerprint(hashes.SHA1()).hex().upper()
    matches_file = any(item['sha1'] == fingerprint for item in expected)
    try:
        efs_usage = ObjectIdentifier('1.3.6.1.4.1.311.10.3.4') in certificate.extensions.get_extension_for_class(ExtendedKeyUsage).value
    except ExtensionNotFound:
        efs_usage = False
    passed = key_matches and matches_file
    result = {'status': 'verified_match' if passed else 'certificate_mismatch',
              'certificate_sha1': fingerprint, 'private_key_present': True,
              'private_key_matches_certificate': key_matches,
              'certificate_matches_file': matches_file, 'efs_extended_key_usage': efs_usage}
    RESULT.write_text(json.dumps(result, indent=2) + '\n')
    key = None
    print(json.dumps(result, indent=2))
    print('No private key was exported; the original PFX and video were not changed.')
    return 0 if passed else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('Verification could not complete:', str(error), file=sys.stderr)
        sys.exit(1)
