import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL ?? "";
// Modern Supabase projects expose a publishable key. Older DoobieLogic local
// workspaces may still carry the legacy anon-key variable. Both are normal
// client-side Auth keys; accepting the legacy name prevents a local login
// regression without exposing or requiring a service-role credential.
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? import.meta.env.VITE_SUPABASE_ANON_KEY ?? "";
export const authConfigured = Boolean(url && key);
export const supabase = authConfigured ? createClient(url, key, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } }) : null;
