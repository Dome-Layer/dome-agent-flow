# Self-hosted n8n for the DOME Governed Agent Flow (P5).
# All configuration (encryption key, DB, host) is supplied via environment
# variables, and the X-Service-Key credential via the n8n credential store; none
# of it is baked into the image. The shim URL lives in the workflow's Config node
# (n8n 2.x blocks $env in expressions by default). See n8n/README.md.
# Pinned (DA-034): mutable tags are not allowed on the workflow engine. Bump
# deliberately; `latest` resolved to this version when pinned (2026-07-07).
FROM n8nio/n8n:2.29.7

EXPOSE 5678
