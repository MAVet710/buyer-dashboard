import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CultivationEnvironmentPanel } from "../../src/components/CultivationEnvironmentPanel";
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
createRoot(document.getElementById("root")!).render(React.createElement(QueryClientProvider, { client }, React.createElement(CultivationEnvironmentPanel)));
