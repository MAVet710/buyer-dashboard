import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SecurityOverview } from "../../src/components/SecurityOverview";
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
createRoot(document.getElementById("root")!).render(React.createElement(QueryClientProvider, { client }, React.createElement(SecurityOverview)));
