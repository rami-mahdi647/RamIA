FROM node:20-slim
WORKDIR /app

# Instala dependencias sin dev (ajusta si tu build necesita devDeps)
COPY package*.json ./
RUN npm ci --omit=dev

COPY . .
ENV NODE_ENV=production
# Si tu app necesita build, descomenta la línea siguiente
# RUN npm run build

# Ajusta el entrypoint a tu servidor real
EXPOSE 3000
CMD ["node", "dist/server.js"]
