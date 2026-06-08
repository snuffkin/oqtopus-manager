# Authentication

OQTOPUS Manager supports pluggable authentication providers configured under the `auth` key in `config.yaml`.

## Provider overview

| `provider` | Description |
|------------|-------------|
| `none` | Authentication is disabled. All requests are allowed without a user identity. Suitable for local development only. |
| `header` | Reads user identity from HTTP headers injected by a trusted reverse proxy (e.g. AWS ALB + Amazon Cognito via oauth2-proxy). |

## provider: none

```yaml
auth:
  provider: none
```

No additional configuration is required.
`request.state.user` is `None` for every request, and the **My Account** page is hidden from the sidebar.

## provider: header

Trusts HTTP headers set by a reverse proxy that sits in front of OQTOPUS Manager.
The proxy is responsible for authenticating the user and injecting the identity headers before forwarding the request.

### Full configuration reference

```yaml
auth:
  provider: header
  header:
    user_header: x-forwarded-email
    roles_header: x-forwarded-groups
    allow_raw_roles:
      - oqtopus-manager.*
    signature_verification:
      enabled: true
      header: authorization
      issuer: https://your-issuer-url/
      audience: your-audience
    signout_url: https://your-proxy/oauth2/sign_out
  role_mappings:
    your-app.operator: operator
    your-app.admin: admin
```

### header.*

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `user_header` | string | No | `x-forwarded-email` | Request header containing the authenticated user's email address. |
| `roles_header` | string | No | `x-forwarded-groups` | Request header containing a comma-separated list of raw role/group values set by the proxy. |
| `allow_raw_roles` | list of strings | No | *(allow all)* | Glob patterns (shell-style, using `fnmatch`) applied to each raw value from `roles_header` **before** `role_mappings`. Values that do not match any pattern are discarded. When omitted or empty, all values are allowed through. See [allow_raw_roles](#allow_raw_roles) for details. |

### header.signature_verification.*

JWT signature verification prevents header spoofing: even if a client forges the `user_header` / `roles_header` values, it cannot forge a valid JWT signed by the identity provider.

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `enabled` | boolean | No | `false` | Set `true` to enable JWT verification. |
| `header` | string | No | `authorization` | Request header containing the JWT (`Bearer <token>`). |
| `issuer` | string | Yes (if enabled) | — | Expected `iss` claim in the JWT. Used to derive the JWKS endpoint (`{issuer}/.well-known/jwks.json`). |
| `audience` | string | Yes (if enabled) | — | Expected `aud` claim in the JWT. |

!!! warning "Token expiry"
    The proxy must refresh tokens before they expire. When using oauth2-proxy, set `cookie_refresh` to a value shorter than the identity provider's token lifetime (e.g. `cookie_refresh = "50m"` for a 60-minute token). If the token expires before refresh, requests will be rejected with `JWT verification failed: Signature has expired`.

### header.signout_url

| Key | Type | Required | Default | Description |
|-----|------|----------|---------|-------------|
| `signout_url` | string | No | — | URL the **Sign out** sidebar link points to. When omitted, the Sign out link is hidden. Typically the oauth2-proxy sign-out endpoint. |

## allow_raw_roles

`allow_raw_roles` is a list of [fnmatch](https://docs.python.org/3/library/fnmatch.html) glob patterns.

| Pattern character | Meaning |
|-------------------|---------|
| `*` | Matches any string of characters (zero or more) |
| `?` | Matches any single character |
| `[seq]` | Matches any character in `seq` |

The patterns are evaluated with **OR** logic — a value is allowed if it matches **any** pattern in the list.

**Example:**

```yaml
allow_raw_roles:
  - oqtopus-manager.*
```

| Raw value | Matches? |
|-----------|----------|
| `oqtopus-manager.admin` | ✓ |
| `oqtopus-manager.operator` | ✓ |
| `other-app.admin` | ✗ (discarded before role_mappings) |

## role_mappings

Maps raw role values to display names used throughout the UI.
Applies regardless of which provider is configured.

```yaml
auth:
  role_mappings:
    your-app.operator: operator
    your-app.admin: admin
```

| Behaviour | Description |
|-----------|-------------|
| Mapped value | Displayed as the mapped name (e.g. `admin`, `operator`). |
| Unmapped value | Passed through as-is (the raw string). |
| No match at all | The request is rejected with `403 Forbidden`. |

Role display colours in the UI:

| Role name | Colour |
|-----------|--------|
| `admin` | Amber |
| `operator` | Blue |
| anything else | Grey |

## Debug endpoint

The `/debug` page shows all request headers, the decoded JWT payload, and the mapped roles.
It is intended for verifying that a reverse proxy is injecting the expected headers.

```yaml
auth:
  enable_debug_endpoint: true   # default: false
```

!!! warning
    `/debug` exposes authentication tokens and user identity in plain text.
    Never enable it in production.

## Example: Amazon Cognito with oauth2-proxy

This example shows a complete setup using Amazon Cognito as the identity provider and [oauth2-proxy](https://oauth2-proxy.github.io/oauth2-proxy/) as the reverse proxy.

### Architecture

```text
Browser → oauth2-proxy → OQTOPUS Manager
                ↕
          Amazon Cognito
```

oauth2-proxy authenticates the user against Cognito and injects the identity headers before forwarding requests to OQTOPUS Manager.

### oauth2-proxy configuration (`oauth2-proxy.cfg`)

```cfg
# Provider
provider          = "oidc"
oidc_issuer_url   = "https://cognito-idp.{region}.amazonaws.com/{user-pool-id}"
oidc_groups_claim = "cognito:groups"
scope             = "openid email"
client_id         = "{app-client-id}"
client_secret     = "{app-client-secret}"

# Network
http_address = "127.0.0.1:4180"
redirect_url = "http://127.0.0.1:4180/oauth2/callback"
upstreams    = ["http://localhost:38000"]

# Cookie
cookie_secret  = "{32-byte-random-secret}"
cookie_secure  = false   # true in production (requires HTTPS)
cookie_refresh = "50m"   # must be shorter than Cognito token expiry (default 1h)

# Headers passed to upstream
set_xauthrequest          = true   # X-Auth-Request-* headers
pass_authorization_header = true   # Authorization: Bearer <id_token> for JWT verification
pass_user_headers         = true   # X-Forwarded-Email, X-Forwarded-Groups, etc.
pass_access_token         = false

# Access control
email_domains = ["*"]

# UI
skip_provider_button = true
```

Generate `cookie_secret` with the following one-liner:

```shell
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

oauth2-proxy injects the following headers into upstream requests:

| Header | Example value | Maps to |
|--------|--------------|---------|
| `x-forwarded-email` | `alice@example.com` | `user_header` |
| `x-forwarded-groups` | `oqtopus-manager.admin,oqtopus-manager.operator` | `roles_header` |
| `authorization` | `Bearer eyJ...` | `signature_verification.header` |

### OQTOPUS Manager configuration (`config.yaml`)

```yaml
auth:
  provider: header
  header:
    user_header: x-forwarded-email
    roles_header: x-forwarded-groups
    allow_raw_roles:
      - oqtopus-manager.*          # discard groups from other applications
    signature_verification:
      enabled: true                # verify the JWT to prevent header spoofing
      header: authorization
      issuer: "https://cognito-idp.{region}.amazonaws.com/{user-pool-id}"
      audience: "{app-client-id}"
    signout_url: "http://localhost:4180/oauth2/sign_out?rd={cognito-login-url}"
  role_mappings:
    oqtopus-manager.operator: operator
    oqtopus-manager.admin: admin
```

### Cognito setup checklist

1. **User Pool** — create a Cognito User Pool.
2. **App client** — create an app client with:
    - OAuth 2.0 grant type: **Authorization code**
    - Scopes: `openid`, `email`
    - Callback URL: `http://localhost:4180/oauth2/callback` (or your production URL)
3. **Groups** — create groups named `oqtopus-manager.operator` and `oqtopus-manager.admin` and assign users.
4. **`iss` claim** — the issuer URL is `https://cognito-idp.{region}.amazonaws.com/{user-pool-id}`.
5. **`aud` claim** — the audience is the App client ID.
6. **Token expiry** — the default ID token lifetime is **1 hour**. Set `cookie_refresh = "50m"` in oauth2-proxy to ensure tokens are refreshed before they expire.
