# ── Stage 1 : build Angular ────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

# Installer les dépendances
COPY package*.json ./
RUN npm ci --silent

# Copier les sources et builder
COPY . .
RUN npm run build -- --configuration production

# ── Stage 2 : serveur Nginx ────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS runtime

# Supprimer la config par défaut
RUN rm /etc/nginx/conf.d/default.conf

# Config Nginx avec proxy vers le backend
COPY nginx.conf /etc/nginx/conf.d/mediflow.conf

# Copier le build Angular
COPY --from=builder /app/dist/frontend/browser /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
