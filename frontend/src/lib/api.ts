import { supabase } from "./supabase";
const API_URL = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type ValidationIssue = { loc?: unknown; msg?: unknown; message?: unknown };
type ErrorPayload = { detail?: unknown; error?: { message?: string } };

function humanField(value: unknown): string {
  if (!Array.isArray(value)) return "";
  const parts = value.filter(part => part !== "body" && typeof part !== "number").map(part => String(part));
  const raw = parts.at(-1) ?? "";
  return raw.replaceAll("_", " ").replace(/\b\w/g, character => character.toUpperCase());
}

function validationDetails(detail: unknown): string {
  if (!Array.isArray(detail)) return "";
  const messages = detail.map(item => {
    if (!item || typeof item !== "object") return "";
    const issue = item as ValidationIssue;
    const field = humanField(issue.loc);
    const message = String(issue.msg ?? issue.message ?? "Invalid value").trim();
    return field ? `${field}: ${message}` : message;
  }).filter(Boolean);
  return [...new Set(messages)].join(" · ");
}

export function errorMessage(payload: ErrorPayload, status: number): string {
  // FastAPI returns useful field-level validation information in `detail`, while
  // our observability envelope also carries a generic `error.message`. Prefer
  // the actionable field errors so operators can fix a form instead of seeing
  // only "One or more request fields are invalid."
  const fieldErrors = validationDetails(payload.detail);
  if (fieldErrors) return fieldErrors;
  if (typeof payload.detail === "string" && payload.detail.trim()) return payload.detail;
  if (payload.error?.message) return payload.error.message;
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

async function authorizedFetch(path: string, makeInit: (headers: Record<string, string>) => RequestInit): Promise<Response> {
  let response = await fetch(`${API_URL}${path}`, makeInit(await requestHeaders()));
  // A restored browser session can briefly hold an expired Supabase JWT even
  // though the refresh token is still valid. Refresh once centrally so every
  // workspace does not have to implement its own login-recovery loop.
  if (response.status === 401 && supabase) {
    const refreshed = await supabase.auth.refreshSession();
    if (!refreshed.error && refreshed.data.session) {
      response = await fetch(`${API_URL}${path}`, makeInit(await requestHeaders()));
    }
  }
  return response;
}

async function throwResponseError(response: Response): Promise<never> {
  const payload = await response.json().catch(() => ({}));
  throw new ApiError(errorMessage(payload, response.status), response.status);
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await authorizedFetch(path, headers => ({ signal, headers }));
  if (!response.ok) return throwResponseError(response);
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const serialized = JSON.stringify(body);
  const response = await authorizedFetch(path, headers => ({ method: "POST", headers: { ...headers, "Content-Type": "application/json" }, body: serialized }));
  if (!response.ok) return throwResponseError(response);
  return response.json() as Promise<T>;
}

export async function apiPostForm<T>(path: string, body: FormData): Promise<T> {
  const response = await authorizedFetch(path, headers => ({ method: "POST", headers, body }));
  if (!response.ok) return throwResponseError(response);
  return response.json() as Promise<T>;
}

export async function apiDownload(path: string, body?: unknown): Promise<Blob> {
  // Streamlit keeps a generated White Label/Repack payload in session state so
  // it can join the Retail/Company executive packs. Preserve that session-level
  // report availability after the web user generates the same report.
  if (path === "/api/v1/executive-reports/white-label.pdf" && body !== undefined) {
    try { sessionStorage.setItem("white-label-current-report-payload", JSON.stringify(body)); } catch { /* storage may be unavailable */ }
  }
  const serialized = body === undefined ? undefined : JSON.stringify(body);
  const response = await authorizedFetch(path, headers => ({
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? headers : { ...headers, "Content-Type": "application/json" },
    ...(serialized === undefined ? {} : { body: serialized }),
  }));
  if (!response.ok) return throwResponseError(response);
  return response.blob();
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob); const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url);
}
