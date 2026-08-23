import { BuyerOperationsPage } from "./BuyerOperationsPage";

export function BuyerCommandCenterPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  return <BuyerOperationsPage onNavigate={onNavigate} />;
}
