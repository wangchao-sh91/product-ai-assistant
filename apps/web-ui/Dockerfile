FROM node:22-alpine

WORKDIR /app
ARG NPM_REGISTRY=https://registry.npmmirror.com
COPY package.json /app/package.json
RUN npm install \
  --registry="${NPM_REGISTRY}" \
  --fetch-timeout=60000 \
  --fetch-retries=3

COPY . /app

EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--port", "3000"]
