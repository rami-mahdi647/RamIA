FROM node:20-slim
WORKDIR /srv
COPY package.json package-lock.json* ./
RUN npm ci || npm install
COPY . .
EXPOSE 8787
CMD ["npm","start"]
