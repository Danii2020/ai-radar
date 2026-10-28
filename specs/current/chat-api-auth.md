# Chat API Authentication Specification

> Last synced: 2026-10-28. Owned artifacts: `infra/lib/chat_api.py` (the `AWS_IAM` authorizer, the
> caller user and its policy, the removed CORS configuration), `infra/stacks/chat_api_stack.py`
> (the removed origins option, the `ChatApiCallerUserName` output), `run_chat_api_smoke.py`
> (developer signing probe), `tests/test_chat_api_smoke.py`, the auth assertions in
> `tests/test_infra_chat_api.py`, and the README "Authentication amendment (`chat-api-auth`)" runbook.

## Purpose

Who may call `POST /v1/chat`, how that caller's credential is created and stored, and why browsers
get no CORS. The gate is API Gateway's, not the handler's: an unsigned request never reaches the
Lambda or the agent. It is its own capability because it is a separate boundary (IAM principals,
access policy and a long-lived secret) that changes independently of the handler's behavior, which
stays in `chat-api`. It supersedes the `chat-api` decision that throttling is the only abuse guard
(ADR 0027).

## Requirements

### Requirement: CAAUTH-1 — A correctly signed turn is handled exactly as before

The system SHALL handle a `POST /v1/chat` signed with SigV4 (service `execute-api`, region
`us-east-1`) by the caller principal with the same handler and the same response contract as
`chat-api`. The handler is unchanged.

**Source:** chat-api-auth · intent.md § AC1; execution-plan.md § Binding constraints

#### Scenario: A signed grounded question
- **WHEN** `run_chat_api_smoke.py` sends one signed `POST /v1/chat` with the caller's key
- **THEN** the response is 200 with a grounded answer, `[1]` cited, in 5161 ms (verified 2026-10-21, tasks O7)

### Requirement: CAAUTH-2 — Every request that is not validly signed by a permitted principal is rejected at the gateway

The system SHALL reject, with 403, every `POST /v1/chat` that is not validly signed by a principal
with `execute-api:Invoke` on the route. This covers an unsigned request, a fabricated
`Authorization` header, a bad signature, and a valid signature from an identity with no grant. The
Lambda and the agent SHALL NOT be invoked for any of them.

**Source:** chat-api-auth · intent.md § AC2; execution-plan.md § Proposed approach (`AWS_IAM` authorizer), § Validation AC2

#### Scenario: An unsigned request with a valid body
- **WHEN** an unsigned `POST /v1/chat` with a valid body reaches the API
- **THEN** the response is 403 `{"message":"Forbidden"}`, and the `Invocations` metric does not move (verified 2026-10-21)

#### Scenario: A bad signature or a policy-less identity
- **WHEN** the caller key is used with `--tamper`, or a throwaway IAM identity with no policy signs the request
- **THEN** the response is 403 for both, and no invocation is recorded (verified 2026-10-21; the throwaway identity was deleted afterwards)

#### Scenario: An expired signature
- **WHEN** a request is signed with an expired clock
- **THEN** the response is 403 by AWS's SigV4 rules. This was not exercised live: the human accepted `--tamper` as the bad-signature probe (open reservation CAAUTH-F1)

### Requirement: CAAUTH-3 — A request to an unrouted method or path is rejected at routing, without the Lambda

The system SHALL answer a request to any method or path other than `POST /v1/chat` with 404, from
routing, before authorization, so the Lambda is not invoked. A signed request of that kind was not
run live (open reservation CAAUTH-F9).

**Source:** chat-api-auth · intent.md § AC2 (last sentence); chat-api · CAPI-4

#### Scenario: Unsigned requests to other methods
- **WHEN** an unsigned `GET /v1/chat` or an `OPTIONS /v1/chat` with `Origin` is sent
- **THEN** the response is 404, and no invocation is recorded (verified 2026-10-21)

### Requirement: CAAUTH-4 — The route is the only authenticated surface, and browsers are not a caller

The system SHALL keep exactly one route, `POST /v1/chat`, authorized with `AWS_IAM`. It SHALL have no
authorizer resource and no CORS configuration, and it SHALL emit no `access-control-*` header. The
`chat_api_allowed_origins` deploy option and the `ChatApiAllowedOrigins` output SHALL NOT exist.

**Source:** chat-api-auth · intent.md § AC3; execution-plan.md § Binding constraints

#### Scenario: A cross-origin browser request
- **WHEN** a preflight with `Origin: http://localhost:3000` reaches the API
- **THEN** the response carries no `access-control-*` header, `CorsConfiguration` is null in `get-api`, and the route reads `POST /v1/chat AWS_IAM` (verified 2026-10-21)

### Requirement: CAAUTH-5 — The only principal the stack grants is the caller user, with one statement

The system SHALL create exactly one IAM user, `ai-radar-chat-api-caller`, whose only permission is one
inline statement: `Allow` `execute-api:Invoke` on this API's `POST /v1/chat` route, for any stage. It
SHALL NOT have a managed policy, a group or a login profile, and its resource SHALL NOT be a wildcard.
The stack SHALL output the user name as `ChatApiCallerUserName`.

**Source:** chat-api-auth · intent.md § AC4; execution-plan.md § Binding constraints

#### Scenario: The synthesized and live caller
- **WHEN** the stack is synthesized, and the user is read after deploy
- **THEN** there is one `AWS::IAM::User` with one inline statement (live: one inline policy, no attached policy, no group, no login profile), and the output `ChatApiCallerUserName=ai-radar-chat-api-caller` is present (verified 2026-10-21)

### Requirement: CAAUTH-6 — The caller's credential is never created by CloudFormation, and is stored server-side only

The system SHALL NOT create an `AWS::IAM::AccessKey` for the caller, and no secret SHALL appear in
CloudFormation, the repository, test fixtures or logs. A human creates the key with the AWS CLI and
stores it only in the frontend's server environment, never a `NEXT_PUBLIC_` variable. The runbook SHALL
document creating, storing and rotating the key.

**Source:** chat-api-auth · intent.md § AC4 and § Constraints; execution-plan.md § Binding constraints, § Proposed approach (rotation)

#### Scenario: The template and the working tree
- **WHEN** the template is synthesized and the tracked and untracked files are scanned
- **THEN** there is zero `AWS::IAM::AccessKey`, and no real API id, no `AKIA`/`ASIA` key id and no secret appears (the audit scan of 436 files; verified 2026-10-21)

#### Scenario: The live key
- **WHEN** `aws iam list-access-keys` is read for the caller
- **THEN** there is one key, created by the human outside CloudFormation, and it is `Active` (verified 2026-10-21). It stays `Active` in the local profile until the `apps/web` signing spec ships.

### Requirement: CAAUTH-7 — Nothing about the caller is logged

The `chat_api_request` record SHALL keep exactly its `chat-api` keys (CAPI-7). It SHALL NOT contain the
caller's principal ARN, the access key id, the signature, or any `requestContext.authorizer` value.

**Source:** chat-api-auth · intent.md § AC5; execution-plan.md § Binding constraints (the handler is unchanged)

#### Scenario: The record after a signed request
- **WHEN** the signed 200 call is logged
- **THEN** the record has exactly the seven keys `duration_ms, event, history_items, outcome, question_chars, session_id, status`, and no principal, key or signature text (verified 2026-10-21)

### Requirement: CAAUTH-8 — The API is updated in place, and the other stacks do not move

The system SHALL keep the `HttpApi` construct id, so the logical id `ChatApiChatHttpApi975E960D` is
stable, and the API id and the URL SHALL NOT change. The `AiRadarFeedApi`, `AiRadarChatRuntime` and
the other stacks SHALL NOT be modified. The Lambda role, the stage throttle (5 rps, burst 10), the
28 s timeout, the reserved-concurrency default and the `none` override, and `CHAT_RUNTIME_ARN` are unchanged.

**Source:** chat-api-auth · intent.md § AC6; execution-plan.md § Binding constraints, § Proposed approach (ADR 0031)

#### Scenario: The deploy
- **WHEN** `AiRadarChatApi` is deployed with `-c chat_api_reserved_concurrency=none`
- **THEN** the update is in place (`UPDATE_COMPLETE`; the API's `CreatedDate` predates the update), the URL is the same, and the other stacks' last-update times are unchanged (verified 2026-10-21)

### Requirement: CAAUTH-9 — The live checks and the rotation procedure are documented, and their results recorded

The system SHALL document, in the README runbook, the deploy and its `cdk diff` review, the caller key's
creation, storage and rotation, and the live checks: unsigned 403, the previously exposed URL 403, the
signed 200, the other-identity 403, the tampered 403, the CORS removal check, and the Lambda `Invocations`
delta. The recorded results SHALL be kept in the README and in `tasks.md` O7, without the real API id,
the URL or any key material.

**Source:** chat-api-auth · intent.md § AC7; execution-plan.md § Validation AC7

#### Scenario: The recorded results
- **WHEN** the README "Authentication amendment" is read
- **THEN** it shows the probe table, the Lambda and CORS checks, and the open items, with `<api-id>`, `$API_URL` and `[username]` in place of the real values (verified 2026-10-21)

### Requirement: CAAUTH-10 — A CI smoke role is a second principal on the route, defined outside the stack

The system SHALL allow one more principal to call `POST /v1/chat`: the CI smoke role. It is defined in the CI
access app `infra/ci_bootstrap/`, not in `AiRadarChatApi`. It trusts only `refs/heads/main` through GitHub OIDC,
and its only route permission is `execute-api:Invoke` on `POST /v1/chat`. The deploy role SHALL NOT hold
`execute-api:Invoke`. CAAUTH-5 stays literally true: the stack itself grants only the caller user, with one
statement. This amends ADR 0028, because the set of principals that can call the route grows from one to two
(ADR 0043).

**Source:** backend-cicd-pipeline · intent.md § AC8 and § Constraints (the contradiction with CAAUTH-5 and ADR 0028, accepted by the human 2026-10-27); execution-plan.md § Proposed approach (smoke; ADR candidate 0043); ADR 0043

#### Scenario: The deploy role signs the chat route
- **WHEN** the deploy role sends a signed `POST /v1/chat`
- **THEN** the response is 403 (offline: `tests/test_infra_ci_bootstrap.py`, `test_deploy_role_cannot_call_the_chat_route`).
  The live 403 check is pending O12 f.

#### Scenario: The smoke role signs the chat route
- **WHEN** the smoke role sends a signed `POST /v1/chat` with the smoke probe
- **THEN** the response is 200 with `answer` and `sources` (offline: `tests/test_ci_smoke.py`). The live check is
  pending O12 f.

## Invariants

1. One route, `POST /v1/chat`, authorized with `AWS_IAM`, and no `$default` route. Adding a second, unauthenticated route would expose the Lambda to unauthorized floods, so a test pins the single route.
2. The caller's policy names only this API's `POST /v1/chat` ARN, for one action. Widening it to `*`, to `execute-api:*` or to another route is caught by a synth test.
3. No `AWS::IAM::AccessKey`, `LoginProfile`, managed policy or group is created for the caller. A key created by CloudFormation would put a secret into the template and the stack.
4. The `HttpApi` logical id is stable (ADR 0031). Renaming the construct replaces the API and changes its URL.
5. Authorization changes nothing in the handler's record: `chat_api_request` keeps its seven keys (CAPI-7 in `chat-api`).

## Open reservations

| ID | Reservation | Severity | Source |
|---|---|---|---|
| CAAUTH-F1 | The expired-signature case is not exercised live. Intent AC2 still says "expired". The human accepted `--tamper` as the bad-signature probe. SigV4 expiry is enforced by AWS, and the offline test covers header construction. | LOW | `specs/archived/chat-api-auth/audit.md` (F1, human decision) |
| CAAUTH-F5 | No test asserts that importing `run_chat_api_smoke.py` makes no network or STS call. The auditor's reading is that the import is side-effect free. | LOW | `specs/archived/chat-api-auth/audit.md` (F5) |
| CAAUTH-F6 | CI (`harny-feedback.yml`) has not run, because the branch is unpushed. Local ruff, `ruff --isolated` and mypy are clean. | LOW | `specs/archived/chat-api-auth/audit.md` (F6) |
| CAAUTH-F9 | The signed `GET /v1/chat` and signed `POST /v1/other` probes were not run. The script has no method or path option. The human accepted the unsigned 404 evidence for this sub-case on 2026-10-21. | LOW | `specs/archived/chat-api-auth/audit.md` (F9) |
| CAAUTH-ADMIN | An HTTP API has no resource policy, so any identity in the account whose own policy allows `execute-api:Invoke` on the route, such as an administrator, can call it. The stack grants only the caller. Accepted limitation (intent Revision 2, ADR 0028). Tightening needs a REST API with a resource policy, a later spec. | LOW (accepted) | `specs/archived/chat-api-auth/audit.md` (plan-flagged limits); ADR 0028 |
| CAAUTH-KEY | The caller key is long-lived and stays `Active` in the local profile `ai-radar-chat-caller` until the `apps/web` signing spec ships. Rotation and the leak response are in the README runbook. | LOW (accepted) | ADR 0030; `specs/archived/chat-api-auth/audit.md` (round 2 note) |
| CAAUTH-F11 | The `chat-api` F11 closure re-check was an unsigned burst, which now gets 403 at the gateway and never reaches the Lambda. The re-check must be a signed run after the quota increase. No signed burst tool exists, and none was written. Open work. | MEDIUM (inherits `chat-api` CAPI-F11) | `specs/archived/chat-api-auth/audit.md` (round 2); README amendment |
| CAAUTH-F3 | The Docker build context does not exclude caches such as `.mypy_cache`, so the image fingerprint can change with local tooling runs. Pre-existing debt, not changed here. | LOW | `specs/archived/chat-api-auth/audit.md` (F3) |
| CAAUTH-SMOKE | The principals that may call `POST /v1/chat` grow from one to two: the CI smoke role (CAAUTH-10, ADR 0043). An HTTP API has no resource policy, so the limit is the grant alone. The smoke role's grant is confirmed live only by the first deploy's signed 200 (O12 f). Accepted by the human on 2026-10-27 (Q4). | LOW (accepted) | `specs/archived/backend-cicd-pipeline/audit.md` (round 2, privilege and first-deploy review); ADR 0043 |

## Contributing features

| Feature | Shipped | What it established |
|---|---|---|
| chat-api-auth | 2026-10-21 | CAAUTH-1..CAAUTH-9: `POST /v1/chat` requires AWS SigV4 (`AWS_IAM`) from one stack-created caller user with one `execute-api:Invoke` statement. No CORS, and the origins option is removed. The caller key is created by hand and never sits in CloudFormation. Deployed in place as `AiRadarChatApi`, and amends `chat-api` CAPI-4 and CAPI-6. |
| backend-cicd-pipeline | 2026-10-28 | CAAUTH-10: a second principal may call `POST /v1/chat`, the CI smoke role, defined in the CI access app and trusted only for `main`. Amends ADR 0028 (ADR 0043). The stack's own grant (CAAUTH-5) is unchanged. Implemented and audit-approved with reservations; **not live** (the signed 403/200 check is pending O12 f). |

## Related ADRs

| ADR | Title | Status |
|---|---|---|
| [0028](../archived/chat-api-auth/decisions/0028-chat-route-authorized-by-aws-iam-sigv4-for-one-caller.md) | The chat route is authorized with AWS SigV4 for one dedicated caller, not by throttling | Accepted |
| [0029](../archived/chat-api-auth/decisions/0029-browsers-are-not-a-supported-caller-so-no-cors.md) | Browsers are not a supported caller, so the chat API has no CORS configuration | Accepted |
| [0030](../archived/chat-api-auth/decisions/0030-caller-access-key-is-long-lived-and-created-outside-cloudformation.md) | The caller's access key is long-lived and created by hand, outside CloudFormation | Accepted |
| [0031](../archived/chat-api-auth/decisions/0031-http-api-construct-id-kept-so-the-api-updates-in-place.md) | The HTTP API construct keeps its logical id, so the deploy updates the API in place | Accepted |
| [0043](../archived/backend-cicd-pipeline/decisions/0043-smoke-role-is-a-second-principal-on-the-chat-route.md) | A dedicated CI smoke role becomes a second principal on the chat route, amending ADR 0028 | Accepted |
