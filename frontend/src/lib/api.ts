import { supabase } from "./supabase";
const API_URL = import.meta.env.VITE_API_URL ?? "";

export function errorMessage(payload: { detail?: unknown; error?: { message?: string } }, status: number): string {
  if (payload.error?.message) return payload.error.message;
  if (typeof payload.detail === "string") return payload.detail;
  return `Request failed (${status})`;
}

export function trialToken(): string { return sessionStorage.getItem("buyer-dash-trial-token") ?? ""; }
export function clearTrialSession(): void { sessionStorage.removeItem("buyer-dash-trial-token"); sessionStorage.removeItem("buyer-dash-trial-expires"); }

export function buyerDataMode(): "Uploads" | "Dutchie Live" {
  return localStorage.getItem("buyer-dash-data-mode") === "Dutchie Live" ? "Dutchie Live" : "Uploads";
}

async function requestHeaders(json = false): Promise<Record<string, string>> {
  const session = (await supabase?.auth.getSession())?.data.session;
  const token = session?.access_token;
  const trial = !token ? trialToken() : "";
  const metadata = session?.user.app_metadata ?? {};
  return {
    ...(json ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(trial ? { "X-Trial-Token": trial } : {}),
    "X-Organization-Id": localStorage.getItem("buyer-dash-organization") ?? metadata.organization_id ?? import.meta.env.VITE_ORGANIZATION_ID ?? "",
    "X-Facility-Id": localStorage.getItem("buyer-dash-facility") ?? metadata.facility_id ?? import.meta.env.VITE_FACILITY_ID ?? "",
    "X-DoobieLogic-Data-Mode": buyerDataMode(),
    ...(token || trial ? {} : { "X-User-Id": "web-local-developer", "X-User-Role": "admin" }),
  };
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { signal, headers: await requestHeaders() });
  if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(errorMessage(payload, response.status)); }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { method: "POST", headers: await requestHeaders(true), body: JSON.stringify(body) });
  if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(errorMessage(payload, response.status)); }
  return response.json() as Promise<T>;
}

export async function apiPostForm<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { method: "POST", headers: await requestHeaders(), body });
  if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(errorMessage(payload, response.status)); }
  return response.json() as Promise<T>;
}

export async function apiDownload(path: string, body?: unknown): Promise<Blob> {
  // Streamlit keeps a generated White Label/Repack payload in session state so
  // it can join the Retail/Company executive packs. Preserve that session-level
  // report availability after the web user generates the same report.
  if (path === "/api/v1/executive-reports/white-label.pdf" && body !== undefined) {
    try { sessionStorage.setItem("white-label-current-report-payload", JSON.stringify(body)); } catch { /* storage may be unavailable */ }
  }
  const response = await fetch(`${API_URL}${path}`, { method: body === undefined ? "GET" : "POST", headers: await requestHeaders(body !== undefined), ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(errorMessage(payload, response.status)); }
  return response.blob();
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
}
