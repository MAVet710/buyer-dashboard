import { InventoryTransferManager } from "../components/InventoryTransferManager";

export function InventoryTransfersPage({ operation }: { operation: "retail" | "production" }) {
  return <InventoryTransferManager operation={operation} packages={[]} embedded />;
}
