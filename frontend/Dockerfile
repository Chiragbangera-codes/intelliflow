# =============================================================================
# IntelliFlow AI — Frontend Dockerfile
#
# Multi-stage build:
#   base        — shared Node.js base
#   development — hot-reload dev server with volume mount
#   builder     — production build (Next.js standalone output)
#   production  — minimal runtime image using standalone output
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Base
# -----------------------------------------------------------------------------
FROM node:20-alpine AS base

# Enable corepack for consistent package manager versions
RUN corepack enable

WORKDIR /app

# -----------------------------------------------------------------------------
# Stage 2: Development
# -----------------------------------------------------------------------------
FROM base AS development

# Copy package files and install all dependencies (including devDependencies)
COPY package.json package-lock.json ./
RUN npm ci

# Source is mounted as a volume in docker-compose
EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
ENV NODE_ENV=development

CMD ["npm", "run", "dev"]

# -----------------------------------------------------------------------------
# Stage 3: Builder — builds the production Next.js output
# -----------------------------------------------------------------------------
FROM base AS builder

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Build the application
ENV NODE_ENV=production
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 4: Production — minimal runtime image using Next.js standalone output
# -----------------------------------------------------------------------------
FROM node:20-alpine AS production

WORKDIR /app

# Create non-root user for security
RUN addgroup --gid 1001 appgroup \
    && adduser --uid 1001 --ingroup appgroup --disabled-password appuser

# Copy only what's needed from the builder stage
COPY --from=builder --chown=appuser:appgroup /app/.next/standalone ./
COPY --from=builder --chown=appuser:appgroup /app/.next/static ./.next/static
COPY --from=builder --chown=appuser:appgroup /app/public ./public

USER appuser

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
ENV NODE_ENV=production

# Next.js standalone server entry point
CMD ["node", "server.js"]
