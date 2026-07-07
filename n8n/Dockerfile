# Self-hosted n8n for the DOME Governed Agent Flow (P5).
# All configuration (encryption key, DB, host, basic-auth, the shim base URL, and
# the X-Service-Key credential) is supplied via environment variables / the n8n
# credential store — never baked into the image. See n8n/README.md.
# Pinned (DA-034): mutable tags are not allowed on the workflow engine. Bump
# deliberately; `latest` resolved to this version when pinned (2026-07-07).
FROM n8nio/n8n:2.29.7

EXPOSE 5678
