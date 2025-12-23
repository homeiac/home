# Entra ID Configuration for Proxmox

Manual steps to create Azure App Registration for Proxmox OIDC.

## Step 1: Create App Registration

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate: **Microsoft Entra ID** → **App registrations** → **New registration**
3. Configure:
   - **Name**: `Proxmox-Office` (or your preference)
   - **Supported account types**: Single tenant (this org only)
   - **Redirect URI**: Web → `https://<PROXMOX_IP>:8006/`

## Step 2: Add Redirect URIs

1. Go to **Authentication** tab
2. Add URI for each Proxmox node:
   ```
   https://192.168.x.x:8006/
   https://proxmox.office.local:8006/
   ```
3. Click **Save**

## Step 3: Configure API Permissions

1. Go to **API permissions** → **Add a permission**
2. Select **Microsoft Graph** → **Delegated permissions**
3. Add these scopes:
   - `openid`
   - `email`
   - `profile`
   - `offline_access`
4. Click **Grant admin consent for [tenant]**

## Step 4: Create Client Secret

1. Go to **Certificates & secrets** → **New client secret**
2. Description: `Proxmox OIDC`
3. Expiry: Choose based on your policy (24 months max)
4. **COPY THE VALUE IMMEDIATELY** - you can't see it again!

## Step 5: Record Credentials

From the **Overview** page, note:

| Value | Location |
|-------|----------|
| Tenant ID | Directory (tenant) ID |
| Client ID | Application (client) ID |
| Client Secret | The VALUE from Step 4 |

**Issuer URL** (for Proxmox):
```
https://login.microsoftonline.com/<TENANT_ID>/v2.0
```

Do NOT include `/.well-known/openid-configuration` - Proxmox adds it automatically.

## Step 6: Verify Setup

Run the verification script:
```bash
./01-configure-proxmox-oidc.sh --verify-only
```

## Troubleshooting

### Error: Request failed (500)
- Check firewall allows outbound HTTPS to `login.microsoftonline.com`
- Verify you used the secret VALUE, not the secret ID

### Error: 401 Unauthorized
- Client secret may have expired
- Check API permissions have admin consent

### No permissions after login
- Users are autocreated but have no roles
- Assign to group with PVEAdmin role manually

## References

- [Proxmox Forum: Entra ID OIDC](https://forum.proxmox.com/threads/openid-authentication-with-microsoft-entra-id-formerly-azure-ad-error-request-failed-500.150932/)
- [LNC Docs: Entra ID SSO](https://docs.lucanoahcaprez.ch/books/azure-active-directory/page/microsoft-entra-id-sso-for-proxmox)
