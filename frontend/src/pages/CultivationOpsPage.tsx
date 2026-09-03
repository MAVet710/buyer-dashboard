import { PlantInventory } from "../components/PlantInventory";
import { PostHarvestHandoffSummary } from "../components/PostHarvestHandoffSummary";

export function CultivationOpsPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  return <div className="page cultivation-ops-page">
    <div className="page-heading">
      <div>
        <div className="eyebrow">GROW OPERATIONS</div>
        <h1>Cultivation</h1>
        <p>Run rooms, plants and groups, nursery work, harvests, cultivation costs, yield, regulatory health, and plant lineage from the living grow workspace.</p>
      </div>
      <span className="access-badge">Grow workspace</span>
    </div>
    <PostHarvestHandoffSummary onOpen={() => onNavigate("Post-Harvest")} />
    <PlantInventory />
  </div>;
}
