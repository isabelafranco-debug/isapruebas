FROM node:22.16.0-alpine AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
ARG VITE_MAP_STYLE=https://tiles.openfreemap.org/styles/liberty
ENV VITE_MAP_STYLE=$VITE_MAP_STYLE
RUN npm run build

FROM nginx:1.28.0-alpine
COPY web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
