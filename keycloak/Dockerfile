# Keycloak for BizPartnerCheck (SCRUM-76), run on Render as a Docker web service. See "Keycloak" in README.md.
FROM quay.io/keycloak/keycloak:26.4 AS builder
ENV KC_DB=postgres
ENV KC_HEALTH_ENABLED=true
WORKDIR /opt/keycloak
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.4
COPY --from=builder /opt/keycloak/ /opt/keycloak/
# Imported on the first start only; once the realm exists, Keycloak skips the import.
COPY bizpartnercheck-realm.json /opt/keycloak/data/import/
# Render ends TLS at its proxy and forwards plain HTTP with X-Forwarded-* headers.
ENV KC_HTTP_ENABLED=true
ENV KC_PROXY_HEADERS=xforwarded
ENTRYPOINT ["/opt/keycloak/bin/kc.sh"]
CMD ["start", "--optimized", "--import-realm"]
