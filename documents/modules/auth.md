# Module — Auth

Specification: §§21–22, 31–32. Public route exceptions live in document 03.

## Responsibility

Authenticate a person, issue and revoke tokens, and expose the current principal. Auth does not contain shelter business rules.

## Endpoints

### `POST /api/v1/auth/login`

Public. Request schema `LoginRequest`: `username`, `password`. Response `TokenPair`: `access_token`, `refresh_token`, `token_type: "Bearer"`, `expires_in`.

| Outcome | Status | Code |
| --- | --- | --- |
| Credentials match an active user | 200 | — |
| Body invalid | 400 | `VALIDATION_ERROR` |
| Unknown user or bad password | 401 | `AUTH_INVALID` |
| User disabled | 401 | `AUTH_INVALID` |

The failure response is identical for unknown user and bad password. Event: `auth.login_succeeded` or `auth.login_failed`. Failed logins do not include the password in the payload.

### `POST /api/v1/auth/refresh`

Public, but requires a refresh token in `RefreshRequest`. Rotates the refresh token. Reuse of a rotated token revokes the family and returns `401`.

### `POST /api/v1/auth/logout`

Authenticated. Revokes the current refresh family. `204`. Event: `auth.logout`.

### `GET /api/v1/auth/me`

Authenticated. Returns `id`, `name`, `role`, `tenant_id`, `shelter_id`, `block_id`, and permission names. Does not return `password_hash`.

## SSO port

`AuthenticationProvider` has `authenticate(credentials) -> Principal`. The local password provider is the default adapter. `integrations/sso/` and `integrations/disha/` may supply another adapter later. Controllers stay unchanged when the adapter changes.

## Tests

- Success login, wrong password, disabled user, malformed body.
- Refresh rotation and reuse detection.
- Logout then refresh fails.
- `/auth/me` without a token returns `401`.
- Token from tenant A cannot be used as tenant B by editing a body field.
