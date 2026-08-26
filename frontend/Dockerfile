# --- dev target: Vite dev server with hot reload, used by docker-compose ---
FROM node:22-slim AS dev
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# --- build target: production static bundle ---
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vite inlines VITE_* env vars into the built JS at build time, not
# runtime — empty by default so a same-origin reverse proxy (see
# docker-compose.prod.yml / Caddyfile) is the default assumption; pass
# --build-arg VITE_API_BASE_URL=https://api.example.com only if the API
# is actually served from a different origin than the frontend.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# --- production target: static bundle served by nginx ---
# Runs as nginx:1.27-alpine's built-in unprivileged `nginx` user (not
# root) on port 8080, not the privileged 80 — see nginx.conf and DEF.md §
# Phase 14. Not currently used by docker-compose.yml (which runs the dev
# target for hot-reload); present for Phase 15's eventual deployment path.
FROM nginx:1.31-alpine AS production
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
RUN chown -R nginx:nginx /usr/share/nginx/html
USER nginx
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
