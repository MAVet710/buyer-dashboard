"""Published in-app policy text and immutable version metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from services.legal_acceptance_store import PolicyDocument


TERMS_VERSION = "2026-08-1"
PRIVACY_VERSION = "2026-08-1"
STATEMENT_VERSION = "2026-08-1"
POLICY_EFFECTIVE_AT = datetime(2026, 8, 2, tzinfo=timezone.utc)

TERMS_TEXT = """
## DoobieLogic Terms of Service

**Effective August 2, 2026**

DoobieLogic is business-operations software for authorized users of regulated
cannabis organizations. You must be at least 21 years old, protect your account,
and use the service only for lawful business purposes.

Your organization remains responsible for its licenses, employees, products,
inventory, manufacturing, transfers, sales, taxes, records, and compliance with
all applicable requirements. DoobieLogic is not a regulator, legal adviser,
testing laboratory, METRC system of record, point-of-sale provider, or substitute
for required books and records.

Calculations, forecasts, equivalency values, nomenclature mappings, production
schedules, labor estimates, margin estimates, audit results, reports, and AI
output depend on customer data and assumptions. Qualified personnel must review
them before changing live inventory, production, packaging, labeling, purchasing,
point-of-sale, track-and-trace, financial, or compliance systems.

Customers retain their rights in uploaded catalogs, manifests, inventory,
production records, and other customer content. Customers authorize DoobieLogic
and its service providers to process that content only as needed to provide,
secure, support, and improve requested features. Customers must have permission
to submit the information and should not upload unnecessary sensitive personal
or patient information.

Third-party integrations, including METRC, Dutchie, Supabase, Streamlit, GitHub,
and configured AI providers, may be governed by separate terms. Their names do
not imply certification or endorsement. Sandbox and demonstration data may be
simulated, reset, or unsuitable for live decisions.

You may not access another organization without authorization, bypass security,
upload malicious content, interfere with the service, reverse engineer protected
components, resell unauthorized access, or use the service to evade legal or
regulatory duties.

The Service is provided **as is** and **as available** to the maximum extent
permitted by law. It may change, contain errors, or experience interruptions.
DoobieLogic may suspend access for security risks, unlawful use, material breach,
or nonpayment under a future paid agreement. Any paid plan, order form, or separately signed agreement may include additional
billing, warranty, liability, indemnification, governing-law, and dispute terms.
If a separate signed agreement conflicts with these Terms, that agreement controls
for the conflicting provision.
""".strip()

PRIVACY_TEXT = """
## DoobieLogic Privacy Policy

**Effective August 2, 2026**

DoobieLogic may process account details, organization and facility assignments,
authentication and security logs, accepted-policy versions, device and browser
information, operational uploads, catalogs, manifests, product identifiers,
inventory counts, purchasing information, schedules, production records,
machine and labor information, reports, support communications, and integration
data supplied by authorized users.

We use this information to authenticate users, enforce roles, provide requested
workflows, operate authorized integrations, create reports and calculations,
support customers, improve reliability, protect the service, and meet legal
obligations. Organization administrators may manage their users and view data
permitted within their organization. Restricted DoobieLogic DEV personnel may
access environments for support, security, maintenance, testing, and incident
response; elevated access should be limited and logged.

When an authorized user invokes an AI feature, necessary request information may
be sent to the configured AI provider. Users should exclude information that is
not needed for the task. DoobieLogic may rely on infrastructure and service
providers such as Supabase, Streamlit, GitHub, and OpenAI, depending on the
customer configuration.

We do not intend to sell personal information for money. Information may be
disclosed to service providers, enabled integrations, professional advisers,
successors in a business transaction, or authorities when legally required. A
production subprocessor list and final provider-specific retention disclosures
will be published before commercial launch.

Information is retained while needed to provide and secure the service, satisfy
customer instructions, resolve disputes, or comply with law. Active records may
be deleted or de-identified after verified closure or deletion requests, subject
to legal holds and ordinary encrypted-backup rotation.

We use reasonable safeguards such as access controls, password hashing,
organization-level separation, encrypted transport, logging, and restricted
administrative access. No system is completely secure. Customers remain
responsible for their devices, networks, credentials, permissions, exports, and
connected third-party systems.

The service is for business users age 21 or older and is not intended for
children, patients, consumer medical records, identity-document storage, or
payment-card storage. Privacy questions and verified access, correction, export,
or deletion requests will be handled through the support contact published with
the Service or the current published policy.
""".strip()


def _digest(document: str) -> str:
    return sha256(document.encode("utf-8")).hexdigest()


CURRENT_TERMS_POLICY = PolicyDocument(
    policy_type="terms",
    version=TERMS_VERSION,
    effective_at=POLICY_EFFECTIVE_AT,
    document_sha256=_digest(TERMS_TEXT),
    document_url="in-app://legal/terms",
)

CURRENT_PRIVACY_POLICY = PolicyDocument(
    policy_type="privacy",
    version=PRIVACY_VERSION,
    effective_at=POLICY_EFFECTIVE_AT,
    document_sha256=_digest(PRIVACY_TEXT),
    document_url="in-app://legal/privacy",
)


