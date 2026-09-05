# Metrc Permission Evidence

Metrc employee permission introspection is optional evidence, not a prerequisite for facility discovery or initial regulatory hydration.

When `GET /employees/v2/permissions` succeeds for the configured employee identity, DoobieLogic stores the normalized provider-reported permission list as tenant/facility-scoped audit evidence. No API keys or encrypted credential material are written into the evidence payload.

If the permission endpoint is unavailable, forbidden, or cannot be persisted, normal authenticated provider reads remain governed by Metrc itself. DoobieLogic does not reinterpret that failure as globally invalid credentials and does not block otherwise-authorized module hydration.

Initial facility hydration therefore covers regulatory data resources only. Permission evidence is exposed separately as an optional capability check and may be refreshed whenever the connected employee has sufficient provider access.
