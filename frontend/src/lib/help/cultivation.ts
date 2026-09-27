import type { HelpWalkthroughRegistry } from './types';
export const cultivationWalkthroughs: HelpWalkthroughRegistry = {
  "/help/cultivation": {
    "title": "Cultivation: review rooms, record plant work, and plan a harvest",
    "category": "cultivation",
    "summary": "Find the right plants, check room capacity, record an individual or bulk change, and prepare a local harvest handoff.",
    "navPath": "Cultivation",
    "appPath": "/cultivation",
    "beforeYouStart": [
      "Check that you're working in the intended facility. Plant tags, rooms, and harvests are facility-specific.",
      "Have the plant tags and actual room or phase change ready. A planned harvest and an estimated harvest date don't prove that harvesting has happened.",
      "Write controls depend on your role. A provider-linked plant may also require a regulated action instead of a local change."
    ],
    "steps": [
      {
        "id": "review-grow-work",
        "title": "Review the room and plant summaries",
        "instructions": [
          "Open Cultivation. Use the Cultivation command panel to identify the room, then scroll to Rooms, Harvests & Cost.",
          "Check Room Capacity for plant count, configured capacity, phase mismatch, and Next harvest. A room shown as unbounded has no configured capacity limit; it isn't evidence of unlimited physical space.",
          "Use Open Room 360 for room evidence. The room row in Room Capacity opens the room editor when you have write access."
        ],
        "expected": "You can identify the intended room and any capacity or phase warnings before recording work."
      },
      {
        "id": "configure-room",
        "title": "Add a room when it doesn't already exist",
        "instructions": [
          "In Rooms, Harvests & Cost, select Add room. Check existing room codes first so you don't create a second record for the same physical room.",
          "Enter the room details and select Save room. To update an existing room, select its Room Capacity row; its Room code cannot be edited."
        ],
        "fields": [
          {
            "label": "Room code",
            "requirement": "Required.",
            "guidance": "Use the facility's existing room identifier.",
            "example": "ROOM-DEMO-1"
          },
          {
            "label": "Display name",
            "requirement": "Optional.",
            "guidance": "Enter the name operators recognize."
          },
          {
            "label": "Expected phase",
            "requirement": "Choose a phase or Any phase.",
            "guidance": "This supplies room phase expectations for mismatch review."
          },
          {
            "label": "Plant capacity",
            "requirement": "Nonnegative number.",
            "guidance": "Enter the configured plant limit; zero displays as unbounded."
          },
          {
            "label": "Square feet",
            "requirement": "Nonnegative number.",
            "guidance": "Enter the recorded room area in square feet."
          },
          {
            "label": "Target cycle days",
            "requirement": "Nonnegative number.",
            "guidance": "Enter the facility's planning value, not a promised completion date."
          },
          {
            "label": "Active room",
            "requirement": "Checkbox.",
            "guidance": "Leave checked for a room available for active operations."
          },
          {
            "label": "Notes",
            "requirement": "Optional.",
            "guidance": "Explain room-specific operating context."
          }
        ],
        "expected": "The editor closes after a successful save and Room Capacity refreshes."
      },
      {
        "id": "find-plant",
        "title": "Find and open the exact plant",
        "instructions": [
          "Scroll to the plant table. Use the search input with the Search tag, strain, room placeholder, All phases, and All rooms to narrow the list.",
          "Select a plant row to open Plant 360. Check the tag, strain, phase, room, Plant lineage, and Lifecycle history before changing anything.",
          "Changing a table filter clears the bulk selection. Recheck the selected count before any bulk action."
        ],
        "expected": "Plant 360 shows the selected tag and its recorded history, or the page explains that the requested plant isn't available in this facility."
      },
      {
        "id": "add-individual-plant",
        "title": "Record an individual plant only when needed",
        "instructions": [
          "For an individual tag or exception, select Add one plant. For a nursery batch, use New plant group in Work plants in batches instead.",
          "Fill in the individual record and select Save plant. This records the plant locally; it doesn't establish provider acceptance."
        ],
        "fields": [
          {
            "label": "Plant tag",
            "requirement": "Required and unique in the active facility.",
            "guidance": "Use the actual tag being recorded.",
            "example": "DEMO-PLANT-001"
          },
          {
            "label": "Strain",
            "requirement": "Required.",
            "guidance": "Use the facility's recorded strain name."
          },
          {
            "label": "Phase",
            "requirement": "Selection required.",
            "guidance": "Choose the plant's actual current phase."
          },
          {
            "label": "Room",
            "requirement": "Defaults to UNASSIGNED.",
            "guidance": "Enter the intended room code; don't guess a destination."
          },
          {
            "label": "Legacy mother tag",
            "requirement": "Optional.",
            "guidance": "This is a legacy text reference, not proof of a linked mother record."
          },
          {
            "label": "Planted date",
            "requirement": "Optional date.",
            "guidance": "Enter the known planting date."
          },
          {
            "label": "Estimated harvest",
            "requirement": "Optional date.",
            "guidance": "Enter a planning estimate only."
          },
          {
            "label": "Notes",
            "requirement": "Optional.",
            "guidance": "Explain why the individual record is being added."
          }
        ],
        "expected": "The dialog closes and the plant list refreshes after the save succeeds."
      },
      {
        "id": "record-individual-change",
        "title": "Record a plant's local change",
        "instructions": [
          "In Plant 360, choose Next phase or No phase change, review Room, and explain the change in Reason.",
          "Check the destination and phase before selecting Record change. If a provider guard blocks the operation, resolve the required regulated workflow instead of trying another local form.",
          "After success, check the updated phase and room in the window. Reopen the plant to review its refreshed Lifecycle history."
        ],
        "fields": [
          {
            "label": "Next phase",
            "requirement": "Choose a permitted next phase or No phase change.",
            "guidance": "Only the transitions offered for this plant are available."
          },
          {
            "label": "Room",
            "requirement": "Review before saving.",
            "guidance": "Keep the current code unless the plant actually moved."
          },
          {
            "label": "Reason",
            "requirement": "Supply the operational reason.",
            "guidance": "Describe what happened so the next operator can understand the record."
          }
        ],
        "warning": "Harvested and destroyed plants have no further phase transitions in this form. Don't use either state to clear a list or correct an unrelated error.",
        "expected": "The plant header reflects the saved local change. This alone does not confirm a Metrc write."
      },
      {
        "id": "apply-bulk-change",
        "title": "Move a reviewed selection together",
        "instructions": [
          "Close Plant 360 and select the checkboxes for the intended plants, or Select all visible plants. Select Move / change phase.",
          "Review the selection table, choose New phase and/or Destination room, and enter Reason and Notes. Keep current phase or Keep current room leaves that part unchanged.",
          "Select Validate and apply to all. The app checks the selection together; a failed plant, room, or capacity check prevents the entire change."
        ],
        "fields": [
          {
            "label": "New phase",
            "requirement": "Required only if changing phase.",
            "guidance": "Choose one phase that is valid for every selected plant."
          },
          {
            "label": "Destination room",
            "requirement": "Required only if changing room.",
            "guidance": "Choose an active room and check its displayed capacity."
          },
          {
            "label": "Reason",
            "requirement": "Explain the change.",
            "guidance": "Describe why this whole selection is moving."
          },
          {
            "label": "Notes",
            "requirement": "Optional.",
            "guidance": "Record additional shift context."
          }
        ],
        "warning": "Review all selected plants, including any beyond the first 100 shown in the dialog. The action applies to the entire selection.",
        "expected": "A success banner reports how many selected plants changed, the dialog closes, and the selection clears."
      },
      {
        "id": "plan-harvest-handoff",
        "title": "Plan the harvest and review the handoff",
        "instructions": [
          "In Rooms, Harvests & Cost, select Plan harvest. Enter Harvest code and optional Notes, then check the flowering plants that belong in this harvest.",
          "Select Create harvest. In Harvest 360, verify Assigned plants and the harvest status. Creating this record plans the harvest locally; it does not submit a Metrc harvest.",
          "Use the actual harvest execution controls available for the facility before expecting a Post-Harvest job. Open Post-Harvest to review eligible open harvests and continue the physical handoff."
        ],
        "fields": [
          {
            "label": "Harvest code",
            "requirement": "Required and unique in the active facility.",
            "guidance": "Use the facility's harvest identifier.",
            "example": "HARV-DEMO-001"
          },
          {
            "label": "Notes",
            "requirement": "Optional.",
            "guidance": "Explain the planned grouping or handoff context."
          }
        ],
        "expected": "Harvest 360 opens with the selected plants. The Harvest Queue shows the saved harvest and its current status."
      }
    ],
    "completion": [
      "The plant list and room summaries reflect the records you saved.",
      "A planned harvest is visible in Harvest Queue with the intended plants; provider acceptance and physical execution are separate checks."
    ],
    "troubleshooting": [
      {
        "symptom": "A bulk move fails for the whole selection.",
        "resolution": "Read the validation error, check each plant's current phase and the destination room's capacity, and remove unintended selections. Don't split a blocked provider-linked operation into local writes to bypass the guard."
      },
      {
        "symptom": "No flowering plants are available for a harvest, or a plant is already assigned.",
        "resolution": "Check the plant's phase and existing open harvests. Only flowering plants can be assigned, and a plant cannot belong to another open harvest."
      },
      {
        "symptom": "A save result is uncertain.",
        "resolution": "Reopen the exact plant or harvest and review its status and history before submitting again. Don't create a replacement record merely because the first response was lost."
      }
    ],
    "sourceFiles": [
      "frontend/src/App.tsx",
      "frontend/src/lib/workspaceRoutes.ts",
      "frontend/src/pages/CultivationOpsPage.tsx",
      "frontend/src/components/PlantInventory.tsx",
      "frontend/src/components/CultivationOperationsControl.tsx",
      "frontend/src/components/CultivationBatchManager.tsx",
      "backend/app/routers/plants.py",
      "modules/cultivation/service.py",
      "modules/cultivation/bulk.py"
    ]
  },
  "/help/cultivation/post-harvest": {
    "title": "Post-Harvest: record weights and hand off the next stage",
    "category": "cultivation",
    "summary": "Append measured weights, check remaining material, and move a harvest through the physical work stages without overwriting earlier readings.",
    "navPath": "Post-Harvest",
    "appPath": "/cultivation/post-harvest",
    "beforeYouStart": [
      "Confirm the active facility and harvest code, and have measured weights in grams ready.",
      "Eligible active or drying harvests are synchronized into this board when a user with write access opens it. A planned harvest alone is not a post-harvest job.",
      "Ready is an operational stage. It doesn't create inventory, record a laboratory result, or establish regulatory release."
    ],
    "steps": [
      {
        "id": "locate-post-harvest-job",
        "title": "Find the correct harvest card",
        "instructions": [
          "Open Post-Harvest and start with All. Match the harvest code, strain, and location to the physical material.",
          "Use Needs Attention or a stage filter to narrow the board. Read the card's attention reason, Wet and Dry weights, and recorded weight event count before entering new readings."
        ],
        "expected": "The card shows the intended harvest, its current stage, Flower, Trim, and Remaining / WIP."
      },
      {
        "id": "inspect-weight-history",
        "title": "Review the last recorded weights",
        "instructions": [
          "Select Update weights on the harvest card. Check the harvest code at the top and the calculated remaining/WIP value.",
          "Expand Audit history to compare previous readings, their stage, actor, and note. The table shows up to 20 readings and displays times in your browser's local format.",
          "The fields represent current totals for each weight type, not quantities to add to the previous total."
        ],
        "expected": "The dialog displays the current weights alongside the previous recorded readings."
      },
      {
        "id": "enter-measured-weights",
        "title": "Enter the current scale readings",
        "instructions": [
          "Change only the weight types you've measured. Enter nonnegative grams; don't enter pounds or ounces into a grams field.",
          "Leaving a field blank sends no reading for that type. Enter zero explicitly when a previously nonzero current amount is now zero.",
          "Add the container reference and a short shift note so another operator can place the reading in context."
        ],
        "fields": [
          {
            "label": "Remaining / WIP (g)",
            "requirement": "Optional changed measurement.",
            "guidance": "Enter measured material still in process. The calculated placeholder is not a saved scale reading."
          },
          {
            "label": "Finished flower (g)",
            "requirement": "Optional changed measurement.",
            "guidance": "Enter the current total finished flower weight in grams."
          },
          {
            "label": "Trim (g)",
            "requirement": "Optional changed measurement.",
            "guidance": "Enter the current trim total in grams."
          },
          {
            "label": "Biomass (g)",
            "requirement": "Optional changed measurement.",
            "guidance": "Enter the current biomass total in grams."
          },
          {
            "label": "Waste (g)",
            "requirement": "Optional changed measurement.",
            "guidance": "Enter the current measured waste total in grams."
          },
          {
            "label": "Container / bin",
            "requirement": "Optional.",
            "guidance": "Identify the material's container.",
            "example": "DEMO-BIN-12"
          },
          {
            "label": "Shift note",
            "requirement": "Optional.",
            "guidance": "Explain when and why this measurement was taken."
          }
        ],
        "expected": "Save weight update becomes available when at least one entered value differs from its recorded total."
      },
      {
        "id": "save-weight-readings",
        "title": "Save and check the weight update",
        "instructions": [
          "Review the units and changed totals, then select Save weight update once.",
          "After the dialog closes, check the card's totals and recorded weight event count. Reopen Update weights and Audit history if you need to confirm the readings.",
          "The save appends readings and keeps earlier values. It doesn't submit a Metrc mutation."
        ],
        "expected": "The card refreshes with the latest totals and additional weight events for changed types."
      },
      {
        "id": "advance-physical-stage",
        "title": "Hand off to the next physical stage",
        "instructions": [
          "Select Advance stage only when the next physical job is ready. Read the dialog title to confirm the proposed destination stage.",
          "Enter Current location / room and an optional Handoff note. Select the displayed Move to button for that stage.",
          "The sequence is Harvested, Drying, Ready for Trim / Bucking, Trimming, Curing, Testing / Hold, then Ready. The board advances one stage at a time."
        ],
        "fields": [
          {
            "label": "Current location / room",
            "requirement": "Optional; review the prefilled value.",
            "guidance": "Enter the physical destination code. A blank value does not clear an existing location.",
            "example": "DEMO-TRIM-1"
          },
          {
            "label": "Handoff note",
            "requirement": "Optional.",
            "guidance": "Tell the next team what work is complete and what needs attention."
          }
        ],
        "warning": "Stage changes move forward. Confirm the destination before saving; this dialog has no reverse-stage action.",
        "expected": "The card shows the new stage and supplied location. Under a stage filter, it may leave the current view."
      },
      {
        "id": "review-ready-lock",
        "title": "Check the final operational stage",
        "instructions": [
          "Before moving from Testing / Hold to Ready, review the physical output weights and any outstanding attention reason.",
          "The final move requires supervisor, QA, or administrator access, a recorded positive dry harvest weight, and flower, trim, biomass, and waste totals that reconcile to dry weight within 1 g. Record final measured WIP as 0 g; the server blocks remaining WIP above 1 g. Being in Testing / Hold does not itself record test results.",
          "After Move to Ready succeeds, look under Ready. Ordinary Update weights is replaced by Correct locked weights for users allowed to correct the locked batch."
        ],
        "warning": "Ready locks ordinary weight entry. It does not prove testing approval or release material into inventory.",
        "expected": "The harvest card appears under Ready with its recorded weights."
      },
      {
        "id": "correct-locked-reading",
        "title": "Append a documented correction if a locked weight is wrong",
        "instructions": [
          "If you have the required access, select Correct locked weights. Compare Audit history with the corrected scale record before changing a value.",
          "Enter the corrected current totals and Correction reason. Locked corrections must still reconcile outputs to dry weight within 1 g and cannot leave WIP above 1 g. Then select Append governed correction. This is the exact button label; it appends a correction rather than replacing history."
        ],
        "fields": [
          {
            "label": "Correction reason",
            "requirement": "Required for a Ready batch.",
            "guidance": "Explain the error and the basis for the corrected reading."
          }
        ],
        "expected": "The card refreshes, and Audit history retains both the original reading and the correction reason."
      }
    ],
    "completion": [
      "The harvest card shows the intended stage, location, and latest measured totals.",
      "Audit history contains the saved readings or corrections. Inventory creation and regulatory release remain separate workflows."
    ],
    "troubleshooting": [
      {
        "symptom": "The harvest doesn't appear on the board.",
        "resolution": "Select All and verify the facility. Check whether the source harvest is active or drying rather than merely planned. If the synchronization warning appears, resolve that error before assuming the job was created."
      },
      {
        "symptom": "Save weight update is disabled.",
        "resolution": "Enter at least one changed numeric value. Blank or unchanged values don't create events. On a locked batch, use an authorized correction and supply Correction reason."
      },
      {
        "symptom": "Move to Ready fails or isn't available.",
        "resolution": "Check supervisor, QA, or administrator access, the source harvest dry weight, output reconciliation within 1 g, and final WIP. Review the error and actual measurements; don't enter invented weights to satisfy the check."
      }
    ],
    "sourceFiles": [
      "frontend/src/pages/PostHarvestPage.tsx",
      "frontend/src/components/PostHarvestBoard.tsx",
      "backend/app/routers/production_mutations.py",
      "modules/cultivation/post_harvest.py"
    ]
  },
  "/help/cultivation/room-360": {
    "title": "Room 360: read current conditions and historical coverage",
    "category": "cultivation",
    "summary": "Review a room's plants, imported sensor readings, historical coverage, approved targets, and operational evidence without confusing missing data with healthy conditions.",
    "navPath": "Cultivation > Cultivation command panel > Open Room 360",
    "appPath": "/cultivation",
    "beforeYouStart": [
      "Know the room you're reviewing and confirm the active facility.",
      "Imported sensor evidence, manual observations, and historical aggregates are separate sources. An import timestamp does not establish current room conditions.",
      "Targets support review only. None of these controls operate equipment."
    ],
    "steps": [
      {
        "id": "open-room-context",
        "title": "Open and verify the room",
        "instructions": [
          "In the Cultivation command panel, select Open Room 360 on the intended room card.",
          "On Crop, check Canonical plants and Crop cycles and recipes. These are the app's linked records. Current room assignment alone does not establish historical cycle membership.",
          "If the window says the view is bounded or incomplete, treat missing records as unknown rather than absent."
        ],
        "expected": "The window heading matches the room and Crop shows its available plant and cycle links."
      },
      {
        "id": "read-latest-sensors",
        "title": "Inspect each sensor source separately",
        "instructions": [
          "Select Environment and read Latest sensor readings. Sources are grouped into Environment, Root zone, Irrigation, and Other measurements.",
          "Open Reading details for a measurement. Compare Observed with Received locally, then check age, receipt latency, source device/channel, zone, mapping interval, and recipe revision.",
          "A displayed value must be ready and fresh. Stale or unusable evidence displays Unknown. Target unknown means a target comparison isn't established, even if a reading is present."
        ],
        "expected": "Each available source shows its value and unit or an explicit unknown state, with source details you can inspect."
      },
      {
        "id": "choose-room-history-window",
        "title": "Read a specific historical window",
        "instructions": [
          "Expand Historical aggregate window. Enter Start (UTC hour) and End (UTC hour) at exact UTC hour boundaries ending in Z.",
          "Select Read dated aggregates. The end must be later than the start and no more than 31 days later. Use default window returns to the previous 24 completed UTC hours.",
          "This reads stored aggregates. It does not import missing readings or build missing summaries."
        ],
        "fields": [
          {
            "label": "Start (UTC hour)",
            "requirement": "Required for a custom window.",
            "guidance": "Enter the start at a whole UTC hour.",
            "example": "2026-09-24T00:00:00Z"
          },
          {
            "label": "End (UTC hour)",
            "requirement": "Required for a custom window.",
            "guidance": "Enter a later whole UTC hour within 31 days.",
            "example": "2026-09-25T00:00:00Z"
          }
        ],
        "expected": "Coverage and deterministic deviations reports the selected window or explains that persisted coverage is unavailable."
      },
      {
        "id": "inspect-coverage-deviations",
        "title": "Check coverage before interpreting deviations",
        "instructions": [
          "Expand a measurement under Coverage and deterministic deviations. Review Coverage seconds, Unknown seconds, and attribution intervals before using its mean or totals.",
          "For PPFD, Measured DLI contribution covers only the evidenced interval; partial coverage is not extrapolated into a full-day value. Event, duration, and volume totals describe recorded observations, not estimated delivery between them.",
          "Above and below target seconds require a recorded recipe revision. Cumulative out-of-target time differs from a continuous deviation episode; gaps break continuity. No listed episodes does not prove complete in-target coverage."
        ],
        "expected": "You can distinguish measured coverage, unknown intervals, and any threshold-qualified deviations for the selected source."
      },
      {
        "id": "compare-targets-observations",
        "title": "Compare approved targets with manual observations",
        "instructions": [
          "Read Current approved setpoint targets, including the unit, recipe version, and continuous deviation threshold.",
          "Review Manual environment observations separately. These entries don't establish that a device is connected or that imported sensor coverage is complete.",
          "Connection evidence clocks describe the connection only. Don't use last import or last receipt as the room's sensor freshness."
        ],
        "expected": "The window shows the available target and manual-observation evidence, including explicit missing-data messages."
      },
      {
        "id": "review-room-operations",
        "title": "Review room events, zones, work, and costs",
        "instructions": [
          "Select Operations. Review Zones, Events, and linked Work. Select a Work title to open its recorded task.",
          "Recorded costs summarize room entries; they aren't allocated cycle costs or proof of true cost of goods, grade, or revenue.",
          "If you manage connections and need a physical sub-area for sensor placement, enter Zone code and optional Zone name under Create zone, then select Create zone. The zone belongs to this room."
        ],
        "fields": [
          {
            "label": "Zone code",
            "requirement": "Required when creating a zone.",
            "guidance": "Use the facility's identifier for this room's sub-area.",
            "example": "DEMO-BENCH-A"
          },
          {
            "label": "Zone name",
            "requirement": "Optional.",
            "guidance": "Use a name operators recognize when mapping sensors."
          }
        ],
        "expected": "Existing evidence remains visible; a successful zone creation shows Saved and refreshes the zone list."
      },
      {
        "id": "record-room-event",
        "title": "Record an operational event when needed",
        "instructions": [
          "In Operations, use Record operational event if it's available to your account. Enter what happened and its actual timestamp with a timezone.",
          "Select Save event once and check Saved plus the refreshed Events list. Use Record another event only for a separate occurrence."
        ],
        "fields": [
          {
            "label": "Event type",
            "requirement": "Required, up to 80 characters.",
            "guidance": "Use your facility's event category.",
            "example": "inspection"
          },
          {
            "label": "Title",
            "requirement": "Required.",
            "guidance": "Summarize the actual event.",
            "example": "Room inspection recorded"
          },
          {
            "label": "Occurred at (ISO with timezone)",
            "requirement": "Required.",
            "guidance": "Replace the default if the event occurred earlier; include Z or a numeric offset.",
            "example": "2026-09-25T09:00:00-04:00"
          },
          {
            "label": "Notes",
            "requirement": "Optional.",
            "guidance": "Add factual context for the next operator."
          }
        ],
        "expected": "Saved appears and Events includes the recorded title. No equipment command or automatic Work task is created."
      }
    ],
    "completion": [
      "The selected room, time window, sources, and gaps are identifiable in the window.",
      "Any zone or event you saved appears in Operations with a success indication."
    ],
    "troubleshooting": [
      {
        "symptom": "No mapped sensor readings appear, or current values are Unknown.",
        "resolution": "Check the connection's device, channel, room mapping, and effective timestamp. Review stale state and observation age. Missing or stale evidence cannot be fixed by changing targets."
      },
      {
        "symptom": "Historical results are empty even though the latest reading exists.",
        "resolution": "Confirm the UTC window and whether local aggregates have been built for that interval. Latest readings and stored aggregates are separate views; ask the connection administrator to inspect local maintenance."
      },
      {
        "symptom": "Save reports a version or load conflict.",
        "resolution": "Use Reload current evidence, review the latest record, and verify whether your event already appears before submitting again."
      }
    ],
    "sourceFiles": [
      "frontend/src/components/Room360.tsx",
      "frontend/src/components/CurrentRoomConditions.tsx",
      "frontend/src/components/CultivationIntelligenceShared.tsx",
      "frontend/src/components/cultivationIntelligenceTypes.ts",
      "modules/cultivation/intelligence_service.py",
      "modules/cultivation/gateway.py",
      "backend/app/routers/cultivation_intelligence_workspace.py"
    ]
  },
  "/help/cultivation/environment": {
    "title": "Room environment: record an observation and review follow-up",
    "category": "cultivation",
    "summary": "Save a manual measurement in its displayed unit, configure a room review range, and explicitly create Work for an environmental exception.",
    "navPath": "Cultivation > Room environment",
    "appPath": "/cultivation",
    "beforeYouStart": [
      "Have the actual measurement, observation time, and source identifier ready.",
      "Use facility-approved ranges. This guide explains data entry, not growing targets.",
      "Manual observations don't connect equipment. Room targets here are separate from approved recipe versions in Room 360."
    ],
    "steps": [
      {
        "id": "select-environment-room",
        "title": "Choose the room before entering evidence",
        "instructions": [
          "Scroll to Room environment and select Environment room. Check the name even if a room was selected automatically.",
          "Review the As of time and Measurement / source rows. Latest observation, State, Past 24 hours, Target, and Follow-up describe each source separately."
        ],
        "fields": [
          {
            "label": "Environment room",
            "requirement": "Required selection.",
            "guidance": "Choose the room where the measurement was taken."
          }
        ],
        "expected": "The table loads observations for the selected room."
      },
      {
        "id": "enter-manual-observation",
        "title": "Enter the measurement and its actual time",
        "instructions": [
          "Expand Record an observation or configure targets and use Manual observation.",
          "Choose Measurement first, then enter the number in the unit shown by Value. For Temperature, the label is Value (C); changing the measurement changes the unit.",
          "Enter Observed at (ISO timestamp with timezone), choose Quality, and add Device ID (optional) if it identifies the source. Use Suspect or Invalid when the observation shouldn't count as valid evidence."
        ],
        "fields": [
          {
            "label": "Measurement",
            "requirement": "Required selection.",
            "guidance": "Choose the measured quantity, such as Temperature (C) or Irrigation volume (L)."
          },
          {
            "label": "Value (C)",
            "requirement": "Required when Temperature is selected; the unit changes with Measurement.",
            "guidance": "Enter the measured number in the displayed unit, not a target or estimate."
          },
          {
            "label": "Observed at (ISO timestamp with timezone)",
            "requirement": "Required and not in the future.",
            "guidance": "Use the time the observation occurred, including Z or an offset.",
            "example": "2026-09-25T08:00:00-04:00"
          },
          {
            "label": "Device ID (optional)",
            "requirement": "Optional, up to 120 characters.",
            "guidance": "Identify the instrument or source consistently."
          },
          {
            "label": "Quality",
            "requirement": "Choose Valid, Suspect, or Invalid.",
            "guidance": "Reflect your evidence quality rather than choosing Valid just to populate a trend."
          }
        ],
        "expected": "The form contains the selected measurement, value, timestamp, and quality, ready for review."
      },
      {
        "id": "save-manual-observation",
        "title": "Record and verify the observation",
        "instructions": [
          "Select Record observation once. Check the Recorded and already recorded counts beneath the form.",
          "Review the refreshed row's source, Latest observation, and State. A historical or invalid reading might not become the latest valid reading or change a valid-reading trend.",
          "Observation times in the table use the browser's local display; the input requires an explicit timezone."
        ],
        "expected": "The form reports the inserted or duplicate count and the room table refreshes."
      },
      {
        "id": "configure-room-target",
        "title": "Save a review range only when authorized",
        "instructions": [
          "Under Room targets, choose Measurement and enter the facility's approved bounds in the displayed unit. Minimum and Maximum are optional, but when both are present Minimum cannot exceed Maximum.",
          "Set Stale after (minutes) and select Save target. Configuring a target marks that measurement as expected and can expose missing-data exceptions.",
          "For Temperature, the inputs read Minimum (C) and Maximum (C). Other selections use their own units."
        ],
        "fields": [
          {
            "label": "Measurement",
            "requirement": "Required selection.",
            "guidance": "Choose the quantity whose room review rule you are configuring."
          },
          {
            "label": "Minimum (C)",
            "requirement": "Optional Temperature lower bound.",
            "guidance": "Use the facility-approved value in the displayed unit."
          },
          {
            "label": "Maximum (C)",
            "requirement": "Optional Temperature upper bound.",
            "guidance": "Use the facility-approved value; don't infer it from a single reading."
          },
          {
            "label": "Stale after (minutes)",
            "requirement": "Required integer from 1 to 10080.",
            "guidance": "Enter the facility's expected freshness interval in minutes."
          }
        ],
        "expected": "Target saved appears and the Target column shows the configured range and stale interval."
      },
      {
        "id": "review-exception-work",
        "title": "Create follow-up only after reviewing the exception",
        "instructions": [
          "Review flagged states and the source's timestamp before assigning follow-up. Unconfigured continuous measurements become stale after 60 minutes; irrigation has no default stale interval.",
          "Past 24 hours summarizes valid readings by source/device. Irrigation totals are recorded events or volumes, not estimated delivery, and No valid readings means coverage is unknown.",
          "Select Create Doobie Work on the exception that needs a task. When a task is linked, select Open Work to review it. A flagged reading alone doesn't create a task."
        ],
        "expected": "The Follow-up column provides Open Work for the linked task, or Review required when you lack write access."
      }
    ],
    "completion": [
      "The observation response reports its saved or duplicate count.",
      "Any target change is visible in Target, and any requested task has an Open Work link."
    ],
    "troubleshooting": [
      {
        "symptom": "The timestamp or value is rejected.",
        "resolution": "Include an explicit timezone, avoid future observation times, and use the unit printed in the field. Check the actual measurement rather than altering it to satisfy validation."
      },
      {
        "symptom": "A reading doesn't appear in Past 24 hours.",
        "resolution": "Check its time and Quality. Trends use valid readings in the past 24 hours, while sources and devices remain separate."
      },
      {
        "symptom": "You aren't sure whether Record observation succeeded.",
        "resolution": "Check the recorded counts and current table before doing anything else. Keep the original evidence intact while resolving the outcome; don't turn one physical reading into multiple new observations."
      }
    ],
    "sourceFiles": [
      "frontend/src/components/CultivationEnvironmentPanel.tsx",
      "backend/app/routers/cultivation_telemetry.py",
      "modules/cultivation/telemetry.py",
      "modules/cultivation/metrics.py"
    ]
  },
  "/help/cultivation/crop-cycle-360": {
    "title": "Crop Cycle 360: record membership, room intervals, and harvest links",
    "category": "cultivation",
    "summary": "Create a crop cycle and maintain its plant membership and dated room history while preserving the distinction between cycle records and individual plant movements.",
    "navPath": "Cultivation > Cultivation command panel > Create Cycle or Crop cycles",
    "appPath": "/cultivation",
    "beforeYouStart": [
      "Have the existing room, plant, and any nursery group or harvest identifiers for the active facility.",
      "Create Cycle and Manage require effective cultivation intelligence permission as well as a write-capable role.",
      "Use the actual event times with explicit timezones. Cycle occupancy is not proof that each plant moved or experienced particular conditions."
    ],
    "steps": [
      {
        "id": "create-crop-cycle",
        "title": "Create the cycle record",
        "instructions": [
          "Select Create Cycle in the Cultivation command panel. Enter Cycle code and Cycle name, then add the known planning context.",
          "Choose an Approved recipe only if it applies to this cycle. Draft recipes aren't offered. Select Save cycle to create the record and open Crop Cycle 360."
        ],
        "fields": [
          {
            "label": "Cycle code",
            "requirement": "Required.",
            "guidance": "Use the facility's cycle identifier.",
            "example": "CYCLE-DEMO-01"
          },
          {
            "label": "Cycle name",
            "requirement": "Required.",
            "guidance": "Enter a recognizable operator-facing name."
          },
          {
            "label": "Genetics label",
            "requirement": "Optional.",
            "guidance": "Enter the known genetics description."
          },
          {
            "label": "Canonical nursery group ID (optional)",
            "requirement": "Optional existing record ID.",
            "guidance": "Use an existing nursery group in this facility, not its display code."
          },
          {
            "label": "Approved recipe",
            "requirement": "Optional; No recipe is available.",
            "guidance": "Choose the approved version intended for this cycle."
          },
          {
            "label": "Started on",
            "requirement": "Optional date.",
            "guidance": "Enter the known cycle start date."
          },
          {
            "label": "Estimated harvest date",
            "requirement": "Optional date, not earlier than Started on.",
            "guidance": "Treat this as an estimate rather than a harvest completion record."
          }
        ],
        "expected": "Crop Cycle 360 opens with the cycle name, planned status, version, and entered context."
      },
      {
        "id": "review-cycle-crop",
        "title": "Review what is actually linked",
        "instructions": [
          "For an existing cycle, expand Crop cycles and select its Open Crop Cycle link.",
          "On Crop, review Started, Estimated harvest, Approved recipe, and Canonical membership. A room assignment does not fill in missing historical membership.",
          "Check for incomplete-evidence messages before treating the list as exhaustive."
        ],
        "expected": "Crop shows linked members and either a harvest ID or an explicit missing-harvest message."
      },
      {
        "id": "record-cycle-members",
        "title": "Add or remove the intended plant members",
        "instructions": [
          "Select Manage, then set Cycle action to Change canonical membership.",
          "Choose Plant choice room to load available plants. Select 1 to 200 unique entries in Canonical plant IDs, choose Add or Remove under Membership action, and enter Effective at (ISO with timezone). Membership changes cannot be future-dated.",
          "Select Save cycle action and check Saved. Review Canonical membership on Crop before starting another action."
        ],
        "fields": [
          {
            "label": "Cycle action",
            "requirement": "Choose Change canonical membership.",
            "guidance": "This changes cycle membership, not plant location or phase."
          },
          {
            "label": "Plant choice room",
            "requirement": "Choose when loading room plants.",
            "guidance": "Use the room containing the intended plants; existing members are also offered."
          },
          {
            "label": "Canonical plant IDs",
            "requirement": "1 to 200 unique selected plants.",
            "guidance": "Select actual plant records; check tags rather than selecting every option by default."
          },
          {
            "label": "Membership action",
            "requirement": "Choose Add or Remove.",
            "guidance": "Choose the membership change that actually occurred."
          },
          {
            "label": "Effective at (ISO with timezone)",
            "requirement": "Required, not in the future.",
            "guidance": "Record when the membership changed.",
            "example": "2026-09-25T08:00:00-04:00"
          }
        ],
        "expected": "Saved appears and refreshed membership evidence reflects the accepted action."
      },
      {
        "id": "record-cycle-occupancy",
        "title": "Record a room and stage interval",
        "instructions": [
          "Set Cycle action to Record room / stage interval. Choose Room, optional Zone (optional), and an Approved recipe stage when one is evidenced.",
          "Enter Entered at (ISO with timezone). Leave Exited at (optional ISO with timezone) blank for an interval that is still open, or enter a later timestamp for a completed interval.",
          "Select Save cycle action. Intervals cannot overlap for the cycle, precede its start, or use a stage from another recipe."
        ],
        "fields": [
          {
            "label": "Room",
            "requirement": "Required existing room.",
            "guidance": "Choose the room the cycle occupied."
          },
          {
            "label": "Zone (optional)",
            "requirement": "Optional after choosing a room.",
            "guidance": "Select a known room zone or Whole room / no zone."
          },
          {
            "label": "Approved recipe stage",
            "requirement": "Optional.",
            "guidance": "Choose an offered stage from this cycle's approved recipe, or No evidenced stage."
          },
          {
            "label": "Entered at (ISO with timezone)",
            "requirement": "Required.",
            "guidance": "Use the actual start of occupancy."
          },
          {
            "label": "Exited at (optional ISO with timezone)",
            "requirement": "Optional, later than entry.",
            "guidance": "Use the actual end only if the interval is complete."
          }
        ],
        "expected": "Saved appears and History lists the room/stage interval."
      },
      {
        "id": "close-cycle-interval",
        "title": "Close an open interval before recording the next one",
        "instructions": [
          "In Manage, locate Close open occupancy for the correct room and stage. Enter Transition boundary (ISO with timezone) and select Close this occupancy.",
          "Wait for the closure to succeed. The status message supplies the saved boundary and prefills the next interval's entry time.",
          "Choose the next room/stage below and separately select Save cycle action. Check History to verify both the closure and the new interval."
        ],
        "fields": [
          {
            "label": "Transition boundary (ISO with timezone)",
            "requirement": "Required to close occupancy.",
            "guidance": "Enter the exact end of the old interval and start of the next one."
          }
        ],
        "warning": "Closing occupancy is a saved action by itself. The next interval is not saved automatically; leaving after closure leaves the cycle without that new interval.",
        "expected": "History shows the previous exit time and, only after the second save, the next entry at the same boundary."
      },
      {
        "id": "link-cycle-harvest",
        "title": "Link an existing harvest when membership is complete",
        "instructions": [
          "In Manage, choose Link existing harvest under Cycle action. Enter Existing canonical harvest ID and select Save cycle action.",
          "The server requires a recorded harvest time and an exact match between the harvest plants and cycle members at that time. The harvest cannot already belong to another cycle. This action doesn't create or execute a harvest.",
          "Return to Crop and check the harvest ID and Open existing harvest workspace link."
        ],
        "fields": [
          {
            "label": "Existing canonical harvest ID",
            "requirement": "Required existing record ID.",
            "guidance": "Use the exact harvest record ID, not just its displayed harvest code."
          }
        ],
        "warning": "The harvest link is immutable. Verify the exact harvest and membership before saving; this form has no unlink action.",
        "expected": "Crop displays the linked harvest ID after the server accepts the relationship."
      },
      {
        "id": "review-cycle-evidence",
        "title": "Review the cycle's environment, history, and costs",
        "instructions": [
          "Select Environment and, if needed, choose a Historical aggregate window using UTC hour boundaries. Review each room's coverage and unknown intervals; no aggregate evidence means unknown coverage.",
          "Select History for occupancy, events, post-harvest, output, quality, and material relationship references. Missing references are not proof of completed work.",
          "Select Economics for Allocated cost and its supporting entries. True COGS, grade, and revenue remain unknown in this view; a room's total costs don't establish the cycle's allocation."
        ],
        "expected": "The tabs expose available evidence and explicitly identify missing or incomplete relationships."
      }
    ],
    "completion": [
      "Crop displays the intended membership and harvest link, if recorded.",
      "History shows the intended occupancy boundaries. A new interval appears only after its own successful save."
    ],
    "troubleshooting": [
      {
        "symptom": "The cycle version changed while you were editing.",
        "resolution": "Select Reload current evidence and inspect the current history. Use Use current version followed by the displayed version number and keep input only after reconciling your intended change with the new evidence."
      },
      {
        "symptom": "An occupancy save reports overlap or an invalid stage.",
        "resolution": "Review History, close the correct open interval if appropriate, and use a stage from this cycle's approved recipe. Don't alter factual timestamps to avoid overlap validation."
      },
      {
        "symptom": "The harvest link is rejected.",
        "resolution": "Check the exact facility-scoped harvest ID and the cycle and harvest member sets. Resolve incomplete or conflicting membership before linking."
      }
    ],
    "sourceFiles": [
      "frontend/src/components/CultivationIntelligenceWorkspace.tsx",
      "frontend/src/components/CropCycle360.tsx",
      "frontend/src/components/CultivationIntelligenceShared.tsx",
      "modules/cultivation/intelligence_service.py",
      "modules/cultivation/gateway.py",
      "backend/app/routers/cultivation_intelligence_workspace.py"
    ]
  },
  "/help/cultivation/recipes": {
    "title": "Recipes: draft and approve facility target versions",
    "category": "cultivation",
    "summary": "Record facility-defined stages and measurement bounds, review a saved draft, and approve an immutable recipe version for cycle context.",
    "navPath": "Cultivation > Cultivation command panel > Recipes",
    "appPath": "/cultivation",
    "beforeYouStart": [
      "Use the facility's approved operating specification. This article doesn't recommend crop targets or growing practices.",
      "Recipe editing and approval require cultivation intelligence write permission.",
      "Recipes provide comparison targets and deviation thresholds. Saving or approving one does not send equipment commands."
    ],
    "steps": [
      {
        "id": "open-recipe-version",
        "title": "Open the recipe list and choose a starting point",
        "instructions": [
          "Select Recipes in the Cultivation command panel. Read each recipe's name, Version, status, description, and approval information.",
          "Select New recipe for a new definition, or New version from this recipe to copy an existing definition into the editor. Copying does not change the original version."
        ],
        "expected": "Create recipe or New recipe version opens with editable draft fields."
      },
      {
        "id": "name-recipe-draft",
        "title": "Identify the draft and its purpose",
        "instructions": [
          "Enter Recipe name and Description. Keep the existing name when intentionally creating the next version of that recipe.",
          "Describe the reason for the version so a reviewer can distinguish it from the earlier approved one."
        ],
        "fields": [
          {
            "label": "Recipe name",
            "requirement": "Required, up to 255 characters.",
            "guidance": "Use the facility's stable recipe name."
          },
          {
            "label": "Description",
            "requirement": "Optional, up to 4000 characters.",
            "guidance": "Explain scope and the reason for the proposed revision."
          }
        ],
        "expected": "The editor contains the intended recipe identity and review context; nothing is saved yet."
      },
      {
        "id": "define-recipe-stages",
        "title": "Add the facility stages in order",
        "instructions": [
          "Select Add facility stage for each stage you need. Enter a unique Stage key and a readable Stage name.",
          "Add stages in the intended order. Remove stage removes an unsaved stage from this draft; it does not alter an approved version.",
          "A recipe needs at least one stage and supports up to 32 stages."
        ],
        "fields": [
          {
            "label": "Stage key",
            "requirement": "Required and unique within the recipe.",
            "guidance": "Use a stable facility stage identifier.",
            "example": "review-stage-a"
          },
          {
            "label": "Stage name",
            "requirement": "Required.",
            "guidance": "Enter the name operators should see in the stage selector."
          }
        ],
        "expected": "The draft shows the intended sequence of named stages."
      },
      {
        "id": "enter-recipe-targets",
        "title": "Add measurement bounds in the displayed units",
        "instructions": [
          "Within a stage, select Add target and choose Measurement. Its unit determines the Minimum and Maximum labels.",
          "Enter at least one bound per target. If both are entered, Minimum cannot exceed Maximum. Use each measurement only once in a stage.",
          "For example, choosing a measurement with unit C produces Minimum (C) and Maximum (C). Copy values only from the reviewed facility specification and convert them correctly before entry.",
          "If required by that specification, enter Continuous deviation threshold (seconds, optional). This is a positive whole number of seconds, not minutes. Leaving it blank means no continuous threshold is configured."
        ],
        "fields": [
          {
            "label": "Measurement",
            "requirement": "Required for each target.",
            "guidance": "Choose an available registry measurement; its displayed unit controls the bounds."
          },
          {
            "label": "Minimum (C)",
            "requirement": "Conditional example label for a C measurement; at least one bound is required.",
            "guidance": "Enter the approved lower bound in the displayed unit."
          },
          {
            "label": "Maximum (C)",
            "requirement": "Conditional example label for a C measurement; at least one bound is required.",
            "guidance": "Enter the approved upper bound in the displayed unit."
          },
          {
            "label": "Continuous deviation threshold (seconds, optional)",
            "requirement": "Optional integer from 1 to 2678400.",
            "guidance": "Enter the approved continuous duration; 60 seconds equals one minute. Gaps break continuity."
          }
        ],
        "expected": "Each draft target shows its measurement, units, bounds, and optional threshold conversion to minutes."
      },
      {
        "id": "save-review-recipe-draft",
        "title": "Save the draft and read it back",
        "instructions": [
          "Review every stage and target, then select Save draft version. The editor closes after a successful save.",
          "Find the new draft in the recipe list. Expand its stages and compare the bounds, units, and threshold values with the specification.",
          "A saved draft is not yet available as an approved recipe for a new cycle."
        ],
        "expected": "The list shows a draft version with the saved stage targets."
      },
      {
        "id": "approve-reviewed-recipe",
        "title": "Approve the exact version after review",
        "instructions": [
          "Check the version number beside the draft, then select Approve version followed by that number.",
          "Read back the status and approval time. Changes after approval require New version from this recipe and another draft review.",
          "New approval does not rewrite a cycle's already selected recipe version or the historical evidence recorded under it."
        ],
        "warning": "Approved versions are immutable. Verify the displayed version and target units before approving; there is no edit-in-place action for an approved version.",
        "expected": "The recipe displays approved status and approval information, and can be offered in Approved recipe for new cycle creation."
      }
    ],
    "completion": [
      "The saved recipe has the intended stages, units, bounds, and threshold values.",
      "If approved, the exact version shows approval information rather than draft status."
    ],
    "troubleshooting": [
      {
        "symptom": "The draft won't save.",
        "resolution": "Check for missing stages, duplicate Stage keys, repeated measurements within a stage, unavailable measurements, missing bounds, or a Minimum greater than Maximum. Thresholds must be whole positive seconds."
      },
      {
        "symptom": "The recipe isn't listed under Approved recipe.",
        "resolution": "Return to Recipes and check that the intended version is approved in this facility. Saving a draft alone doesn't make it selectable."
      },
      {
        "symptom": "An approval reports a conflict.",
        "resolution": "Use Reload current evidence and recheck the version and status. Don't approve another version just to get past the conflict."
      }
    ],
    "sourceFiles": [
      "frontend/src/components/RecipeEditor.tsx",
      "frontend/src/components/recipeDraftPayload.ts",
      "frontend/src/components/CultivationIntelligenceWorkspace.tsx",
      "modules/cultivation/intelligence_service.py",
      "modules/cultivation/metrics.py"
    ]
  },
  "/help/cultivation/connections": {
    "title": "Cultivation connections: register devices and map sensor placement",
    "category": "cultivation",
    "summary": "Create a file configuration, register known device identities, and map their channels and dated room placement before reviewing imported evidence.",
    "navPath": "Cultivation > Cultivation connection setup > Cultivation connections",
    "appPath": "/settings/integrations?provider=cultivation",
    "beforeYouStart": [
      "Connection management requires administrator access and effective cultivation connection permission in the active facility.",
      "Have the actual export's device ID, channel, source metric, and unit, plus the physical room/zone and placement time.",
      "This guide covers file configuration and explicit device mapping. Normalized JSON push and approved nearby-sensor discovery have their own guides. Growlink remains export-only; no path promises universal hardware pairing or equipment control."
    ],
    "steps": [
      {
        "id": "open-cultivation-connections",
        "title": "Open the facility's cultivation connection setup",
        "instructions": [
          "From the Cultivation command panel, select Cultivation connection setup. On Integrations, expand Cultivation integrations if it isn't already open.",
          "Read Administrator capability and check existing File connection choices before creating another configuration."
        ],
        "expected": "Cultivation connections shows existing configurations and whether your account can manage them."
      },
      {
        "id": "create-file-configuration",
        "title": "Create a clearly named file configuration",
        "instructions": [
          "Choose File import under Collection mode, then choose Import provider: Generic JSON, Generic CSV, or Growlink export / live authorization pending.",
          "Enter Connection label and select Create file configuration. Growlink here means export evidence only; choosing it does not authorize native API access.",
          "Review the selected File connection or Cultivation connection, depending on the modes already configured. Check its label, Provider, Mode and Version before opening its devices."
        ],
        "fields": [
          {
            "label": "Collection mode",
            "requirement": "Required selection.",
            "guidance": "Choose File import for an export you will review. Normalized JSON push has separate producer credentials and instructions."
          },
          {
            "label": "Import provider",
            "requirement": "Required selection.",
            "guidance": "Choose the source category for the export you actually have."
          },
          {
            "label": "Connection label",
            "requirement": "Required, up to 120 characters in the form.",
            "guidance": "Use a name that identifies the source and facility context.",
            "example": "Demo room export"
          },
          {
            "label": "File connection / Cultivation connection",
            "requirement": "Select the exact configuration to manage.",
            "guidance": "Check the label and whether it is revoked."
          }
        ],
        "expected": "The selected configuration reports File configuration. Live activation blocked."
      },
      {
        "id": "register-source-device",
        "title": "Register the source device from the export",
        "instructions": [
          "Expand Register device. Enter Source device ID exactly as represented by the source export and add an optional Device name.",
          "Select Register device and wait for Saved. Use Register another device only for another source device.",
          "Expand that device under Scoped devices and mappings to see its version, mapping history, and sensor channels."
        ],
        "fields": [
          {
            "label": "Source device ID",
            "requirement": "Required, up to 120 characters.",
            "guidance": "Use letters, numbers, underscores, periods, colons, @, or hyphens. This must match imported rows.",
            "example": "demo-device-01"
          },
          {
            "label": "Device name",
            "requirement": "Optional.",
            "guidance": "Enter a readable label for this device."
          }
        ],
        "expected": "The device appears in Scoped devices and mappings. Registration does not discover or contact hardware."
      },
      {
        "id": "map-device-placement",
        "title": "Record where the device was placed and when",
        "instructions": [
          "Inside the device details, use New time-effective room mapping. Choose Mapped room, then Zone (optional) if the measurement is tied to a known sub-area.",
          "Enter Effective at (ISO with timezone) using the actual placement start and select Save mapping revision.",
          "After the initial placement mapping, later revisions must be future-effective and later than the previous mapping. Schedule the known placement change before it takes effect; this form does not allow a backdated remapping correction. Whole room / no zone does not prove uniform coverage throughout the room."
        ],
        "fields": [
          {
            "label": "Mapped room",
            "requirement": "Required existing room.",
            "guidance": "Choose the physical room represented by this source."
          },
          {
            "label": "Zone (optional)",
            "requirement": "Optional after choosing a room.",
            "guidance": "Choose the actual mapped sub-area, or Whole room / no zone."
          },
          {
            "label": "Effective at (ISO with timezone)",
            "requirement": "Required.",
            "guidance": "Use the placement boundary with timezone. After the initial mapping, the boundary must be future-effective and later than the previous revision.",
            "example": "2026-09-24T08:00:00-04:00"
          }
        ],
        "expected": "Saved appears and the mapping history shows the new effective time and zone."
      },
      {
        "id": "map-device-channel",
        "title": "Map each source channel to a measurement",
        "instructions": [
          "Under Map source channel, copy Source channel, Source metric, and Source unit from the export. Choose Normalized measurement from the available registry.",
          "Select Save channel mapping. Check the displayed source-to-measurement mapping and units after saving.",
          "Use Map another channel for a different channel. A room placement mapping by itself does not identify what a channel measures."
        ],
        "fields": [
          {
            "label": "Source channel",
            "requirement": "Required.",
            "guidance": "Match the source channel exactly.",
            "example": "air-1"
          },
          {
            "label": "Source metric",
            "requirement": "Required.",
            "guidance": "Use the measurement identifier present in the export.",
            "example": "temperature"
          },
          {
            "label": "Source unit",
            "requirement": "Required.",
            "guidance": "Use the actual source unit; do not relabel Fahrenheit data as C.",
            "example": "C"
          },
          {
            "label": "Normalized measurement",
            "requirement": "Required supported measurement.",
            "guidance": "Choose the corresponding quantity and check its displayed normalized unit."
          }
        ],
        "expected": "The device shows the saved channel mapping from source metric/unit to the selected measurement/unit."
      },
      {
        "id": "check-connection-evidence",
        "title": "Review evidence health without assuming a live connection",
        "instructions": [
          "Read Last import (count-only audit), Last local receipt, and Last valid sensor reading separately.",
          "Review Local states and whether the local evidence store is available. Import activity and these clocks do not establish expected freshness or live connectivity.",
          "Continue with Import JSON / CSV evidence only after checking device and placement mappings."
        ],
        "expected": "You can identify the selected configuration's evidence clocks and local storage state, while Live contract remains blocked."
      },
      {
        "id": "revoke-file-ingestion",
        "title": "Revoke a configuration only when ingestion should stop",
        "instructions": [
          "If this source should no longer accept evidence, verify the selected File connection and choose Revoke connection and preserve evidence.",
          "Read the resulting state before leaving. Existing evidence remains available, but ingestion for the revoked configuration is disabled."
        ],
        "warning": "Revocation stops ingestion. This screen provides no restore action, so confirm the exact configuration before selecting the button.",
        "expected": "The connection displays Revoked. Existing evidence is preserved; ingestion is disabled."
      }
    ],
    "completion": [
      "The selected configuration contains the intended device, dated placement mapping, and channel mappings.",
      "The page identifies it as file evidence only, not a live provider connection."
    ],
    "troubleshooting": [
      {
        "symptom": "Create or mapping controls are missing.",
        "resolution": "Read Administrator capability. Ask a facility administrator to review your effective cultivation connection permission; a general cultivation write role is not enough."
      },
      {
        "symptom": "A version conflict prevents saving a mapping.",
        "resolution": "Use Reload current evidence, inspect the latest placement and channel mappings, then use the displayed Use current device version control if your change is still appropriate."
      },
      {
        "symptom": "Imports don't appear in the intended room.",
        "resolution": "Compare exact source device/channel identifiers, source metric and unit, and the mapping's effective time with observed_at. Registering a device alone doesn't assign its readings to a room."
      }
    ],
    "sourceFiles": [
      "frontend/src/pages/IntegrationsPage.tsx",
      "frontend/src/components/CultivationConnections.tsx",
      "frontend/src/components/CultivationIntelligenceShared.tsx",
      "modules/cultivation/intelligence_service.py",
      "modules/cultivation/gateway.py",
      "modules/cultivation/adapters/growlink.py"
    ]
  },
  "/help/cultivation/imports": {
    "title": "Cultivation imports: preview and commit JSON or CSV evidence",
    "category": "cultivation",
    "summary": "Load an explicit measurement export, review its validation and mappings, then commit the reviewed content and inspect every result category.",
    "navPath": "Cultivation > Cultivation connection setup > File connection > Import JSON / CSV evidence",
    "appPath": "/settings/integrations?provider=cultivation",
    "beforeYouStart": [
      "Select an active cultivation connection in the correct facility and confirm administrator connection permission. A file imported into a push configuration is still file evidence; it does not prove the producer is sending readings.",
      "Prepare JSON or CSV of at most 1 MiB and 500 rows. JSON uses an array of row objects; CSV uses the header shown in the form.",
      "Required row fields are event_id, source_device_id, source_channel, source_metric, value, unit, and observed_at. Timestamps require a timezone. Use real source event IDs consistently so duplicate evidence can be recognized.",
      "Growlink support is export-only. The importer does not accept arbitrary vendor formats by automatically identifying their columns."
    ],
    "steps": [
      {
        "id": "select-import-connection",
        "title": "Select the exact evidence destination",
        "instructions": [
          "Open Cultivation connection setup, then choose File connection. Verify Provider, Mode, and the configuration label.",
          "Review Scoped devices and mappings, including room placement times and channels. A file may parse correctly while its readings still lack a usable room mapping."
        ],
        "expected": "Import JSON / CSV evidence is available under an active configuration you are allowed to manage."
      },
      {
        "id": "load-export-content",
        "title": "Load the export and confirm its format",
        "instructions": [
          "Choose JSON or CSV under File format. Select Choose evidence file or paste the export into Measurement content.",
          "For CSV, use the exact required header: event_id,source_device_id,source_channel,source_metric,value,unit,observed_at. For JSON, use those field names on each row object.",
          "Check units and observed_at values before previewing. An example timezone-aware timestamp is 2026-09-25T08:00:00-04:00. The form loads file content; it does not send a filesystem path."
        ],
        "fields": [
          {
            "label": "File format",
            "requirement": "Required selection.",
            "guidance": "Match the actual JSON or CSV content; file selection doesn't choose this for you."
          },
          {
            "label": "Choose evidence file",
            "requirement": "Optional alternative to pasting.",
            "guidance": "Choose a .json or .csv export within the 1 MiB limit."
          },
          {
            "label": "Measurement content",
            "requirement": "Required content, loaded from file or pasted.",
            "guidance": "Keep rows at or below 500 and preserve source identifiers, measured values, units, and timestamps."
          }
        ],
        "expected": "Measurement content contains the export to be reviewed; nothing has been committed."
      },
      {
        "id": "supply-import-mappings",
        "title": "Review explicit measurement mappings",
        "instructions": [
          "After loading the file, check Selected file preview. These are the original source values, not validated room readings.",
          "Select Use source channels for mapping to copy the distinct channel, source measurement and original unit combinations into Review channel mappings. Choose Normalized measurement for each combination.",
          "Use Add channel mapping for a missing combination or Remove mapping for an entry you do not intend to map. Complete every field in a remaining mapping. An intentionally unmapped channel can stay pending for review rather than becoming usable room evidence.",
          "The device mapping above controls room, zone and effective time. Choosing a normalized measurement here does not assign the device to a room or rewrite its historical placement."
        ],
        "fields": [
          {
            "label": "Source channel",
            "requirement": "Required for each retained mapping.",
            "guidance": "Match the original channel exactly as it appears in the export.",
            "example": "temperature"
          },
          {
            "label": "Source measurement",
            "requirement": "Required for each retained mapping.",
            "guidance": "Keep the source measurement name from the selected file. It may differ from the normalized measurement.",
            "example": "qa_temperature"
          },
          {
            "label": "Original unit",
            "requirement": "Required for each retained mapping.",
            "guidance": "Choose the actual source unit. Do not label a Fahrenheit value as Celsius to make the units match.",
            "example": "F"
          },
          {
            "label": "Normalized measurement",
            "requirement": "Required for each retained mapping.",
            "guidance": "Select the meaning of the reading from the supported measurement list. The server performs supported conversion.",
            "example": "Temperature (C)"
          }
        ],
        "expected": "Every retained mapping has a source channel, measurement, original unit and normalized measurement. The selected file has not been committed."
      },
      {
        "id": "preview-measurement-import",
        "title": "Preview before committing",
        "instructions": [
          "Select Preview import and check Preview rows, Unknown channels and Conflicts.",
          "In Server normalized preview, compare Original and Normalized, Observed (UTC), Destination and Review status. Confirm the actual room, zone and crop rather than assuming your current screen supplies them. Only the first 20 sample rows are displayed; counts cover the full file.",
          "Normalized, not committed means the sample passed that preview. Assign a device, room and channel mapping means placement or channel evidence is unresolved. Unavailable is not a zero reading.",
          "If Commit blocked appears, fix the stated validation or mapping conflict. Editing content, format or mappings cancels the previous preview. A changed connection version also requires a new preview before committing."
        ],
        "expected": "The preview either explains the blocking issue or enables Commit reviewed import for the reviewed content."
      },
      {
        "id": "commit-reviewed-evidence",
        "title": "Commit only the reviewed content",
        "instructions": [
          "After reviewing the preview, select Commit reviewed import once. This saves the reviewed file evidence to the local evidence workflow; it does not establish live connection health.",
          "Read Accepted, duplicates, conflicts, queued for mapping, and quarantined, plus any individual disposition reasons. Accepted is not a promise that every row appears as a fresh room reading.",
          "If the outcome is uncertain, inspect the configuration's clocks and result evidence before submitting again. Preserve event IDs and content while resolving the outcome."
        ],
        "expected": "The result displays counts by disposition and clears the reviewed commit state."
      },
      {
        "id": "resolve-queued-evidence",
        "title": "Resolve mapping gaps and process the queue",
        "instructions": [
          "For queued mapping evidence, review the device, source channel, source metric/unit, and room mapping interval against the original row.",
          "After correcting the actual missing mapping, expand Process queued mapping evidence and select Process up to 100 queued rows.",
          "Read Processed, pending, and conflicts. This retries local mapping resolution; it doesn't issue equipment commands or create Work automatically."
        ],
        "expected": "The queue action reports processed, pending, and conflict counts for the batch."
      },
      {
        "id": "verify-imported-room-readings",
        "title": "Check the resulting room evidence",
        "instructions": [
          "Return to Cultivation and open the mapped room's Open Room 360 link, then Environment.",
          "Review Latest sensor readings and Reading details for the source, observed time, original unit, mapping revision, and freshness.",
          "Historical aggregates are separate from the latest-reading view. Missing aggregates or stale current values should remain unknown until evidence supports them."
        ],
        "expected": "Room 360 shows the available mapped evidence or a specific missing/stale state rather than a fabricated current value."
      }
    ],
    "completion": [
      "The import result records disposition counts for the reviewed file.",
      "Any usable room readings can be traced to the intended source and mapping, with freshness checked separately."
    ],
    "troubleshooting": [
      {
        "symptom": "The export won't parse.",
        "resolution": "Check File format, JSON array structure or the CSV header, required row fields, 1 MiB size, and 500-row limit. Convert the export to the documented structure outside the app rather than assuming native vendor columns are supported."
      },
      {
        "symptom": "Commit reviewed import is disabled.",
        "resolution": "Run Preview import after every edit and after any connection version change. Resolve reported conflicts; a stale preview cannot authorize changed content."
      },
      {
        "symptom": "Rows are queued, quarantined, or conflicting.",
        "resolution": "Read the disposition reasons and verify source identifiers, units, quality, times, and dated room mappings. Process the mapping queue only after resolving its cause. Don't change source event IDs to disguise a conflicting duplicate."
      }
    ],
    "sourceFiles": [
      "frontend/src/components/CultivationConnections.tsx",
      "modules/cultivation/gateway.py",
      "modules/cultivation/adapters/normalized.py",
      "modules/cultivation/adapters/growlink.py",
      "modules/cultivation/edge_store.py",
      "backend/app/routers/cultivation_intelligence_workspace.py",
      "frontend/src/components/telemetryMappingTable.tsx",
      "frontend/src/components/telemetryReview.ts",
      "modules/cultivation/preview_samples.py"
    ]
  },
  "/help/cultivation/evidence-maintenance": {
    "title": "Cultivation evidence: build local summaries and review retention",
    "category": "cultivation",
    "summary": "Build dated local aggregates, inspect archive acknowledgements, and review protected raw-reading retention before any removal.",
    "navPath": "Cultivation connection setup > File connection > Local aggregate maintenance",
    "appPath": "/settings/integrations?provider=cultivation",
    "beforeYouStart": [
      "Use the intended facility and active file configuration with administrator connection permission.",
      "Local maintenance does not publish data to a cloud provider. Raw readings stay local when summaries are archived.",
      "Follow your facility's retention decision. Removing raw bodies is a separate action from building or archiving summaries."
    ],
    "steps": [
      {
        "id": "inspect-maintenance-protection",
        "title": "Inspect local maintenance and protection",
        "instructions": [
          "Select the intended File connection, then expand Local aggregate maintenance.",
          "Read Retention protection, the host's Limits, and whether a local summary archive is configured. Don't assume a visible summary means its exact revision has been archived and acknowledged."
        ],
        "expected": "The panel shows the local configuration and archive/protection state."
      },
      {
        "id": "build-dated-local-aggregates",
        "title": "Build the selected local aggregate window",
        "instructions": [
          "Expand Historical aggregate window and enter Start (UTC hour) and End (UTC hour) on UTC hour boundaries ending in Z, no more than 31 days apart.",
          "Select Read dated aggregates to apply the window, verify Selected aggregate window, then select Build selected local aggregates.",
          "Review Rebuilt, unchanged, blocked, and truncated. Building summaries doesn't fill missing intervals or publish them to a cloud receiver."
        ],
        "fields": [
          {
            "label": "Start (UTC hour)",
            "requirement": "Required for the build window.",
            "guidance": "Use a whole UTC hour at the start of the intended interval.",
            "example": "2026-09-24T00:00:00Z"
          },
          {
            "label": "End (UTC hour)",
            "requirement": "Required and later than start.",
            "guidance": "Use a whole UTC hour within 31 days of the start.",
            "example": "2026-09-25T00:00:00Z"
          }
        ],
        "expected": "The result reports how many aggregates were rebuilt, unchanged, or blocked and whether the batch was incomplete."
      },
      {
        "id": "archive-local-summaries",
        "title": "Archive summaries when the host supports it",
        "instructions": [
          "If Archive local summaries is available, select it and inspect Archived, Exact revisions acknowledged, and Stale revisions.",
          "A stale revision or incomplete archive needs review before retention. Raw readings are not removed by this archive action.",
          "If the panel says the local summary archive isn't configured, ask the system administrator to review host setup; there is no browser field for configuring that storage."
        ],
        "expected": "The archive result reports acknowledgements and batch completeness, or the panel explicitly states that the archive is not configured."
      },
      {
        "id": "preview-raw-retention",
        "title": "Preview retention prerequisites for an exact cutoff",
        "instructions": [
          "Expand Raw reading retention. Enter Raw readings before (UTC) as a past timestamp ending in Z, including seconds.",
          "Select Preview retention prerequisites and read Protection. This checks prerequisites only; it does not calculate the eligible count or remove evidence.",
          "Changing the cutoff clears the reviewed preview and acknowledgement, so preview the new value again."
        ],
        "fields": [
          {
            "label": "Raw readings before (UTC)",
            "requirement": "Required past UTC timestamp for retention.",
            "guidance": "Use the approved cutoff, not the newest reading time.",
            "example": "2026-09-24T00:00:00Z"
          }
        ],
        "expected": "The preview reports prerequisite protection and explicitly says the eligible count is unknown until execution."
      },
      {
        "id": "execute-reviewed-retention",
        "title": "Remove eligible raw bodies only after the retention decision",
        "instructions": [
          "Review the cutoff and archive state, then select I understand that only eligible already-archived raw bodies can be removed. only if this is the intended action.",
          "Select Remove eligible raw readings. The action is limited to a batch and preserves identity records and summaries.",
          "Read Raw bodies removed, Protected, and any incomplete-batch or blocker message. Pending, quarantined, conflicting, or unacknowledged evidence remains protected; don't bypass that protection."
        ],
        "fields": [
          {
            "label": "I understand that only eligible already-archived raw bodies can be removed.",
            "requirement": "Required acknowledgement before removal.",
            "guidance": "Check only after reviewing the exact cutoff and prerequisite result."
          }
        ],
        "warning": "This removes eligible raw reading bodies. It is not a preview and this screen has no undo action. Confirm the facility, connection, cutoff, and approved retention decision first.",
        "expected": "The result reports whether removal executed, how many raw bodies were removed, and how many remained protected."
      }
    ],
    "completion": [
      "Build and archive results identify the selected batch's outcome and completeness.",
      "If retention was executed, the displayed removal and protection counts describe the result without implying all older evidence was removed."
    ],
    "troubleshooting": [
      {
        "symptom": "Remove eligible raw readings stays disabled.",
        "resolution": "Check that the host archive is configured, the current cutoff has a successful preview, and the acknowledgement is checked. Don't change host settings merely to force a retention action."
      },
      {
        "symptom": "Evidence remains protected or aggregates are blocked.",
        "resolution": "Read the blocker and inspect unresolved mappings, conflicts, and exact archive revisions. Protected evidence needs resolved mappings and clean verified archives covering its full interval."
      }
    ],
    "sourceFiles": [
      "frontend/src/components/CultivationConnections.tsx",
      "frontend/src/components/CultivationIntelligenceShared.tsx",
      "modules/cultivation/gateway.py",
      "modules/cultivation/edge_store.py",
      "modules/cultivation/aggregate_archive.py"
    ]
  },
  "/help/cultivation/plant-exposure": {
    "title": "Plant exposure: review the evidence behind a plant's history",
    "category": "cultivation",
    "summary": "Read environmental exposure status, mother and group references, and cycle occupancy without treating a plant's current room as proven historical exposure.",
    "navPath": "Cultivation > Plant 360 > Environmental exposure",
    "appPath": "/cultivation",
    "beforeYouStart": [
      "Know the plant tag and active facility.",
      "This is a read-only evidence panel. Cycle occupancy and current room assignment don't establish an individual plant's movement history or exposure."
    ],
    "steps": [
      {
        "id": "open-plant-exposure",
        "title": "Open the exact plant record",
        "instructions": [
          "In Cultivation, find the plant in the table and select its row. You can also follow a plant tag from Room 360 or an Open plant evidence link.",
          "Check the Plant 360 header's tag, strain, phase, and room before reading Environmental exposure."
        ],
        "expected": "Environmental exposure loads for the selected plant, or reports that the requested exposure is unavailable."
      },
      {
        "id": "read-exposure-status",
        "title": "Read the exposure status and reason first",
        "instructions": [
          "Read the status and explanation at the top of Environmental exposure. Treat unknown or missing exposure as unknown, not as a period within target.",
          "A current room reading cannot be applied backward across a plant's life. Exposure needs supported movement history and source coverage for the relevant intervals."
        ],
        "expected": "The panel provides the available exposure status and its reason without substituting another plant."
      },
      {
        "id": "review-plant-relationships",
        "title": "Check mother, group, and harvest references",
        "instructions": [
          "Review Mother plant, Group references, and Harvest references. Use Open canonical mother only when the link is present, then verify that plant's tag in the new view.",
          "Compare the separate Plant lineage section below if you need the recorded group, mother, source lot, or external package relationship. A legacy mother tag isn't the same as a first-class mother link.",
          "If relationship references are incomplete, don't treat unlisted references as proof that no relationship exists."
        ],
        "expected": "Known relationships are displayed as references or links, while unavailable ones remain Unknown or absent."
      },
      {
        "id": "inspect-membership-occupancy",
        "title": "Review cycle membership separately from exposure",
        "instructions": [
          "Read Canonical cycle membership, then Cohort occupancy references. Follow Open Crop Cycle or Open Room 360 links when present to inspect the supporting context.",
          "Compare the reported entry and exit times with the question you're investigating. Cycle occupancy describes the cohort; it doesn't prove that this individual plant moved with it."
        ],
        "expected": "The available membership and occupancy references are visible, including their missing-evidence messages."
      },
      {
        "id": "check-proven-exposure-intervals",
        "title": "Finish with the proven intervals or the stated gap",
        "instructions": [
          "Read the No proven exposure intervals message at the bottom. The current service reports exposure as unknown and does not calculate proven individual exposure intervals. Retain that limitation in your review.",
          "Use Lifecycle history for recorded plant changes and Room 360 for source coverage, but don't invent an exposure interval by combining a present-day room assignment with an old sensor reading.",
          "There is no save or exposure-override control in this panel. Correct underlying records through their own authorized workflows when the factual evidence supports a correction."
        ],
        "expected": "Your review distinguishes linked relationships and cohort history from proven individual exposure."
      }
    ],
    "completion": [
      "The reviewed plant tag and exposure status are known.",
      "Missing intervals and incomplete references remain explicitly identified rather than reported as measured exposure."
    ],
    "troubleshooting": [
      {
        "symptom": "A plant has room readings but no proven exposure intervals.",
        "resolution": "Review the panel's reason and the plant movement and source-coverage evidence. Room readings alone don't prove an individual plant was exposed to them."
      },
      {
        "symptom": "The plant or its relationships are unavailable.",
        "resolution": "Verify the active facility and exact plant link. Use Retry for a read failure; don't open a different plant and treat its evidence as a substitute."
      }
    ],
    "sourceFiles": [
      "frontend/src/components/PlantExposure.tsx",
      "frontend/src/components/PlantInventory.tsx",
      "frontend/src/components/CultivationIntelligenceShared.tsx",
      "modules/cultivation/intelligence_service.py",
      "backend/app/routers/cultivation_intelligence_workspace.py"
    ]
  },
  "/help/cultivation/push-setup": {
    "title": "Set up a producer that sends cultivation readings",
    "category": "cultivation",
    "summary": "Create a normalized JSON connection, authorize one producer, map its sources and check what actually arrived.",
    "navPath": "Settings & Administration → Integrations → Cultivation connections",
    "appPath": "/settings/integrations?provider=cultivation",
    "beforeYouStart": [
      "Use the intended facility and an administrator account with effective cultivation connection permission. The source owner must authorize the integration.",
      "This receiver accepts the published normalized JSON contract. It is not a native Growlink webhook, an equipment-discovery tool, or a way to control environmental equipment.",
      "Have the real device IDs, channels, original units and placement times. Do not put credentials in screenshots, shared documents or measurement payloads."
    ],
    "steps": [
      {
        "id": "push-choose-mode",
        "title": "Create the push configuration",
        "instructions": [
          "Open Cultivation connections and choose Normalized JSON push under Collection mode. Import provider becomes Generic JSON.",
          "Enter Connection label. Under Optional delivery expectations, enter the actual producer schedule only when known. Leave unknown expectations blank.",
          "Select Create push connection, then check the selected connection label, Mode and Version. Creating a configuration does not mean a producer is sending readings."
        ],
        "expected": "The new configuration is selected and Normalized push setup is available. It is still awaiting actual producer evidence.",
        "fields": [
          {
            "label": "Collection mode",
            "requirement": "Required.",
            "guidance": "Choose Normalized JSON push for a producer that implements this receiver."
          },
          {
            "label": "Connection label",
            "requirement": "Required, up to 120 characters.",
            "guidance": "Use a recognizable source name without putting credentials in the label.",
            "example": "Demo temperature producer"
          },
          {
            "label": "Expected interval (seconds)",
            "requirement": "Optional whole seconds, 1 to 2678400.",
            "guidance": "Enter the actual connection delivery interval. This does not define the cadence of every sensor."
          },
          {
            "label": "Stale after (seconds)",
            "requirement": "Optional whole seconds, 1 to 2678400.",
            "guidance": "Use the agreed delivery freshness window. This is not a crop target or a deviation duration threshold."
          }
        ]
      },
      {
        "id": "push-review-contract",
        "title": "Read the receiver instructions with the source owner",
        "instructions": [
          "Expand Integration instructions in Normalized push setup. Use the exact connection endpoint shown there; do not send to a different facility connection.",
          "The producer sends Content-Type: application/json with a bearer credential. Schema version 1 has batch_id and readings. Each reading needs event_id, source_device_id, source_channel, source_metric, value, unit and observed_at with a timezone.",
          "Respect the displayed limits: at most 1 MiB and 500 readings, possibly less under host configuration. Identity fields use the allowed ASCII characters and have a 120-character maximum. Do not add organization, facility, room, URLs, receipt timestamps or credentials to reading bodies.",
          "The example payload is a format example, not a measured observation. Replace its identifiers, values and timestamp with real source evidence."
        ],
        "expected": "The source owner has the correct endpoint and payload contract. No successful connection is inferred from opening these instructions."
      },
      {
        "id": "push-map-source",
        "title": "Register and place each source before relying on its readings",
        "instructions": [
          "Expand Register device and enter the exact Source device ID and a recognizable Device name. Register device saves this identity; it does not discover hardware.",
          "Open the saved device under Scoped devices and mappings. Complete New time-effective room mapping with Mapped room, optional zone and Effective at (UTC). Review before selecting Save mapping revision.",
          "Under Map source channel, supply Source channel, Source metric, Source unit and Normalized measurement. Select Save channel mapping after checking them against the actual export or producer.",
          "Review the saved mapping history. No zone assigned means a room-level association is known, not that one sensor represents the whole room. A later placement revision preserves the earlier history."
        ],
        "expected": "The exact device has saved channel and time-effective placement mappings. Missing mappings can still leave incoming evidence pending."
      },
      {
        "id": "push-issue-grant",
        "title": "Authorize this producer explicitly",
        "instructions": [
          "Select Create ingress grant. Enter Producer label and a future Expires at (ISO with timezone).",
          "Check the active connection, producer and expiry, then select Issue one-time credential once. An existing broad service account does not authorize this specific receiver.",
          "If the response is lost or an error appears, select Reload grant and connection evidence before trying again. A grant may exist even if its credential never reached the browser. Revoke an unused grant before replacing it."
        ],
        "expected": "On a confirmed issuance, the one-time credential appears and the grant is listed for this connection.",
        "fields": [
          {
            "label": "Producer label",
            "requirement": "Required, up to 120 characters.",
            "guidance": "Identify the authorized sender so another administrator can recognize the grant.",
            "example": "Demo facility collector"
          },
          {
            "label": "Expires at (ISO with timezone)",
            "requirement": "Required future timestamp.",
            "guidance": "Use a future date with Z or an explicit timezone offset. Do not use a timezone-free date.",
            "example": "2026-10-26T12:00:00Z"
          }
        ],
        "warning": "Issuing a grant creates connection-specific authorization. Only issue it for an approved producer; never capture the revealed credential in training images."
      },
      {
        "id": "push-save-credential",
        "title": "Move the one-time credential into protected producer configuration",
        "instructions": [
          "Select Copy credential and store it in the producer’s protected configuration. If clipboard access is denied, select and copy the text manually.",
          "Close credential setup when the producer owner has stored it safely. Closing the setup, switching connection or facility, or losing management access clears the value from view.",
          "The grant list does not reveal the credential later. If it was lost, inspect and revoke the unused grant rather than expecting it to be shown again."
        ],
        "expected": "The producer owner has stored the credential securely and the setup is closed. A copied credential alone does not prove any readings were received."
      },
      {
        "id": "push-check-receipts",
        "title": "Check delivery and observation evidence separately",
        "instructions": [
          "Select Refresh connection health. The active browser also refreshes this evidence periodically. Read Grant state, Last committed push and Current valid observation together.",
          "Awaiting first reading means no committed push receipt is evidenced. Receiving readings requires qualifying current delivery and observation evidence, not just an old file import.",
          "Readings are stale refers to observation age. An old reading delivered now remains old. A recent connection receipt cannot establish every sensor’s freshness.",
          "Review Mapping backlog and Storage and evidence limits. Use Room 360 to inspect each source and its recorded crop context. On 429, the producer must respect Retry-After; a 503 unavailable response is not a durable receipt. Preserve stable identities and unchanged payloads when retrying a lost acknowledgement."
        ],
        "expected": "The connection health panel distinguishes authorization, delivery, observations, pending mappings and storage state. Room health remains a separate check."
      },
      {
        "id": "push-revoke-grant",
        "title": "Revoke access that is no longer needed",
        "instructions": [
          "Locate the exact producer in Connection ingress grants. Select Revoke followed by its label.",
          "Review the confirmation and current version, then choose Confirm grant revocation. Cancel and refresh first if the version changed.",
          "Verify the updated grant status. Connection revocation is a separate, broader action that disables ingestion for the connection."
        ],
        "expected": "The revoked grant no longer authorizes later admissions. Existing evidence remains available.",
        "warning": "A bounded request authorized before revocation may finish. Revocation does not delete observations or erase their audit history."
      }
    ],
    "completion": [
      "The intended connection and producer are identified, with an explicitly reviewed grant and saved device mappings.",
      "Health evidence and per-source Room 360 readings have been checked separately. No native vendor integration, continuous coverage or equipment control is inferred."
    ],
    "troubleshooting": [
      {
        "symptom": "Create ingress grant is missing.",
        "resolution": "Check that the connection uses Normalized JSON push, is active, and your account has administrator and effective cultivation connection permission. Read-only users cannot issue credentials."
      },
      {
        "symptom": "The credential response was lost.",
        "resolution": "Reload grant and connection evidence. Inspect and revoke any unused grant before issuing a replacement; never assume the first request did nothing."
      },
      {
        "symptom": "Push is receiving but a room reading is Unknown.",
        "resolution": "Check the individual channel, original unit, observation time and effective room mapping. A fresh connection receipt does not prove that channel is current or valid."
      },
      {
        "symptom": "Storage limit reached or status unavailable appears.",
        "resolution": "Keep the producer’s source backlog. Have the authorized host operator inspect storage and collector health. Do not assume an unavailable response acknowledged persistence or delete unresolved evidence to clear space."
      }
    ],
    "sourceFiles": [
      "frontend/src/components/CultivationConnections.tsx",
      "frontend/src/components/CultivationPushSetup.tsx",
      "backend/app/routers/cultivation_ingress.py",
      "modules/cultivation/ingress.py",
      "modules/cultivation/gateway.py"
    ]
  },
  "/help/cultivation/deviation-work": {
    "title": "Turn a reviewed historical deviation into Work",
    "category": "cultivation",
    "summary": "Check a proven out-of-range interval, create or reuse its Work item, and keep the link back to the exact room evidence.",
    "navPath": "Cultivation → Open Room 360 → Environment → Review historical deviations for Work",
    "appPath": "/cultivation",
    "beforeYouStart": [
      "Open the exact room in the active facility. This workflow uses a selected persisted historical aggregate window, not a single latest reading.",
      "Eligible evidence needs an approved historical recipe, targets, mapping and sufficient continuous duration. Missing coverage cannot be treated as healthy or joined across gaps.",
      "Creating Work requires effective cultivation write access and Work creation permission. Reviewing evidence does not create tasks automatically."
    ],
    "steps": [
      {
        "id": "deviation-select-history",
        "title": "Select the historical window you intend to investigate",
        "instructions": [
          "Open the room through Open Room 360, select Environment and apply the dated historical window using the existing aggregate controls.",
          "Check the dates and whether historical evidence is available. If the required persisted aggregates do not exist, have the authorized operator prepare the correct window through local aggregate maintenance first.",
          "Do not use the newest sensor value as proof of a historical duration."
        ],
        "expected": "The room shows the intended historical window. Review eligible deviations is enabled only when a valid window is available."
      },
      {
        "id": "deviation-review-eligible",
        "title": "Read the eligible historical deviations",
        "instructions": [
          "Under Review historical deviations for Work, select Review eligible deviations.",
          "Check whether the response is complete. Evidence is incomplete means you must refresh before creating Work. No eligible duration-qualified deviations means this window has not established a qualifying event, not that missing coverage was healthy.",
          "For an eligible item, compare the measurement, direction, interval, Continuous duration and Required duration."
        ],
        "expected": "Each eligible item shows the specific measured interval and duration requirement, or the panel explicitly explains why none is available."
      },
      {
        "id": "deviation-review-action",
        "title": "Review the Work action before creating it",
        "instructions": [
          "For the exact event you intend to follow up, select Review Work action.",
          "Check the interval again. The action creates one task for this historical exception or reuses an existing task for it, including completed Work.",
          "Do not create a separate manual duplicate simply because the existing task is completed. Open that task and review its evidence instead."
        ],
        "expected": "The confirmation offers Create Doobie Work for the selected, still-valid exception. No new Work has been created merely by reviewing it."
      },
      {
        "id": "deviation-create-reviewed",
        "title": "Create or reuse the linked Work item",
        "instructions": [
          "Select Create Doobie Work once after review.",
          "Wait for Open Work and Return to this room exception. If an error leaves the outcome uncertain, refresh the evidence before another attempt.",
          "A permission error or changed-evidence conflict requires resolution through the normal authorization or evidence workflow; do not bypass it."
        ],
        "expected": "The event is linked to a saved Work item, with links to the task and the exact source exception.",
        "warning": "This action saves an operational task. It does not adjust inventory, send a Metrc action, notify a vendor or control equipment."
      },
      {
        "id": "deviation-follow-return",
        "title": "Keep the task and source evidence connected",
        "instructions": [
          "Select Open Work to inspect the linked task, owner and progress in the Work workspace.",
          "Use Return to this room exception to reopen the same room, historical dates and selected exception.",
          "Review current evidence when returning. The task records evidence as it stood at creation, not a promise that subsequent sensor data cannot change the picture."
        ],
        "expected": "The links open the correct Work item and the source room exception rather than a generic dashboard."
      },
      {
        "id": "deviation-refresh-changed",
        "title": "Re-review evidence after a conflict",
        "instructions": [
          "If Evidence changed appears, select Review refreshed evidence.",
          "Check the refreshed interval and required duration again before reopening Review Work action. An updated aggregate revision requires another review even when its displayed duration looks similar.",
          "If the selected exception is no longer available, investigate the revised window. Do not repeatedly submit the old selection."
        ],
        "expected": "The panel uses refreshed evidence and requires a deliberate new review before another creation attempt."
      }
    ],
    "completion": [
      "The saved task is linked to the intended historical exception and its return link preserves the room and window.",
      "The event was reviewed explicitly, with no automatic hardware, inventory or provider changes."
    ],
    "troubleshooting": [
      {
        "symptom": "Review eligible deviations is disabled.",
        "resolution": "Select a valid persisted historical aggregate window. Current readings alone cannot supply the required dated evidence."
      },
      {
        "symptom": "No eligible duration-qualified deviations are found.",
        "resolution": "Check coverage, approved recipe targets, continuous duration and mapping at the observation time. Missing or interrupted evidence cannot be assumed to satisfy a threshold."
      },
      {
        "symptom": "Only Read only is shown.",
        "resolution": "Ask an authorized operator with both cultivation write and Work creation permission to review the event. Do not change the facility to bypass access controls."
      },
      {
        "symptom": "The task already exists or has been completed.",
        "resolution": "Use Open Work. The bridge reuses the existing task for the same exception so repeat review does not silently create duplicates."
      }
    ],
    "sourceFiles": [
      "frontend/src/components/ImportedDeviationWork.tsx",
      "frontend/src/components/Room360.tsx",
      "frontend/src/components/telemetryReview.ts",
      "backend/app/routers/cultivation_edge_work.py",
      "modules/cultivation/edge_work.py"
    ]
  },
  "/help/cultivation/nearby-sensors": {
    "title": "Find and link a supported nearby sensor",
    "category": "cultivation",
    "summary": "Use the facility receiver to find supported broadcasts, check the sensor identity, and approve read-only collection for its room.",
    "navPath": "Settings & Administration → Integrations → Cultivation integrations → Find nearby sensors",
    "appPath": "/settings/integrations?provider=cultivation",
    "beforeYouStart": [
      "An authorized host administrator must configure a supported local receiver for this exact organization and facility. Discovery listens at that facility PC, not at your phone or a remote office.",
      "Use an account with effective connection-management permission. Only identify equipment you are authorized to manage.",
      "The sensor must use a supported, unencrypted broadcast format. Sharing a frequency is not enough. This workflow does not bypass encryption, pair every commercial controller, or send commands to equipment."
    ],
    "steps": [
      {
        "id": "radio-check-receiver",
        "title": "Check that you are listening at the right facility",
        "instructions": [
          "Open Cultivation integrations and find Find nearby sensors.",
          "Read the receiver status. If this facility has no configured local radio receiver, ask the authorized host administrator to set it up before continuing. File imports and normalized JSON push remain separate options.",
          "Check Listening location and the receiver shown. When more than one receiver is configured, select Receiver for the equipment you intend to identify."
        ],
        "fields": [
          {
            "label": "Receiver",
            "requirement": "Shown when more than one receiver is available.",
            "guidance": "Choose the configured receiver for this source. A frequency label is not a guarantee that the sensor format can be decoded."
          }
        ],
        "expected": "The panel identifies this facility’s receiver and shows the authorization control, or clearly explains why local discovery is unavailable."
      },
      {
        "id": "radio-authorize-search",
        "title": "Authorize a bounded search",
        "instructions": [
          "Select I am authorized to identify sensors at this facility only when that is true.",
          "Select Find sensors. The page shows the bounded listening period; the duration depends on the configured receiver.",
          "Use Stop search to end it early. If a stop cannot be confirmed, the discovery window still expires automatically."
        ],
        "warning": "This starts passive discovery at the facility receiver. It does not authorize ongoing collection from every device found.",
        "expected": "The page shows a search in progress, a completed result list, or a receiver error. A search result is not yet saved telemetry."
      },
      {
        "id": "radio-identify-candidate",
        "title": "Compare the candidate with your physical sensor",
        "instructions": [
          "For each result, read its name, device ending, signal and sample measurements.",
          "Compare those details with the actual sensor or controller before selecting Select followed by its name. A name or a strong signal alone is not proof of ownership.",
          "Encrypted, unsupported or event-only sources show an explanation rather than a link action. Do not choose an unrelated supported device simply because the intended one is unavailable."
        ],
        "expected": "The link form opens for the exact supported candidate you reviewed. Unsupported devices remain unavailable for connection."
      },
      {
        "id": "radio-assign-location",
        "title": "Name the sensor and choose its real location",
        "instructions": [
          "Enter a Device name that operators will recognize and choose the active Room containing the sensor.",
          "Select Zone (optional) when its placement is known. No zone assigned means only the room association is known, not that the sensor represents every part of it.",
          "If room zones cannot be loaded, refresh before linking. Select Cancel to leave without approving this candidate."
        ],
        "fields": [
          {
            "label": "Device name",
            "requirement": "Required, at most 64 characters.",
            "guidance": "Use a familiar equipment or placement name, not a credential.",
            "example": "Flower room bench A sensor"
          },
          {
            "label": "Room",
            "requirement": "Required active room.",
            "guidance": "Choose the room where the physical sensor is located."
          },
          {
            "label": "Zone (optional)",
            "requirement": "Optional after choosing a room.",
            "guidance": "Choose the actual sub-area when known. Leave it unassigned rather than guessing."
          }
        ],
        "expected": "The form identifies the intended sensor, room and optional zone. Collection is not approved until the ownership confirmation and Connect sensor action."
      },
      {
        "id": "radio-approve-link",
        "title": "Approve collection from this sensor",
        "instructions": [
          "Read and select This is my facility’s sensor and I authorize read-only collection after verifying ownership and location.",
          "Select Connect sensor once. Wait for the confirmation rather than repeatedly clicking after a slow response.",
          "If linking was not confirmed, refresh Linked sensors before another attempt. An expired candidate requires a new search."
        ],
        "warning": "This saves the approved sensor link and its location. Discovery samples are not backfilled into history; the system waits for a new post-approval reading.",
        "expected": "The sensor appears in Linked sensors. Linked. Waiting for a new reading means approval is saved but a new reception has not yet established collection."
      },
      {
        "id": "radio-check-saved-reading",
        "title": "Verify a new saved reception",
        "instructions": [
          "Read the linked sensor’s status and Last saved reception. Receiving readings appears only after the system has saved a new reading.",
          "Select Open Room 360 and inspect the source, measurement, unit, freshness and room context. Needs review, stale, receiver-unavailable and storage/mapping-paused states are not healthy readings.",
          "Remember that times reflect reception at the facility PC. Broadcast identity is not cryptographically verified, and missed transmissions cannot automatically be recovered."
        ],
        "expected": "Linked status and room evidence separately show what has actually been saved, or explicitly report why collection or a current value is unavailable."
      },
      {
        "id": "radio-disconnect-reviewed",
        "title": "Stop collection without removing its history",
        "instructions": [
          "In Linked sensors, expand Disconnect sensor for the exact device.",
          "Read the explanation, then choose Confirm disconnect followed by its name.",
          "Check the updated status. If disconnect was not confirmed, refresh the device before retrying."
        ],
        "warning": "Disconnect stops new collection for this link and preserves existing evidence. It does not turn off the physical sensor or erase recorded observations.",
        "expected": "The linked device reports Disconnected while its previous evidence remains available."
      }
    ],
    "completion": [
      "The approved source is assigned to the correct room and optional zone. A successful link is distinguished from a new saved reading.",
      "Room 360 has been checked for the individual source. No equipment-control or universal compatibility claim is inferred from discovery."
    ],
    "troubleshooting": [
      {
        "symptom": "This facility has no configured receiver.",
        "resolution": "Have the authorized host administrator check receiver configuration for this exact facility. A browser or phone does not supply the facility’s receiver automatically."
      },
      {
        "symptom": "No supported broadcasts were found.",
        "resolution": "Check that the intended sensor is awake and within range of the configured receiver. Verify its supported broadcast format. Do not assume that matching a frequency proves compatibility."
      },
      {
        "symptom": "An encrypted or unsupported source appears.",
        "resolution": "Use a separately supported pairing or export/integration path. This screen cannot decode unsupported formats or bypass encryption."
      },
      {
        "symptom": "The device is linked but is still waiting.",
        "resolution": "Wait for a new post-approval broadcast and inspect receiver/storage status. The discovery sample is deliberately not treated as a saved reading."
      },
      {
        "symptom": "The reading is stale or needs review.",
        "resolution": "Open Room 360 and inspect the exact source, mapping and freshness. Do not treat a stored link as proof of ongoing collection."
      }
    ],
    "sourceFiles": [
      "frontend/src/components/CultivationRadioSetup.tsx",
      "frontend/src/components/CultivationConnections.tsx",
      "backend/app/routers/cultivation_radio.py",
      "modules/cultivation/radio/service.py",
      "modules/cultivation/radio/runtime.py"
    ]
  }
};
