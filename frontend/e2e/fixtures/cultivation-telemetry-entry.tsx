import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CultivationEnvironmentPanel } from "../../src/components/CultivationEnvironmentPanel";
import "../../src/styles.css";
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const params = new URLSearchParams(window.location.search);
createRoot(document.getElementById("root")!).render(
  React.createElement(QueryClientProvider, { client },
    React.createElement(CultivationEnvironmentPanel, {
      initialRoomId: params.get("room") || "",
      initialExceptionId: params.get("telemetry") || "",
    }),
  ),
);
