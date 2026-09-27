export type HelpCapture = {
  src: string; alt: string; caption: string; appPath: string;
  releaseSha: string; capturedAt: string;
};
const reference = (name: string, alt: string, caption: string, appPath: string): HelpCapture => ({
  src: `/help/screens/${name}.webp`, alt, caption: `${caption} Reference capture: September 25, 2026.`,
  appPath, releaseSha: '2e2626dc65f2b45229f1a4b10deb9802f8a65997', capturedAt: '2026-09-25',
});
// Use actual inspected captures, identified by stable step IDs, not array positions.
// A screenshot is supporting evidence, not proof that every action was executed.
export const helpStepCaptures: Record<string, Record<string, HelpCapture[]>> = {
  '/help/inventory/receiving': {'receiving-open-queue': [reference('inventory-receiving-guide',
    'Receive Inventory window showing the Inbound Queue',
    'Open Receive inventory to reach the Inbound Queue. This demonstration has no pending inbound transfers.', '/inventory')]},
  '/help/inventory/audits': {'audit-start-scope': [reference('inventory-audits-guide',
    'Retail Scan Audit with Start New Audit and saved audits',
    'Start New Audit opens the setup controls. Existing sessions have their own Open button; resume one rather than duplicating it.', '/inventory/audits')]},
  '/help/buying/purchase-orders': {'po-check-existing': [reference('buying-purchase-orders-guide',
    'Purchase Orders workspace and existing purchase-order list',
    'Check the saved orders before starting another draft for the same delivery.', '/buying/purchase-orders')]},
  '/help/package-studio': {'choose-package-action': [reference('package-studio-guide',
    'Package Studio with Breakdown selected and a source package',
    'Package action determines the form you will complete. This example has Breakdown selected; choosing an action has not posted a transformation.', '/production/package-studio')]},
  '/help/wholesale/accounting': {'review-wholesale-ar': [reference('wholesale-accounting-guide',
    'Wholesale Accounting summary of receivables, overdue balances and payments',
    'Use the Accounting tab to find the balance that needs investigation, then open the underlying order and invoice.', '/wholesale')]},
  '/help/wholesale/storefront': {'save-storefront-foundation': [reference('wholesale-storefront-guide',
    'Storefront foundation fields for brand, subdomain and customer-facing copy',
    'The foundation form holds storefront identity and copy. Saving this form and publishing a design are separate actions.', '/wholesale')]},
  '/help/compliance/advanced-labelguard': {'select-advanced-inventory-package': [reference('compliance-label-studio-guide',
    'Advanced LabelGuard and templates tab in Label Studio',
    'Choose Advanced LabelGuard & templates for the testing-label workflow. The separate Create labels tab is for finished-product labels.', '/compliance/labels')]},
  '/help/cultivation/room-360': {'read-latest-sensors': [{
    src: '/help/screens/room-360-reference-20260926.webp',
    alt: 'Room 360 Environment tab with a sensor whose current value is Unknown',
    caption: 'Environment shows each source separately. In this actual release-test capture, the source is present but its current value is Unknown. That is not a healthy measurement or a zero.',
    appPath: '/cultivation', releaseSha: '7ff2dc921a69cf82419d4cab8d27ebe50ed7567c', capturedAt: '2026-09-26',
  }]},
  '/help/cultivation/crop-cycle-360': {'review-cycle-crop': [{
    src: '/help/screens/cycle-360-reference-20260926.webp',
    alt: 'Crop Cycle 360 Crop tab with recipe, membership and harvest-link status',
    caption: 'The Crop tab separates recipe, plant membership and harvest links. This synthetic test cycle has a recipe, but no membership or harvest evidence yet; a room alone does not establish either relationship.',
    appPath: '/cultivation', releaseSha: '7ff2dc921a69cf82419d4cab8d27ebe50ed7567c', capturedAt: '2026-09-26',
  }]},
};
const currentCaptures: Record<string, Record<string, HelpCapture[]>> = {
  "/help/inventory/audits": {
    "audit-start-scope": [
      {
        "src": "/help/screens/audit-start-scope-20260926.webp",
        "alt": "Choose the scope before starting a new audit. Opening these controls has not saved another audit session.",
        "caption": "Choose the scope before starting a new audit. Opening these controls has not saved another audit session. Captured September 26, 2026.",
        "appPath": "/inventory/audits",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:24:44.032Z"
      }
    ]
  },
  "/help/inventory/receiving": {
    "receiving-manual-fallback": [
      {
        "src": "/help/screens/receiving-manual-fallback-20260926.webp",
        "alt": "Manual receiving fields before submission. This screenshot does not show a completed receipt or Metrc acceptance.",
        "caption": "Manual receiving fields before submission. This screenshot does not show a completed receipt or Metrc acceptance. Captured September 26, 2026.",
        "appPath": "/inventory",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:14:47.010Z"
      }
    ]
  },
  "/help/cultivation/room-360": {
    "read-latest-sensors": [
      {
        "src": "/help/screens/read-latest-sensors-20260926.webp",
        "alt": "Room 360 Environment shows the sources available for this room. Unknown means a current value is not established.",
        "caption": "Room 360 Environment shows the sources available for this room. Unknown means a current value is not established. Captured September 26, 2026.",
        "appPath": "/cultivation?room=c9b82677-88a2-4b49-a254-827b267dfd53",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:15:13.706Z"
      }
    ],
    "review-room-operations": [
      {
        "src": "/help/screens/review-room-operations-20260926.webp",
        "alt": "The Operations tab keeps the room zones, events and linked work together.",
        "caption": "The Operations tab keeps the room zones, events and linked work together. Captured September 26, 2026.",
        "appPath": "/cultivation?room=c9b82677-88a2-4b49-a254-827b267dfd53",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:15:14.593Z"
      }
    ]
  },
  "/help/cultivation/crop-cycle-360": {
    "create-crop-cycle": [
      {
        "src": "/help/screens/create-crop-cycle-20260926.webp",
        "alt": "Cycle setup before Save cycle. Select the correct recipe and dates; opening this form has not created a crop cycle.",
        "caption": "Cycle setup before Save cycle. Select the correct recipe and dates; opening this form has not created a crop cycle. Captured September 26, 2026.",
        "appPath": "/cultivation",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:15:26.319Z"
      }
    ],
    "review-cycle-crop": [
      {
        "src": "/help/screens/review-cycle-crop-20260926.webp",
        "alt": "Crop Cycle 360 separates membership, recipe and harvest evidence. Missing relationships are not inferred.",
        "caption": "Crop Cycle 360 separates membership, recipe and harvest evidence. Missing relationships are not inferred. Captured September 26, 2026.",
        "appPath": "/cultivation?cycle=33d3864a-693a-4446-9050-b09d016f2622",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:15:41.494Z"
      }
    ],
    "record-cycle-occupancy": [
      {
        "src": "/help/screens/record-cycle-members-20260926.webp",
        "alt": "Manage holds the membership and occupancy controls. Each relationship must be explicitly recorded.",
        "caption": "Manage shows the room/stage interval controls for this example cycle. The existing occupancy and a new interval are separate records. No occupancy was changed for this screenshot. Captured September 26, 2026.",
        "appPath": "/cultivation?cycle=33d3864a-693a-4446-9050-b09d016f2622",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:15:42.338Z"
      }
    ]
  },
  "/help/cultivation/connections": {
    "create-file-configuration": [
      {
        "src": "/help/screens/create-file-configuration-20260926.webp",
        "alt": "Choose File import for a reviewed export. This is connection setup, not an active vendor integration.",
        "caption": "Choose File import for a reviewed export. This is connection setup, not an active vendor integration. Captured September 26, 2026.",
        "appPath": "/settings/integrations?provider=cultivation",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:16:02.012Z"
      }
    ]
  },
  "/help/doobie-agent": {
    "choose-specialist-question": [
      {
        "src": "/help/screens/choose-specialist-question-20260926.webp",
        "alt": "Choose the specialist for the work you are doing, then check provider readiness. No question has been submitted in this screenshot.",
        "caption": "Choose the specialist for the work you are doing, then check provider readiness. No question has been submitted in this screenshot. Captured September 26, 2026.",
        "appPath": "/home",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:24:56.975Z"
      }
    ]
  },
  "/help/cultivation/push-setup": {
    "push-choose-mode": [
      {
        "src": "/help/screens/push-choose-mode-20260926.webp",
        "alt": "Normalized JSON push settings before creation. The optional intervals describe connection delivery, not agronomic targets or the health of every sensor.",
        "caption": "Normalized JSON push settings before creation. The optional intervals describe connection delivery, not agronomic targets or the health of every sensor. Captured September 26, 2026.",
        "appPath": "/settings/integrations?provider=cultivation",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:25:06.008Z"
      }
    ]
  },
  "/help/cultivation/imports": {
    "supply-import-mappings": [
      {
        "src": "/help/screens/supply-import-mappings-20260926.webp",
        "alt": "Map the original channel, measurement and unit to the normalized measurement. This is a synthetic preview example, not committed telemetry.",
        "caption": "Map the original channel, measurement and unit to the normalized measurement. This is a synthetic preview example, not committed telemetry. Captured September 26, 2026.",
        "appPath": "/settings/integrations?provider=cultivation",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:25:19.593Z"
      }
    ],
    "preview-measurement-import": [
      {
        "src": "/help/screens/preview-measurement-import-20260926.webp",
        "alt": "Server preview reports values, destinations and validation status. A preview does not commit readings, and an unassigned room is not inferred from the current facility.",
        "caption": "Server preview reports values, destinations and validation status. A preview does not commit readings, and an unassigned room is not inferred from the current facility. Captured September 26, 2026.",
        "appPath": "/settings/integrations?provider=cultivation",
        "releaseSha": "e2fd6bebb97173998d93a2178a997969bdf93372",
        "capturedAt": "2026-09-26T22:25:22.165Z"
      }
    ]
  }
};
for (const [path, steps] of Object.entries(currentCaptures)) {
  helpStepCaptures[path] = {...helpStepCaptures[path], ...steps};
}
const latestCaptures: Record<string, Record<string, HelpCapture[]>> = {
  "/help/inventory/receiving": {
    "receiving-open-queue": [
      {
        "src": "/help/screens/receiving-open-queue-current-20260926.webp",
        "alt": "Receive Inventory Inbound Queue in DoobieLogic Sandbox with provider access disabled",
        "caption": "The sandbox queue is open, but provider reads are disabled and no pending transfers are shown. Verify the correct facility connection before selecting a real shipment. Captured September 26, 2026.",
        "appPath": "/inventory",
        "releaseSha": "fd91e4f7991e3d65f7adb81cd0765f0d9e3395bc",
        "capturedAt": "2026-09-27T01:30:32.012Z"
      }
    ]
  },
  "/help/cultivation/nearby-sensors": {
    "radio-check-receiver": [
      {
        "src": "/help/screens/radio-check-receiver-current-20260926.webp",
        "alt": "Nearby-sensor setup reports the facility receiver state before any search. A configured receiver or visible setup is not proof that physical equipment has been discovered. No search or sensor approval was performed for this capture.",
        "caption": "Nearby-sensor setup reports the facility receiver state before any search. A configured receiver or visible setup is not proof that physical equipment has been discovered. No search or sensor approval was performed for this capture. Captured September 26, 2026.",
        "appPath": "/settings/integrations?provider=cultivation",
        "releaseSha": "fd91e4f7991e3d65f7adb81cd0765f0d9e3395bc",
        "capturedAt": "2026-09-27T01:31:14.277Z"
      }
    ]
  }
};
for (const [path, steps] of Object.entries(latestCaptures)) {
  helpStepCaptures[path] = {...helpStepCaptures[path], ...steps};
}
export function capturesForStep(path: string, stepId: string): HelpCapture[] {
  return helpStepCaptures[path]?.[stepId] ?? [];
}
