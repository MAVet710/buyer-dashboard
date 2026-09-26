# Cultivation intelligence API contract v1

Prefix: `/api/v1/cultivation-intelligence`. This is the implementation contract for concurrent frontend work, not a release claim. JSON only, unknown fields rejected recursively. IDs are opaque strings; dates are ISO dates and timestamps require explicit UTC offsets. All scope comes from authenticated request context, never request bodies. GET paths never contact a provider. Lists are bounded to 200 (detail children to 200); `truncated` explicitly identifies incomplete results. Missing evidence is `null`, never a fabricated zero or healthy status.

Every response includes `can_manage` and `can_manage_connections` where returned by workspace/detail reads. Effective flags include cultivation capability, legacy cultivation write role and granular permission. Connections additionally require administrator (`admin` or `dev`). Errors: 403 permission, 404 scoped entity absent, 409 version/identity/interval conflict, 422 validation, 503 unavailable local edge store. Standard FastAPI `{detail: ...}` envelope. Writes return persisted objects, with `id` and `version` when versioned. No secrets appear in responses.

## Core shapes

`Cycle`: `{id, cycle_code, display_name, genetics_label, nursery_group_id:null|string, recipe_id:null|string, harvest_id:null|string, status, started_on:null|date, estimated_harvest_date:null|date, version}`.

`Room`: `{id, room_code, display_name, phase, active, plant_capacity}`. `Connection`: `{id, provider, label, mode, status, version, revoked_at:null|timestamp, live_supported:false}`. Fixture/import activity never implies live connection health.

`Recipe`: `{id,name,version,status,description,approved_by:null|string,approved_at:null|timestamp,stages:[{id,stage_key,display_name,sequence,targets:[{metric,minimum,maximum,unit,threshold_seconds,alert_threshold_status}]}]}`. Arbitrary facility stage names, no default agronomy. Targets require at least one bound and normalized registry units. Approved recipes are immutable; POST a new recipe version to change standards.

## Routes and exact request bodies

| Method/path | Request | Response |
|---|---|---|
| GET `/workspace` | none | `{rooms:Room[],cycles:Cycle[],connections:Connection[],recipes:Recipe[],truncated,can_manage,can_manage_connections,decision_support_only:true}` |
| GET `/rooms/{room_id}` | none | `{room:Room,plants:[{id,plant_tag,phase}],cycles:Cycle[],environment:legacyTelemetrySnapshot,edge_summary:null|object,events:[],work:[],costs:{total:null,allocation_status:"unknown"},truncated,can_manage,can_manage_connections}` |
| GET `/cycles/{cycle_id}` | none | `{cycle:Cycle,members:[],occupancy:[],harvest:null|object,economics:{allocated_cost:null|number,allocation_status,provenance:[]},events:[],lineage:[],truncated,can_manage,can_manage_connections}` |
| POST `/cycles` | `{cycle_code,display_name,genetics_label:"",nursery_group_id:null,recipe_id:null,started_on:null,estimated_harvest_date:null}` | Cycle |
| POST `/cycles/{id}/occupancy` | `{version,room_id,zone_id:null,stage_id:null,entered_at,exited_at:null}` | `{id,version}`; half-open interval, stage must belong to cycle's approved recipe; sequential stage intervals can share a room |
| POST `/cycles/{id}/members` | `{version,plant_ids:[],action:"add"|"remove",effective_at}` | `{id,version,changed}`; 1..200 unique canonical plants |
| POST `/cycles/{id}/harvest` | `{version,harvest_id}` | Cycle; exclusive complete canonical harvest membership required |
| GET `/recipes` | none | `{recipes:Recipe[],truncated}` |
| POST `/recipes` | `{name,description:"",stages:[{stage_key,display_name,sequence,targets:[{metric,minimum:null,maximum:null,unit,threshold_seconds:null}]}]}` | Recipe; server allocates next version |
| POST `/recipes/{id}/approve` | `{version}` | Recipe; authenticated AppUser approval |
| POST `/events` | `{room_id:null,cycle_id:null,event_type,title,notes:"",occurred_at}` | `{id}`; at least room or cycle required |
| GET `/plants/{id}/exposure` | none | `{plant_id,exposure_status:"unknown",intervals:[],reason,memberships:[],cohort_occupancy:[],relationships,truncated}`; current room alone does not prove historical exposure |
| GET `/metrics` | none | `{metrics:[{metric,unit,kind,aliases:[]}]}` |
| GET `/connections` | none | `{connections:Connection[],truncated}` |
| POST `/connections` | `{provider:"json"|"csv"|"growlink",label,mode:"file"}` | Connection; Growlink live contract remains blocked |
| POST `/connections/{id}/revoke` | `{version}` | Connection; disables subsequent ingestion and preserves evidence |
| GET `/connections/{id}/devices` | none | `{devices:[],truncated}` |
| POST `/connections/{id}/devices` | `{version,source_device_id,display_name:""}` | `{id,version}`; explicit registration, no live discovery |
| POST `/devices/{id}/mapping` | `{version,room_id,zone_id:null,effective_at}` | `{id,version}`; immutable time-effective mapping revision |
| POST `/devices/{id}/sensors` | `{version,source_channel,source_metric,source_unit,metric}` | `{id,version}`; explicit controlled metric mapping |
| POST `/connections/{id}/imports/preview` | `{format:"json"|"csv",content,mappings:[]}` | `{digest,rows,unknown_channels:[],conflicts:[],can_commit}` |
| POST `/connections/{id}/imports` | `{format:"json"|"csv",content,mappings:[],digest}` | `{accepted,duplicates,conflicts,queued_for_mapping}` |
| POST `/connections/{id}/drain` | `{limit:100}` (1..500) | `{processed,pending,conflicts}` |
| GET `/connections/{id}/health` | none | `{connection:Connection,edge:null|object,live_contract_status:"blocked"}` |

Import mapping item: `{source_channel,source_metric,metric,unit}`. Content is bounded to 1 MiB UTF-8, 500 rows per request. No browser filesystem paths, URLs, auth headers or arbitrary provider settings. Preview and commit are explicitly separate. The edge owner's `CULTIVATION_EDGE_CONTRACT.md` defines the local persistence implementation; final adapter row details and availability will be recorded here after integration. Connection/import routes must fail closed until that seam is implemented, never report fictitious success.

No equipment commands, automatic Work, plant moves, inventory consumption or Metrc calls. Canonical Work/harvest/cost/quality/material-lineage remain authoritative. Raw provider observations stay local by default. Existing manual observation routes remain compatible.

## Implemented integration details and additive routes

All minimum routes above are registered. The generic export format uses a JSON array or CSV with these exact column names: `event_id,source_device_id,source_channel,source_metric,value,unit,observed_at`. Unknown device/channel mappings stay pending. Preview returns row indices in `unknown_channels` and mapping conflicts in `conflicts`; `identity_conflict_check:"at_commit"` makes clear that durable identity conflicts are determined by the edge commit. Import `accepted` counts resolved ready observations; `queued_for_mapping` counts durable unresolved rows; `quarantined` is separate. Replays return duplicates without replacing source evidence.

Device and sensor mutation responses additionally include `connection_version`, and device creation includes the new connection version too. Mapping/sensor changes advance connection versions and invalidate preview digests. After a remap, preview the same content again; edge replay remains idempotent and never replaces stored snapshots or drops pending rows. `/drain` additionally returns `{rollup,raw_stays_local:true,cloud_publication:false}`. Pending count refers to rows examined in this bounded attempt; the health diagnostics supply total state counts. No cloud receiver acknowledgement is implied.

Additive POST `/rooms/{room_id}/zones`: `{zone_code,display_name:""}` returns `{id,room_id,zone_code,display_name,active}`. It requires connection administrator permission. Room360 additionally returns `zones` with these fields.

Additive POST `/cycles/{id}/occupancy/{occupancy_id}/close`: `{version,exited_at}` returns `{id,version}`. Close time must follow entry, be present/future, and cannot rewrite historical attribution. An already-closed interval conflicts. A subsequent occupancy interval can start at that exact half-open boundary, including a new stage in the same room.

Room360 adds `cycle_attribution_status:"assigned"|"unassigned"|"ambiguous"` for current occupancy. Persisted snapshots with null cycle IDs represent unassigned-or-ambiguous evidence at observation time and must not be labeled as proven plant exposure. Local room summary streams are capped at 200 with explicit truncation.

Cycle360 adds `edge_summary:{rooms:[{room_id,summary}],truncated,status:"UNKNOWN"}`. Each summary uses the edge contract and is filtered to the requested cycle over the previous 24 completed UTC hours. At most eight most recent occupied rooms are hydrated. The outer status makes no inferred health claim; inspect each stream's coverage/deviations. Economics additionally returns `true_cogs:null`; proven harvest costs are partial allocation, not total production COGS. Recursive genealogy and COA bodies remain detail-on-demand in their canonical workspaces; proven historical plant exposure remains an explicit integration limitation.

Historical legacy observations expose `original:{metric:null,value:null,unit:null,provenance:"unavailable_historical"}` until genuine source evidence exists. New manual evidence returns `provenance:"captured"`. Neither retries nor migrations fabricate originals.


Cycle360 also returns `post_harvest:null|{id,harvest_id,stage,location_code,started_at,completed_at}`, `lineage:[{id,transformation_type,source_entity_type,source_entity_id,status}]`, `lineage_outputs:[{id,transformation_id,lot_id,quantity,unit,measurement_basis}]` and `quality:[{lot_id,lab_testing_state,coa_document_id,evidence_source,verified_at}]`. These are bounded canonical references, not a new ledger, current inventory balances or invented test/grade values.

Room360 adds `approved_targets:[{cycle_id,recipe_id,recipe_version,stage_id,stage_key,metric,minimum,maximum,unit,threshold_seconds,alert_threshold_status}]` for current approved stage intervals. Room `costs` adds `recorded_total:null|number`, `recorded_entry_count`, `period:"all_recorded_room_entries"`, `provenance:"cultivation_cost_entries"`. This room ledger total does not allocate costs to cycles and does not establish true COGS.

Connection lists and health add `last_import_at:null|timestamp`, derived in a grouped query from canonical count-only import audit events. Health adds `freshness:{basis:"local_import_and_scoped_edge_evidence",last_import_at,last_received_at,last_valid_observed_at,sensor_freshness_status:"unknown",last_provider_contact_at:null,live_connected:false}`. A recent file import is not evidence of a live provider or fresh sensor measurement; measured coverage remains in edge summaries.

## Final integration additive contract

Recipe target input/output adds `threshold_seconds:null|integer` (1..2678400). Null means `alert_threshold_status:"not_configured"`; band duration is still measured, but no threshold-qualified alert is reported. Configured thresholds measure each continuous same-direction excursion, never accumulated disconnected excursions. Gaps, stage and semantic-context changes break continuity. All approved versions and raw snapshots retain their original threshold.

Workspace Room summaries add `plant_count` (canonical active plants), `current_cycle_ids:[]`, `current_stages:[{cycle_id,stage_id,stage_key,display_name}]`, `current_stage:null|{cycle_id,stage_id,stage_key,display_name}`, and `context_truncated`. Singular stage is populated only for one provable active occupancy with a known stage. Global `truncated` also covers context limits.

GET `/rooms/{room_id}/zones` returns `{zones:[{id,room_id,zone_code,display_name,active}],truncated}`. GET `/devices/{id}/mapping` returns `{mappings:[{id,device_id,room_id,zone_id,effective_at}],truncated}` newest first. GET `/devices/{id}/sensors` returns `{sensors:[{id,device_id,source_channel,source_metric,source_unit,metric,unit}],truncated}`. Each child list is capped at 200. Device lists remain bounded and child details load on demand.

Preview returns `context_fingerprint` and binds its digest to the resolved snapshots for the exact input rows from one bounded resolver load. Commit re-resolves under the facility write lock before any edge write; changed temporal attribution requires another preview. Equivalent retries retain the original local evidence.

GET Room360 and Cycle360 accept optional paired `start`/`end` UTC aligned timestamps for historical aggregate reads. Default remains the previous 24 completed UTC hours. Cycle360 adds `approved_recipe:null|Recipe` for its exact immutable recipe, including all stage targets. Summary streams add `alert_threshold_status` and `threshold_semantics:"continuous_same_direction"`. Missing thresholds suppress alert intervals, while measured band durations and UNKNOWN gaps remain visible.

GET Plant360 exposure adds `memberships:[{id,cycle_id,added_at,removed_at,cycle_url}]`, `cohort_occupancy:[{id,cycle_id,room_id,zone_id,stage_id,entered_at,exited_at,room_url,cycle_url,evidence_basis:"cycle_occupancy_not_individual_movement"}]`, `relationships:{mother_plant_tag,mother_plant_id,group_ids:[],harvest_ids:[]}`, `truncated`. These are canonical relationship references, not individual exposure intervals. `exposure_status` stays unknown until canonical movement evidence proves individual intervals.

Administrator maintenance: POST `/connections/{id}/rollup` with `{start,end}` runs an explicit bounded local rollup. GET `/connections/{id}/maintenance` returns configured limits, scoped diagnostics and the retention blocker. GET `/connections/{id}/evidence?limit=100&after=...` returns the scoped local raw evidence page for administrators only, with no central audit copy. POST `/connections/{id}/retention` accepts `{before,limit:100,execute:false}`. Preview is conservative and nonmutating, execution calls the edge prerequisite checks. Rollup and retention never acknowledge aggregates; the separate explicit archive action below acknowledges only verified durable revisions. Unacknowledged evidence stays protected. No automatic service or task is installed.

Maintenance configuration names and caps are in `CULTIVATION_INTELLIGENCE_ARCHITECTURE.md`. Room360/Cycle360 also return `connection_freshness:{connections:[{connection_id,connection_url,last_import_at,last_received_at,last_valid_observed_at,counts,live_connected:false,sensor_freshness_status:"unknown",basis:"connection_scope_not_room_condition"}],truncated}` (maximum eight). Health `freshness` has the three separate timestamps plus `last_provider_contact_at:null`, `live_connected:false`, and `sensor_freshness_status:"unknown"`. A historical valid observation imported today is not current sensor proof.

Import commit adds `dispositions:[{identity,status,reason}]` for at most 500 input rows; reasons are fixed safe edge codes, with no raw provider body. Quarantine is separately counted. Central import audit contains counts only.

Retention preview returns `{executed:false,purged:0,eligible:null,preview_basis:"edge_prerequisites_checked_on_execution",blocker:"durable_aggregate_receiver_not_configured",edge}`. Execution returns `{purged,protected,truncated,executed:true,blocker,receiver_acknowledged:false}`. No caller-supplied acknowledgement endpoint exists. The archive action performs exact acknowledgement only after the verified local receiver accepts a revision. Local quotas can fill even after retention because aggregate evidence and identity tombstones are preserved.

Room360 `canonical_links` is `{self,work:[{id,url}],cycles:[{id,url}]}`. Cycle360 `canonical_links` is `{self,rooms:[{id,url}],harvest:null|string,plants:[{id,url}]}`. These are actual existing API detail URLs; plant links resolve the canonical lineage endpoint. Occupancy detail retains the latest 200 intervals in chronological order with explicit truncation. Recipe approval is also a temporal boundary: a pre-approval snapshot cannot carry an unconfigured target context past that approval time.

POST `/connections/{id}/archive` accepts only `{limit:100}` (1..500 and configured edge bounds), requires connection administrator authorization, and returns `{archived,acknowledged,stale,truncated,raw_stays_local:true,cloud_publication:false}`. Configure a pre-created absolute local `CULTIVATION_EDGE_ARCHIVE_DIR` on the host. An absent setting returns 503. Request bodies cannot choose a path. Each acknowledged revision has passed the edge receiver scope/hash/generation validation, durable immutable publication and verified readback. This endpoint does not purge raw evidence. Maintenance adds `archive_configured`; when configured, its retention prerequisite code is `requires_clean_verified_archive_and_resolved_evidence`. Retention execution returns `blocker:null` when no examined rows are protected. Its `receiver_acknowledged:false` means retention itself creates no acknowledgement.


## Final primary integration corrections

JSON/CSV optional `quality` and `received_at` columns are preserved when present. Only an absent quality field defaults to `valid`; explicit invalid, suspect or null quality never becomes a valid sample. Malformed export syntax returns a fixed safe HTTP 422 message without echoing content.

Room360 adds `edge_latest:null|{as_of,readings,truncated,status}` from the scoped local current-reading projection. It is independent of the canonical manual `environment.readings` and historical aggregate window. Current imported readings are displayed in Latest sensor readings; stale or invalid current evidence never falls back to a prior healthy value.

POST `/connections/{id}/archive` accepts `{limit:100}` and uses only host-owned `CULTIVATION_EDGE_ARCHIVE_DIR`. It returns verified archived/acknowledged/stale revision counts and truncation. No raw cloud publication or browser filesystem path is supported. Retention is a separate explicit operation and still protects unresolved, disputed, dirty and unacknowledged evidence.

Recipe drafts serialize only the allowed input fields, excluding derived `alert_threshold_status` and immutable response IDs. PostgreSQL child-writer triggers lock the parent recipe before checking approval so concurrent approval and insertion serialize without broadening grants.
