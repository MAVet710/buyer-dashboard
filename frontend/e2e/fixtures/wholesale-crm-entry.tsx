import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WholesaleCRMPanel } from "../../src/pages/WholesaleCRMPanel";
import "../../src/styles.css";
import "../../src/wholesale-ops.css";
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
createRoot(document.getElementById("root")!).render(React.createElement(QueryClientProvider, { client }, React.createElement(WholesaleCRMPanel, { pipeline: location.search.includes("pipeline") })));
