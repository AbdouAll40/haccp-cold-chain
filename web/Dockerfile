# Stage 1: download the pinned front-end libraries (Chart.js, Leaflet)
FROM node:20-alpine AS deps
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Stage 2: serve the static dashboard with nginx (no Node.js in the final image)
FROM nginx:1.29-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html app.js style.css /usr/share/nginx/html/
COPY --from=deps /build/node_modules/chart.js/dist/chart.umd.js /usr/share/nginx/html/vendor/chart.umd.js
COPY --from=deps /build/node_modules/leaflet/dist/ /usr/share/nginx/html/vendor/leaflet/
EXPOSE 80
HEALTHCHECK --interval=10s --timeout=5s --retries=5 CMD wget -q --spider http://localhost/healthz || exit 1
