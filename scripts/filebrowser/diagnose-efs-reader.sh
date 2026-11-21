#!/usr/bin/env bash
# Test the installed decryptor with a synthetic key; never opens the user's PFX.
set -euo pipefail
ssh -o BatchMode=yes "root@${1:-pumped-piglet.maas}" 'python3 -' <<'PY'
import datetime,os,subprocess,tempfile
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID,ObjectIdentifier
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12

os.umask(0o077)
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Synthetic EFS diagnostic')])
now=datetime.datetime.utcnow()
cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
    .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(days=1))
    .not_valid_after(now+datetime.timedelta(days=1))
    .add_extension(x509.ExtendedKeyUsage([ObjectIdentifier('1.3.6.1.4.1.311.10.3.4')]),critical=False)
    .sign(key,hashes.SHA256()))
password=os.urandom(24).hex().encode()
with tempfile.TemporaryDirectory(prefix='efs-synthetic-',dir='/run') as directory:
    pfx=Path(directory)/'synthetic.pfx'
    pfx.write_bytes(pkcs12.serialize_key_and_certificates(b'diagnostic',key,cert,None,serialization.BestAvailableEncryption(password)))
    command=['/usr/local/sbin/filebrowser-ntfsdecrypt' if Path('/usr/local/sbin/filebrowser-ntfsdecrypt').exists() else 'ntfsdecrypt','-f','-q','-k',str(pfx),'/dev/mapper/filebrowser-bitlocker',
        '/linuxfour_backup/iso_backup/vlc-record-2020-04-13-15h06m25s-MOVI0033.avi-.avi']
    assert subprocess.check_output(['blockdev','--getro',command[-2]],text=True).strip()=='1'
    result=subprocess.run(command,input=password+b'\n',stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                          start_new_session=True,timeout=30)
    print('Synthetic decryptor exit:',result.returncode)
    print(result.stderr.decode(errors='replace'))
    if command[0].startswith('/usr/local/'):
        assert b'Key does not have an EFS purpose OID' not in result.stderr
        assert b'Failed to verify the MAC' not in result.stderr
        assert b'Failed to obtain file encryption key' in result.stderr
        print('PASS: synthetic password and EFS certificate accepted; unrelated file key correctly rejected.')
    print('Temporary synthetic key removed on exit; user PFX was not accessed.')
PY
