# PLAYWRIGHT_VERSION 必須與下方映像 tag 一致：映像只內建該版本的瀏覽器，
# @playwright/test 若裝到更新版會找不到對應的 chromium 而全部失敗。
ARG PLAYWRIGHT_VERSION=1.63.0
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble
ARG PLAYWRIGHT_VERSION
WORKDIR /app
COPY package.json bun.lock ./
RUN npm install --save-dev @playwright/test@${PLAYWRIGHT_VERSION}
COPY playwright.config.ts ./
COPY e2e/ ./e2e/
ENV BASE_URL=http://frontend:80
ENV API_URL=http://backend:8080
CMD ["npx", "playwright", "test"]
