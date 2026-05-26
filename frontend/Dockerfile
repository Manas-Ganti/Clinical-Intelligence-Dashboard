# Build the static bundle, then serve it with `vite preview`.
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# VITE_API_URL is inlined at build time; the browser (on the host) calls the
# API directly at this URL, which the backend's CORS config allows.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

EXPOSE 5173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
