FROM node:22-alpine AS build
# Build from the repository root so both runtimes use the same shared definition.
WORKDIR /web/frontend
RUN corepack enable && corepack prepare pnpm@10.34.5 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
COPY shared/ /web/shared/
ARG VITE_API_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY
ARG VITE_ORGANIZATION_ID
ARG VITE_FACILITY_ID
ARG VITE_RELEASE_SHA=unknown
ENV VITE_API_URL=$VITE_API_URL \
    VITE_SUPABASE_URL=$VITE_SUPABASE_URL \
    VITE_SUPABASE_PUBLISHABLE_KEY=$VITE_SUPABASE_PUBLISHABLE_KEY \
    VITE_ORGANIZATION_ID=$VITE_ORGANIZATION_ID \
    VITE_FACILITY_ID=$VITE_FACILITY_ID \
    VITE_RELEASE_SHA=$VITE_RELEASE_SHA
RUN pnpm build \
    && printf '{"release_sha":"%s"}\n' "$VITE_RELEASE_SHA" > /web/frontend/dist/release.json

FROM nginx:1.31.4-alpine@sha256:db35bfc6b2951e7f8a72db5db120288c127ffaeeb4a6d4b95a26fead017d5913
# Keep the nginx runtime image pinned while applying every available Alpine
# security update published after that digest. The release gate scans this
# final image and fails on any remaining fixable HIGH/CRITICAL finding.
RUN apk upgrade --no-cache
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/frontend/dist /usr/share/nginx/html
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
