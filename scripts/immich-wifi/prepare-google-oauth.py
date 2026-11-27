#!/usr/bin/env python3
"""Convert Google's downloaded Web client JSON to a SOPS-encrypted Helm secret.

No plaintext files are written and no credential values are logged. Rerunning
requires --replace so rotations are deliberate. Existing backup clients remain
independent. Run from this checkout so SOPS uses the repository creation rules.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / 'gitops/clusters/homelab/apps/photo-enrichment/immich-pilot/google-oauth.sops.yaml'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('client_json', type=Path)
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    if TARGET.exists() and not args.replace:
        raise SystemExit('Encrypted configuration exists; use --replace for a reviewed rotation')
    client = json.loads(args.client_json.read_text()).get('web', {})
    if not client.get('client_id', '').endswith('.apps.googleusercontent.com') or not client.get('client_secret'):
        raise SystemExit('Expected a downloaded Google Web application client JSON')
    os.environ.setdefault('SOPS_AGE_KEY_FILE', str(Path.home()/'.config/sops/age/keys.txt'))
    network = subprocess.run(['sops', '--decrypt', '--output-type', 'json', str(TARGET.parent.parent/'immich-wifi/network.sops.yaml')], capture_output=True, text=True, check=True)
    settings = dict(line.split('=', 1) for line in json.loads(network.stdout)['stringData']['network.env'].splitlines() if '=' in line and not line.startswith('#'))
    origin = 'https://' + settings['IMMICH_HOSTNAME']
    required = {origin + path for path in ['/auth/login', '/user-settings', '/api/oauth/mobile-redirect']}
    if set(client.get('redirect_uris', [])) != required:
        raise SystemExit('Client callbacks differ from the three approved Immich HTTPS callbacks')
    values = {'immich': {'configuration': {'oauth': {
        'enabled': True, 'issuerUrl': 'https://accounts.google.com',
        'clientId': client['client_id'], 'clientSecret': client['client_secret'],
        'scope': 'openid email profile', 'signingAlgorithm': 'RS256',
        'profileSigningAlgorithm': 'none', 'tokenEndpointAuthMethod': 'client_secret_post',
        'buttonText': 'Sign in with Google', 'autoRegister': False,
        'autoLaunch': False, 'prompt': 'select_account',
        'mobileOverrideEnabled': True,
        'mobileRedirectUri': origin + '/api/oauth/mobile-redirect',
    }, 'passwordLogin': {'enabled': True}}}}
    manifest = {'apiVersion': 'v1', 'kind': 'Secret', 'metadata': {
        'name': 'immich-google-oauth', 'namespace': 'immich-pilot',
        'labels': {'reconcile.fluxcd.io/watch': 'Enabled'}},
        'type': 'Opaque', 'stringData': {'values.yaml': yaml.safe_dump(values, sort_keys=False)}}
    encrypted = subprocess.run(['sops', '--encrypt', '--input-type', 'yaml', '--output-type', 'yaml', '--filename-override', str(TARGET), '/dev/stdin'],
        input=yaml.safe_dump(manifest, sort_keys=False), capture_output=True, text=True, cwd=ROOT)
    if encrypted.returncode:
        raise SystemExit('SOPS encryption failed; no credential values logged')
    TARGET.write_text(encrypted.stdout)
    print('Encrypted OAuth Helm values written; no plaintext configuration created')


if __name__ == '__main__':
    main()
