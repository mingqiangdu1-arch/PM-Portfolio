FROM node:24.14.1-bookworm-slim AS build

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH

RUN corepack enable && corepack prepare pnpm@9.12.3 --activate

WORKDIR /app

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY packages/design-tokens/package.json packages/design-tokens/package.json

RUN pnpm install --frozen-lockfile

COPY apps/web apps/web
COPY packages/design-tokens packages/design-tokens

ARG NEXT_PUBLIC_APP_ENV=production
ARG NEXT_PUBLIC_API_MODE=real
ARG NEXT_PUBLIC_API_BASE_URL

ENV NEXT_PUBLIC_APP_ENV=$NEXT_PUBLIC_APP_ENV \
    NEXT_PUBLIC_API_MODE=$NEXT_PUBLIC_API_MODE \
    NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN pnpm build

FROM node:24.14.1-bookworm-slim AS runtime

ENV NODE_ENV=production
ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH

RUN corepack enable && corepack prepare pnpm@9.12.3 --activate && \
    groupadd --system --gid 1001 nodejs && \
    useradd --system --uid 1001 --gid nodejs nextjs

WORKDIR /app

COPY --from=build --chown=nextjs:nodejs /app /app

USER nextjs

EXPOSE 3000

CMD ["pnpm", "--filter", "@aipdv/web", "start", "--hostname", "0.0.0.0", "--port", "3000"]
