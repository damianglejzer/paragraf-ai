# Frontend image for the portable bundle: build with Node, serve with nginx.
# (On Vercel the frontend is built from source; this image is not used there.)

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Empty API URL: the browser calls /api on the same origin and nginx forwards it.
ENV VITE_API_URL=""
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
