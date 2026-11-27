# Immich Google sign-in

Google login reuses the project recorded in the [backup plan](../plans/cloud-drive-backup-and-reclaim.md#12-open-questions).
The rclone Desktop client continues serving backups. A separate **Immich family
sign-in** Web client has only the three Immich HTTPS callbacks.

## Configuration ownership

- Google Cloud owns the Web client and registered redirect URIs.
- `immich-pilot/google-oauth.sops.yaml` stores encrypted Helm values. Flux decrypts
  them; Helm renders application configuration as a Kubernetes Secret.
- The release preserves the existing storage template and GPU settings.
- `autoRegister: false` prevents arbitrary Google accounts from creating users.
- Password login stays enabled and automatic OAuth launch stays disabled.
- The requested scope is `openid email profile`, with no Drive or Photos access.

## Private callback and mobile apps

Google redirects the browser; it does not connect inbound to the private server.
Immich exchanges the code over outbound HTTPS to Google. Register these paths on
the existing Immich HTTPS origin:

| Path | Purpose |
| --- | --- |
| `/auth/login` | Web login |
| `/user-settings` | Link Google to an already signed-in account |
| `/api/oauth/mobile-redirect` | Return to the iPhone or Android app |

Mobile override is enabled with the third URL. On iPhone, enter the same HTTPS
server URL and choose **Sign in with Google**. Home access uses Google Wi-Fi;
away from home, private network access such as Tailscale is still required.

The public secondary DNS can return the unreachable homelab address and break
the callback. See the [network architecture](../reference/google-wifi-immich-architecture.md)
for the accepted internet-first fallback policy. No port forwarding is needed.

## Provision and rotate

1. Create the Web client in the existing Google project with the callbacks above.
   Download its JSON privately; never paste it into an issue or blog.
2. Run `python3 scripts/immich-wifi/prepare-google-oauth.py /absolute/path/client.json`.
   The script checks callbacks against the encrypted network inventory and writes
   only ciphertext. Deliberate rotation requires `--replace`.
3. Run `python3 scripts/immich-wifi/validate-google-oauth.py` and
   `bash scripts/immich-wifi/validate.sh`. The Helm check verifies Secret storage,
   closed registration, password fallback, mobile override, and preserved settings.
4. Review, commit, and push to the branch watched by Flux. Check the HelmRelease
   rollout and `bash scripts/immich-wifi/inspect-auth.sh`.
5. Link Google from the existing administrator's account settings while signed in.
   This preserves the user ID, library ownership, albums, and administrator role.
6. Pre-create ordinary family users with matching Google email addresses. Matching
   existing users can link on login despite automatic registration being disabled.
   Share the intended albums separately; Google login grants no photo access itself.

After encryption and recovery verification, remove downloaded plaintext client
files from Downloads. Keep the age key and its existing recovery process.

## Verification and rollback

Verified November 26, 2026: Helm revision 12 is Ready; public features report
OAuth and password login enabled. The existing administrator linked Google and
then completed a fresh Google login in Chrome, retaining the original library
and administrator role. Linking preserved the original account email; Google
login uses the linked provider identity. No duplicate owner was created.
The Google project is External and In production. Both plaintext JSON downloads
were removed only after comparison with the successfully decrypted SOPS values.

Useful checks:

```bash
bash scripts/immich-wifi/check-google-oauth-rollout.sh
bash scripts/immich-wifi/inspect-live-users.sh
bash scripts/immich-wifi/inspect-live-users.sh --sharing
bash scripts/immich-wifi/reconcile-google-oauth.sh
python3 scripts/immich-wifi/clean-google-oauth-downloads.py
```

The reconciliation script requests controller reconciliation using annotations;
it does not require a local Flux CLI or manually apply resource manifests.
Family accounts were provisioned during setup. A subsequent read-only database
check confirmed three active users: the existing Google-linked administrator,
a Google-linked ordinary family user with an iOS (`GSA`) session, and another
ordinary family user without an OAuth link or session yet. The owner confirmed
that the first family user signed in with her own Google account. Registration
remains closed. The iOS browser session is not proof of native Immich app login.

The earlier statement that family provisioning was still pending was stale.
Use live user and session checks before reporting whether an account exists.
The inspection script prints private account information for local diagnosis;
never commit its output or include it in blog screenshots.

The same live check confirmed one-way partner sharing from the owner to both
ordinary family accounts. Timeline integration is disabled for both relationships.
They can open the owner's shared library through Sharing. No individual album
memberships were present for those accounts at inspection time. Partner sharing
does not automatically include the owner's existing albums; opening named album
links requires album membership or a separate shared link. See
[Immich partner-sharing behavior](https://docs.immich.app/features/partner-sharing/).

Verify browser login reaches the existing administrator account. Verify family
members see the intended shared albums. Test the mobile callback on an actual
iPhone; successful browser login alone does not establish app callback success.

To disable Google login, set `oauth.enabled: false` in the encrypted values and
commit through Flux. Keep password login and remaining configuration intact.
Revoking the Google client is separate and must not affect the rclone client.

Sources: [Immich OAuth](https://docs.immich.app/administration/oauth/),
[v3.4.2 linking implementation](https://github.com/immich-app/immich/blob/v3.4.2/server/src/services/auth.service.ts#L300),
[Google authorization-code flow](https://developers.google.com/identity/protocols/oauth2/web-server).
