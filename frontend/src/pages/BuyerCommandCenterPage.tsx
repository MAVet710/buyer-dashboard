import { BuyerLegacyOverview } from "../components/BuyerLegacyOverview";
import { BuyerOperationsPage } from "./BuyerOperationsPage";

export function BuyerCommandCenterPage({ onNavigate }: { onNavigate: (page: string) => void }) {
  return <>
    <BuyerLegacyOverview />
    <BuyerOperationsPage onNavigate={onNavigate} />
  </>;
}
