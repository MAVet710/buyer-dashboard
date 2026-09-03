import { PostHarvestBoard } from "../components/PostHarvestBoard";

export function PostHarvestPage() {
  return <div className="page post-harvest-page">
    <div className="page-heading">
      <div>
        <div className="eyebrow">GROW OPERATIONS · POST-HARVEST</div>
        <h1>Post-Harvest</h1>
        <p>Run drying, bucking, trimming, curing, testing hold, final reconciliation and release in a dedicated grow workspace without breaking the lineage that started at harvest.</p>
      </div>
      <span className="access-badge">Post-Harvest workspace</span>
    </div>
    <PostHarvestBoard />
  </div>;
}
