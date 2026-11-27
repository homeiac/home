FROM alpine:3.24.0@sha256:a2d49ea686c2adfe3c992e47dc3b5e7fa6e6b5055609400dc2acaeb241c829f4
RUN apk add --no-cache github-cli git ca-certificates \
    && adduser -D -u 10001 worker
USER 10001:10001
ENV HOME=/tmp/home GH_CONFIG_DIR=/tmp/gh GH_PROMPT_DISABLED=1
WORKDIR /work
CMD ["sleep", "3600"]
