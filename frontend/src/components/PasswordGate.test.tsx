import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PasswordGate } from "./PasswordGate";
import { WorkspaceTimeoutError } from "../lib/workspaceRecovery";

const state = vi.hoisted(() => ({ query: {} as Record<string, unknown> }));
vi.mock("@tanstack/react-query", () => ({ useQuery: () => state.query, useQueryClient: () => ({ invalidateQueries: vi.fn() }) }));
vi.mock("../lib/supabase", () => ({ supabase: null }));
const render = () => renderToStaticMarkup(createElement(PasswordGate, { userId: "user-a" }, createElement("div", null, "Operator unsaved workspace")));
beforeEach(() => { state.query = { data: { user: { must_change_password: false } }, isError: true, error: new WorkspaceTimeoutError(), refetch: vi.fn() }; });

describe("workspace gate availability boundary", () => {
  it("keeps verified workspace content during a transient background failure", () => {
    const html = render();
    expect(html).toContain("Operator unsaved workspace");
    expect(html).toContain("Connection interrupted");
    expect(html).not.toContain("Access context unavailable");
  });
  it("does not enter a workspace before the first successful access check", () => {
    state.query.data = undefined;
    expect(render()).not.toContain("Operator unsaved workspace");
    expect(render()).toContain("Access context unavailable");
  });
  it("blocks real access denials even with earlier cached data", () => {
    state.query.error = { status: 403, message: "Access revoked" };
    expect(render()).not.toContain("Operator unsaved workspace");
    expect(render()).toContain("Access revoked");
  });
  it("still enforces mandatory password changes during an outage", () => {
    state.query.data = { user: { must_change_password: true } };
    expect(render()).toContain("Create your private password");
    expect(render()).not.toContain("Operator unsaved workspace");
  });
});
