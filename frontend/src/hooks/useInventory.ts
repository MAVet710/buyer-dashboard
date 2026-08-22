import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import type { InventoryResponse } from "../types/inventory";

export type InventoryFilters = {
  operation: "retail" | "production";
  search: string;
  status: string;
  materialType: string;
  location: string;
  source: string;
  view: string;
};

export function useInventory(filters: InventoryFilters) {
  return useQuery({
    queryKey: ["inventory", filters],
    queryFn: ({ signal }) => {
      const params = new URLSearchParams({
        search: filters.search,
        status: filters.status,
        material_type: filters.materialType,
        location: filters.location,
        source: filters.source,
        view: filters.view,
      });
      return apiGet<InventoryResponse>(`/api/v1/inventory/${filters.operation}/packages?${params}`, signal);
    },
  });
}
