FROM alpine:3.19

RUN apk add --no-cache \
    bash \
    curl \
    jq

WORKDIR /app

COPY update-model.sh check-ollama.sh test-inference.sh /app/

RUN chmod +x /app/*.sh

ENTRYPOINT ["/app/update-model.sh"]
