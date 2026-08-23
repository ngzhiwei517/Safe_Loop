# SafeLoop production runbook

All production changes require a named operator and a timestamp in the incident or
change record. Never repair workflow state with a direct `UPDATE reports.status`.

## Rollback

### Frontend

1. In Vercel, open Deployments and identify the last known-good Production deployment.
2. Inspect its commit and environment before promoting it.
3. Promote that deployment, then check `/en`, `/zh-CN`, sign-in and one authenticated
   API call.
4. Keep the failed deployment and build logs for diagnosis.

Frontend rollback does not roll back the database or backend. Confirm API compatibility
before promoting an older frontend.

### Backend

List revisions in Singapore:

```bash
gcloud run revisions list \
  --service=safeloop-api \
  --project=safe-506316 \
  --region=asia-southeast1
```

Move all traffic to the last known-good revision:

```bash
gcloud run services update-traffic safeloop-api \
  --project=safe-506316 \
  --region=asia-southeast1 \
  --to-revisions=<known-good-revision>=100
```

Check `/health`, `/health/deep`, one report read and one role-scoped queue read. Do not
delete the failed revision until its logs and request IDs have been retained.

### Database

Migrations are forward-only by default. If an application rollback remains compatible,
leave the schema in place. For an incompatible or destructive migration:

1. Stop deployment and write access.
2. Preserve audit, append-only AI draft, verification and receipt tables.
3. Restore a Supabase point-in-time recovery branch or backup to a separate project.
4. Verify row counts, enum labels, RLS policies and guard triggers there.
5. Switch traffic only after the application suite passes against the restored copy.

Never edit an applied migration file and never delete evidence rows to make rollback
appear successful.

## Key rotation

Rotate one credential at a time and keep the old value active until the new revision is
healthy.

### Supabase database password

1. Rotate the password in Supabase and obtain a Singapore session-pooler URI.
2. Add a new version to `safeloop-database-url` and update `SUPABASE_DB_URL` in the
   protected GitHub environment.
3. Deploy the backend, check deep health, then revoke the old password.

### Supabase service-role and browser keys

1. Create/rotate the key in Supabase API Keys.
2. Put the service-role value in a new `safeloop-service-role-key` version.
3. Update only the publishable/anon value in Vercel.
4. Deploy both surfaces, test signed media/document access, then revoke the old keys.

Never expose the service-role key to a `NEXT_PUBLIC_*` variable.

### JWT secret

The current backend contract verifies HS256 tokens with `SUPABASE_JWT_SECRET`. Rotating
it invalidates outstanding sessions. Schedule a sign-out window, create the new Secret
Manager version, deploy the backend and require users to sign in again. Verify reporter,
reviewer and responsible-role tokens before completing the change.

### Google and Vercel deployment access

Prefer GitHub OIDC for Google; if federation is compromised, disable the provider or
attribute mapping, create a replacement, update the protected GitHub environment and
review Cloud Audit Logs. Revoke and replace the scoped Vercel token, then run a manual
deployment. Neither token belongs in repository variables or local `.env` files.

## AI provider outage

The intake circuit breaker fails closed. A failed graph leaves the report in
`submitted`; it does not create a draft or claim that a human reviewed it. Urgent alerts
remain independent and must continue to reach reviewers.

1. Confirm `/health/deep` reports `provider_unreachable` and use request IDs to inspect
   `ai_run_failed` logs. Check Vertex AI status and quota in `asia-southeast1`.
2. Do not switch production to the stub provider. The stub is only for deterministic
   tests and demos.
3. Tell reviewers to monitor submitted reports and urgent alerts. Do not directly move
   a report into review or closure.
4. After Vertex recovers, retry each still-submitted report through the existing service:

   ```bash
   python -c "import asyncio; from uuid import UUID; from app.services.intake_service import run_intake; asyncio.run(run_intake(UUID('<report-id>'), 'provider-recovery'))"
   ```

5. Confirm each retry either enters clarification, produces a validated review draft,
   or remains submitted with a new diagnosable failure. Record every affected report ID.

Do not rerun a report that has already advanced; `run_intake` refuses statuses outside
`submitted` and answer-complete `clarifying`.

## First-response checks

| Symptom | First check |
| --- | --- |
| API unavailable | Cloud Run revision health, traffic split and request logs |
| Sign-in succeeds but API returns 401 | JWT secret/audience and backend deployment time |
| Photos or documents fail | Deep-health Storage code, bucket privacy and service-role key |
| Queue is empty for one role | Profile role, RLS policy and active assignment—not a direct data update |
| Urgent banner is absent | Alert row, reviewer/admin profile and polling request logs |
| Reports remain submitted | Provider deep health, circuit state and `ai_run_failed` logs |
| Quiz returns 429 | IP rate-limit window and request ID; do not delete valid responses |

The safety invariant takes priority over availability: there is no machine fallback to
verified closure.
