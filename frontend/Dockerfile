# Frontend : build puis copie du dist dans l'image nginx
FROM node:22-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# SPA : router en mode hash, index.html suffit
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
