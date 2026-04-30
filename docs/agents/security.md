# Security Requirements

## Container Security

### Vulnerability Scanning

| Tool | Purpose | Usage |
|------|---------|-------|
| **Trivy** | Scan Docker images for CVEs | `trivy image <image-name>` |
| **Docker Bench Security** | CIS benchmark audit for Docker host | `docker run docker/docker-bench-security` |

### Runtime Hardening

- **Seccomp**: Restrict system calls available to containers
- **AppArmor**: Mandatory access control profiles for containers
- Run containers as **non-root** where possible
- Use **read-only** file systems for model serving containers
- Limit container resources (`--memory`, `--cpus`)

## VM Security

### Vulnerability Scanning

| Tool | Purpose |
|------|---------|
| **OpenSCAP** | Security compliance scanning for VM images |
| Disk image scanning | Check VM disk images for known vulnerabilities |

### Runtime Hardening

- **SELinux**: Mandatory access control for VM hosts
- **VM isolation**: Ensure proper hypervisor-level isolation
- **Boundary controls**: Network segmentation between VMs
- Minimal OS images — remove unnecessary packages

## Compliance

### GDPR

- Ensure no personal data is stored in model inputs/outputs during benchmarks
- Use synthetic or public datasets only (Alpaca, Lotus)
- Document data flow for any user-facing features

### HIPAA

- Relevant if SLM processes private/medical data
- Ensure encryption at rest and in transit
- Audit logging for all model access

## Security Testing Checklist

For every deployment (Docker and VM):

- [ ] Run Trivy / OpenSCAP scan — no critical CVEs
- [ ] Verify container runs as non-root
- [ ] Verify network isolation between test environments
- [ ] Verify no sensitive data in logs or results
- [ ] Verify model files integrity (checksum validation)

## Network Security

- Use TLS for any API endpoints exposed during benchmarks
- Restrict Prometheus/Grafana access to localhost or VPN
- No model inference endpoints exposed to public internet during testing
