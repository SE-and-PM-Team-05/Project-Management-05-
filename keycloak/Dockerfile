# Keycloak for BizPartnerCheck (SCRUM-76), run on Render as a Docker web service. See "Keycloak" in README.md.
FROM quay.io/keycloak/keycloak:26.4 AS builder
ENV KC_DB=postgres
ENV KC_HEALTH_ENABLED=true
# One instance only: a local cache instead of the cluster cache, which needs less memory.
ENV KC_CACHE=local
WORKDIR /opt/keycloak
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.4
COPY --from=builder /opt/keycloak/ /opt/keycloak/
# Imported on the first start only; once the realm exists, Keycloak skips the import.
COPY bizpartnercheck-realm.json /opt/keycloak/data/import/
# Render ends TLS at its proxy and forwards plain HTTP with X-Forwarded-* headers.
ENV KC_HTTP_ENABLED=true
ENV KC_PROXY_HEADERS=xforwarded
# Fit into Render's free instance (512 MB): Java's defaults size the heap for a bigger machine and run out of memory.
# ponytail: tuned by guess for 512 MB; if it still runs out of memory, use an instance with more memory instead.
ENV JAVA_OPTS_KC_HEAP="-Xms64m -Xmx224m -XX:MaxMetaspaceSize=160m -XX:ReservedCodeCacheSize=48m -XX:TieredStopAtLevel=1 -XX:+UseSerialGC -Xss512k"
ENV KC_DB_POOL_MAX_SIZE=5
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized", "--import-realm"]
