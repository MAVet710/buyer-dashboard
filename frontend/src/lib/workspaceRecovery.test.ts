import { afterEach, describe, expect, it, vi } from "vitest";
import { abortable, isTransientWorkspaceError, retryWorkspace, workspaceAttempt, WorkspaceTimeoutError } from "./workspaceRecovery";

afterEach(() => vi.useRealTimers());

describe("workspace recovery", () => {
  it("allows a service waking for longer than the former 15 second limit", async () => {
    vi.useFakeTimers();
    const request = workspaceAttempt(() => new Promise(resolve => setTimeout(() => resolve("ready"), 25_000)));
    await vi.advanceTimersByTimeAsync(25_000);
    await expect(request).resolves.toBe("ready");
    expect(vi.getTimerCount()).toBe(0);
  });

  it("settles even if auth never resolves or observes cancellation", async () => {
    vi.useFakeTimers();
    const request = workspaceAttempt(() => new Promise(() => {}));
    const result = expect(request).rejects.toBeInstanceOf(WorkspaceTimeoutError);
    await vi.advanceTimersByTimeAsync(30_000);
    await result;
    expect(vi.getTimerCount()).toBe(0);
  });

  it("does not start a cancelled attempt", async () => {
    const controller = new AbortController(); controller.abort();
    const operation = vi.fn();
    await expect(workspaceAttempt(operation, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
    expect(operation).not.toHaveBeenCalled();
  });

  it("propagates cancellation while waiting for the SDK", async () => {
    const controller = new AbortController();
    const promise = abortable(() => new Promise(() => {}), controller.signal);
    controller.abort();
    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
  });

  it("only retries transient failures, at most twice", () => {
    for (const error of [new WorkspaceTimeoutError(), new TypeError("Failed to fetch"), { status: 503 }, { status: 429 }]) {
      expect(retryWorkspace(0, error)).toBe(true);
      expect(retryWorkspace(1, error)).toBe(true);
      expect(retryWorkspace(2, error)).toBe(false);
    }
    for (const status of [400, 401, 403, 404, 422]) expect(isTransientWorkspaceError({ status })).toBe(false);
    expect(isTransientWorkspaceError(new DOMException("Aborted", "AbortError"))).toBe(false);
  });
});
