# Module — Users

Specification: §§4, 20, 22.

## Responsibility

Represent people who operate the system: role, organization, and shelter or block assignment. This is operational identity, not a population register of shelter residents.

## Endpoints

### `POST /api/v1/users/`

Permission: `user.manage`.

Request `UserCreate`: `name`, `username`, `password` (omitted when the tenant is SSO-only), `role`, `organization`, `shelter_id` or `block_id` according to role.

| Role | Assignment rule |
| --- | --- |
| Warden | `shelter_id` required, `block_id` omitted |
| Block Officer | `block_id` required, `shelter_id` omitted |
| District Officer | both omitted |
| Volunteer | `shelter_id` or `block_id` required, plus `support_functions` from `reporting_support`, `onboarding`, `training`, `verification`, `local_coordination` |

Success: `201`. Event: `user.registered`. Response omits password and hash.

### `PATCH /api/v1/users/{user_id}`

Permission: `user.manage`. Role or assignment change publishes `user.assignment_changed`. Disabling a user sets `status: inactive` and refresh tokens for that user stop working.

### `GET /api/v1/users/`

Permission: `user.read`. Tenant scoped. Query: `role`, `block_id`, `shelter_id`.

Self-service profile is `GET /api/v1/auth/me`, not this collection.

## Privacy

Do not add fields for residents. Volunteer and warden records contain only what coordination needs: name, role, organization, assignment, and a reporting contact held on the shelter.

## Validation failures

Wrong assignment shape for the role is `400` `VALIDATION_ERROR`. Shelter in another tenant is `404`.

## Tests

Create each role with a legal assignment. Reject a warden without a shelter. Reject a volunteer with `action.approve` in the payload (unknown field or forbidden permission grant) with `400`. Inactive user cannot refresh.
