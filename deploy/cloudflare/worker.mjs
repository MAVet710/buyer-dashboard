const ORIGINS = Object.freeze({
  "doobielogic.io": "doobielogic-web-prod.onrender.com",
  "ops.doobielogic.io": "doobielogic-web-prod.onrender.com",
  "cowboykush.doobielogic.io": "doobielogic-web-prod.onrender.com",
  "api.doobielogic.io": "doobielogic-api-rc.onrender.com",
});

export default {
  async fetch(request) {
    const publicUrl = new URL(request.url);
    const origin = ORIGINS[publicUrl.hostname];
    if (!origin) return new Response("Unknown hostname", { status: 404 });
    if (publicUrl.protocol !== "https:") {
      publicUrl.protocol = "https:";
      return Response.redirect(publicUrl.href, 308);
    }
    const upstreamUrl = new URL(publicUrl);
    upstreamUrl.hostname = origin;
    upstreamUrl.port = "";
    const upstream = new Request(upstreamUrl, request);
    upstream.headers.set("Host", origin);
    upstream.headers.delete("Forwarded");
    upstream.headers.set("X-Forwarded-Host", publicUrl.hostname);
    upstream.headers.set("X-Forwarded-Proto", "https");
    const ip = request.headers.get("CF-Connecting-IP");
    upstream.headers.delete("X-Forwarded-For");
    if (ip) upstream.headers.set("X-Forwarded-For", ip);
    try {
      // Manual redirects prevent credentials being forwarded to another origin.
      // The backend remains responsible for CORS and all authorization decisions.
      const response = await fetch(upstream, {
        redirect: "manual",
        cache: "no-store",
        cf: { cacheTtl: -1, cacheEverything: false },
      });
      const result = new Response(response.body, response);
      const location = result.headers.get("Location");
      if (location) {
        const target = new URL(location, upstreamUrl);
        if (target.hostname === origin) {
          target.protocol = "https:";
          target.host = publicUrl.host;
          result.headers.set("Location", target.href);
        }
      }
      if (publicUrl.hostname === "api.doobielogic.io") {
        result.headers.set("Cache-Control", "no-store");
      }
      result.headers.set("X-DoobieLogic-Edge", "cloudflare-render-v1");
      return result;
    } catch {
      return new Response("Service temporarily unavailable. Please retry shortly.", {
        status: 502,
        headers: { "Cache-Control": "no-store", "Content-Type": "text/plain; charset=utf-8" },
      });
    }
  },
};
