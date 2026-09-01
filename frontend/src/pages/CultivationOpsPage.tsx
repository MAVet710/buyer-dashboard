import { PlantInventory } from "../components/PlantInventory";

export function CultivationOpsPage() {
  return <div className="page cultivation-ops-page">
    <div className="page-heading">
      <div>
        <div className="eyebrow">CULTIVATION OPS</div>
        <h1>Cultivation</h1>
        <p>Run rooms, plants and groups, nursery work, harvests, dry-down, cultivation costs, yield, regulatory health, and plant lineage from one dedicated grow workspace.</p>
      </div>
      <span className="access-badge">Grow workspace</span>
    </div>
    <PlantInventory />
  </div>;
}
