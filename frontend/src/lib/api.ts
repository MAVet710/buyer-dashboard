import { supabase } from "./supabase";
const API_URL = import.meta.env.VITE_API_URL ?? "";

export function errorMessage(payload: { detail?: unknown; error?: { message?: string } }, status: number): string {
  if (payload.error?.message) return payload.error.message;
  if (typeof payload.detail === "string") return payload.detail;
  return `Request failed (${status})`;
}

async function requestHeaders(json = false): Promise<Record<string, string>> {
  const session = (await supabase?.auth.getSession())?.data.session; const token = session?.access_token; const metadata = session?.user.app_metadata ?? {};
  return { ...(json ? { "Content-Type": "application/json" } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}), "X-Organization-Id": localStorage.getItem("buyer-dash-organization") ?? metadata.organization_id ?? import.meta.env.VITE_ORGANIZATION_ID ?? "", "X-Facility-Id": localStorage.getItem("buyer-dash-facility") ?? metadata.facility_id ?? import.meta.env.VITE_FACILITY_ID ?? "", ...(token ? {} : { "X-User-Id": "web-local-developer", "X-User-Role": "admin" }) };
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    signal,
    headers: await requestHeaders(),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(errorMessage(payload, response.status));
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: await requestHeaders(true),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(errorMessage(payload, response.status));
  }
  return response.json() as Promise<T>;
}

export async function apiPostForm<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { method: "POST", headers: await requestHeaders(), body });
  if (!response.ok) { const payload = await response.json().catch(() => ({})); throw new Error(errorMessage(payload, response.status)); }
  return response.json() as Promise<T>;
}
