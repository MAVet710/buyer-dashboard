import { PlantInventory } from "../components/PlantInventory";
import { PostHarvestHandoffSummary } from "../components/PostHarvestHandoffSummary";
import { CultivationEnvironmentPanel } from "../components/CultivationEnvironmentPanel";
import { CultivationIntelligenceWorkspace } from "../components/CultivationIntelligenceWorkspace";

export function CultivationOpsPage({ onNavigate, initialPlantId = "", initialRoomId = "", initialCycleId = "", initialTelemetryId = "" }: { initialPlantId?: string; initialRoomId?: string; initialCycleId?: string; initialTelemetryId?: string; onNavigate: (page: string) => void }) {
  return <div className="page cultivation-ops-page">
    <div className="page-heading">
      <div>
        <div className="eyebrow">CULTIVATION OPS · GROW OPERATIONS</div>
        <h1>Cultivation</h1>
        <p>Run rooms, plants and groups, nursery work, harvests, cultivation costs, yield, regulatory health, and plant lineage from the living grow workspace.</p>
      </div>
      <span className="access-badge">Grow workspace</span>
    </div>
    <CultivationIntelligenceWorkspace key={JSON.stringify([initialRoomId, initialCycleId, initialTelemetryId])} initialRoomId={initialTelemetryId ? "" : initialRoomId} initialCycleId={initialCycleId} />
    <PostHarvestHandoffSummary onOpen={() => onNavigate("Post-Harvest")} />
    <PlantInventory initialPlantId={initialPlantId} />
    <CultivationEnvironmentPanel initialRoomId={initialRoomId} initialExceptionId={initialTelemetryId} />
  </div>;
}
