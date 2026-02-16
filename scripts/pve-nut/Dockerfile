# Pin to specific digest for reproducibility (alpine:3.19)
FROM alpine:3.19@sha256:6baf43584bcb78f2e5847d1de515f23499913ac9f12bdf834811a3145eb11ca1

# Install required packages
RUN apk add --no-cache \
    openssh-client \
    bash \
    curl \
    jq

WORKDIR /app

# Copy all deployment files
COPY deploy.sh /app/
COPY scripts/ /app/scripts/
COPY configs/ /app/configs/

# Make scripts executable
RUN chmod +x /app/deploy.sh && \
    find /app/scripts -name "*.sh" -exec chmod +x {} \;

ENTRYPOINT ["/app/deploy.sh"]
