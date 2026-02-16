FROM alpine:3.19

RUN apk add --no-cache openssh-client bash

COPY scripts/ /scripts/
COPY deploy.sh /deploy.sh

RUN chmod +x /deploy.sh && \
    find /scripts -name "*.sh" -exec chmod +x {} \;

ENTRYPOINT ["/deploy.sh"]
