from __future__ import annotations

from pathlib import Path


def replace(path: str, old: str, new: str, *, expected: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    found = text.count(old)
    if found != expected:
        raise SystemExit(f"{path}: expected {expected} occurrence(s), found {found}: {old[:120]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# Extraction: memoize stage-owned output fields so the effect has a stable dependency.
replace(
    "frontend/src/pages/ExtractionPage.tsx",
    'const stages=detail.workflow.stages.filter(row=>showOptional||!row.optional||row.key===detail.run.current_stage_key);const selectedStage=detail.workflow.stages.find(row=>row.key===form.stage_key)??stages[0];const outputFields=selectedStage?.output_fields??[];const isFormulation=selectedStage?.key==="formulation";',
    'const stages=detail.workflow.stages.filter(row=>showOptional||!row.optional||row.key===detail.run.current_stage_key);const selectedStage=detail.workflow.stages.find(row=>row.key===form.stage_key)??stages[0];const outputFields=useMemo(()=>selectedStage?.output_fields??[],[selectedStage]);const isFormulation=selectedStage?.key==="formulation";',
)

# Admin: keep selected entities and derived arrays referentially stable and make effects
# depend on the actual values they read instead of compressed identifier strings.
replace(
    "frontend/src/pages/AdminToolsPage.tsx",
    '  const selected=facilities.find(row=>row.id===selectedId)??facilities[0];',
    '  const selected=useMemo(()=>facilities.find(row=>row.id===selectedId)??facilities[0],[facilities,selectedId]);',
)
replace(
    "frontend/src/pages/AdminToolsPage.tsx",
    '  },[selected?.id]);',
    '  },[selected,selectedId]);',
    expected=2,
)
replace(
    "frontend/src/pages/AdminToolsPage.tsx",
    '  const rows=storefronts.data??[];',
    '  const rows=useMemo(()=>storefronts.data??[],[storefronts.data]);',
)
replace(
    "frontend/src/pages/AdminToolsPage.tsx",
    '  const selected=rows.find(row=>row.id===selectedId)??rows[0];',
    '  const selected=useMemo(()=>rows.find(row=>row.id===selectedId)??rows[0],[rows,selectedId]);',
)
replace(
    "frontend/src/pages/AdminToolsPage.tsx",
    '  const targetFacilities=(targetOrganization?.facilities??[]).filter(facility=>facility.active!==false&&facility.commercial_enabled);',
    '  const targetFacilities=useMemo(()=>(targetOrganization?.facilities??[]).filter(facility=>facility.active!==false&&facility.commercial_enabled),[targetOrganization]);',
)
replace(
    "frontend/src/pages/AdminToolsPage.tsx",
    '  },[organizationId,targetFacilities.map(row=>row.id).join("|")]);',
    '  },[organizationId,targetFacilities,facilityId]);',
)
replace(
    "frontend/src/pages/AdminToolsPage.tsx",
    '  const rows = uploads.data?.uploads ?? [];',
    '  const rows = useMemo(() => uploads.data?.uploads ?? [], [uploads.data]);',
)

# Integration defaults are immutable product defaults, so keep them at module scope.
spacemail_defaults = '{ smtp_username: "nelson@doobielogic.io", from_email: "support@doobielogic.io", from_name: "DoobieLogic Support", support_email: "support@doobielogic.io", help_email: "help@doobielogic.io", info_email: "info@doobielogic.io", welcome_email_enabled: true, mailbox_password: "" }'
replace(
    "frontend/src/pages/IntegrationsPage.tsx",
    'function SpacemailCard({ value, onSaved }: { value: Integration; onSaved: () => void }) {',
    f'const SPACEMAIL_DEFAULTS = {spacemail_defaults};\n\nfunction SpacemailCard({{ value, onSaved }}: {{ value: Integration; onSaved: () => void }}) {{',
)
replace(
    "frontend/src/pages/IntegrationsPage.tsx",
    f'  const defaults = {spacemail_defaults};',
    '  const defaults = SPACEMAIL_DEFAULTS;',
)
# Keep the local alias explicit in the effect contract; this leaves future default-set
# changes visible to exhaustive-deps without duplicating six scalar dependencies.
integrations = Path("frontend/src/pages/IntegrationsPage.tsx")
text = integrations.read_text(encoding="utf-8")
start = text.index("function SpacemailCard")
end = text.index("function AIRuntimeCard", start)
block = text[start:end]
needle = '})), [value]);'
if block.count(needle) != 1:
    raise SystemExit(f"IntegrationsPage.tsx: expected one Spacemail [value] effect, found {block.count(needle)}")
block = block.replace(needle, '})), [value, defaults]);', 1)
integrations.write_text(text[:start] + block + text[end:], encoding="utf-8")

# Location Settings: the selected provider object is the source of truth read by each
# synchronization effect; depending on it prevents stale forms without dependency hacks.
replace(
    "frontend/src/pages/LocationSettingsPage.tsx",
    '  }, [selectedId, data]);',
    '  }, [selected]);',
    expected=3,
)

print("Applied P0-P2 frontend reactive hardening transformations.")
