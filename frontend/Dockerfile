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
RUN npm run build

# --- production target: static bundle served by nginx ---
# Runs as nginx:1.27-alpine's built-in unprivileged `nginx` user (not
# root) on port 8080, not the privileged 80 — see nginx.conf and DEF.md §
# Phase 14. Not currently used by docker-compose.yml (which runs the dev
# target for hot-reload); present for Phase 15's eventual deployment path.
FROM nginx:1.27-alpine AS production
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
RUN chown -R nginx:nginx /usr/share/nginx/html
USER nginx
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
