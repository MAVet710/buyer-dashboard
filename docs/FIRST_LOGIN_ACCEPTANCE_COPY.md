# DoobieLogic First-Login Acceptance

> **Product copy and implementation specification for the published in-app policies.**
>
> Terms version: `2026-08-1`  
> Privacy version: `2026-08-1`

## Screen copy

### Welcome to DoobieLogic

Before continuing, please review the agreements that govern your use of DoobieLogic.

DoobieLogic supports operational decision-making for regulated cannabis businesses. Calculations, recommendations, mappings, reports, AI-assisted output, and integration data must be reviewed by qualified personnel before they are applied to live inventory, production, point-of-sale, track-and-trace, financial, or compliance systems.

**Required checkbox â€” unchecked by default**

> I have read and agree to the [Terms of Service] and acknowledge the [Privacy Policy]. I confirm that I am at least 21 years old and authorized to use DoobieLogic for my organization.

**Primary button:** `Accept and continue`  
**Secondary action:** `Sign out`

The primary button must remain disabled until the checkbox is selected. The policy links must open without losing the login session and must be keyboard accessible.

### Compact compliance notice

> DoobieLogic is an operational tool, not legal or regulatory advice. Your organization remains responsible for verifying data and complying with applicable requirements.

## Policy update screen

### We updated our terms

Please review and accept the updated agreements to continue using DoobieLogic.

**Required checkbox â€” unchecked by default**

> I have read and agree to the updated [Terms of Service] and acknowledge the updated [Privacy Policy].

**Primary button:** `Accept updated terms`  
**Secondary action:** `Sign out`

Show the effective date and a short, plain-language summary of material changes above the checkbox.

## Trial and sandbox copy

For trial or sandbox users, add this visible notice:

> This environment may contain simulated data and may be reset. Do not rely on sandbox output for live inventory, production, financial, or regulatory reporting.

Trial and sandbox users should still accept the policies. Internal automated test accounts may bypass the visual screen only when they are clearly identified, non-human, restricted to non-production data, and covered by test controls.

## Organization administrator acknowledgement

When the first organization administrator creates or activates an organization, require an additional checkbox:

> I confirm that I am authorized to create this organization, invite its users, connect its systems, and submit data to DoobieLogic on its behalf.

This acknowledgement does not replace a negotiated order form, service agreement, or Data Processing Addendum when one is required.

## Acceptance record

Store an immutable acceptance event containing at least:

- acceptance event ID;
- user ID;
- organization ID, if assigned;
- Terms version;
- Privacy Policy version;
- exact checkbox statement version;
- acceptance timestamp in UTC;
- acceptance method (`first_login`, `policy_update`, or `organization_activation`);
- application environment (`production`, `trial`, or `sandbox`);
- IP address when legally appropriate and disclosed;
- user agent or device metadata when legally appropriate and disclosed; and
- the administrator or system responsible for creating the account.

Do not store a mutable boolean as the only acceptance evidence. Keep historical events when newer policy versions are accepted.

## Suggested database shape

```sql
create table if not exists public.legal_policy_versions (
    id uuid primary key default gen_random_uuid(),
    policy_type text not null check (policy_type in ('terms', 'privacy')),
    version text not null,
    effective_at timestamptz not null,
    document_url text not null,
    document_sha256 text not null,
    requires_reacceptance boolean not null default true,
    published_at timestamptz not null default now(),
    unique (policy_type, version)
);

create table if not exists public.legal_acceptance_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    organization_id uuid null,
    terms_version text not null,
    privacy_version text not null,
    statement_version text not null,
    acceptance_method text not null check (
        acceptance_method in ('first_login', 'policy_update', 'organization_activation')
    ),
    environment text not null check (environment in ('production', 'trial', 'sandbox')),
    accepted_at timestamptz not null default now(),
    ip_address inet null,
    user_agent text null,
    created_by_user_id uuid null
);
```

Foreign keys should reference the projectâ€™s actual user and organization tables. Apply row-level security so ordinary users can read their own acceptance history but cannot alter or delete acceptance events. Only the trusted server path should insert events. DEV access should be auditable and should not permit silent modification of historical acceptance records.

## Application behavior

1. Authenticate the user.
2. Load the currently required Terms and Privacy versions from durable storage.
3. Check for a matching acceptance event for the authenticated user.
4. If none exists, render only the acceptance screen and sign-out control.
5. Insert the acceptance event through a trusted server operation after explicit acceptance.
6. Confirm the insert succeeded before granting application access.
7. Never treat a failed database write as acceptance.
8. Re-check required versions on each new authenticated session.
9. Keep policy documents reachable later from Account or Help.

## Accessibility and mobile behavior

- Use real links and a real checkbox with a visible label.
- Support keyboard navigation and visible focus states.
- Do not preselect agreement.
- Do not hide policy links inside expandable text.
- Keep the acceptance action visible on phone and tablet layouts without covering policy text.
- Announce validation and database errors using the applicationâ€™s accessible alert pattern.
- Preserve acceptance state if a user opens and returns from a policy link in the same session.

## Error copy

**Checkbox incomplete**

> Review and accept the Terms of Service and Privacy Policy to continue.

**Acceptance could not be stored**

> We could not securely record your acceptance. Your account has not been changed. Please try again or contact support.

**Policy unavailable**

> The current agreement is temporarily unavailable. Please try again shortly. Access will remain paused until the agreement can be reviewed.


