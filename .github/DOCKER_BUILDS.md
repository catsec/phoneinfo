# Docker Multi-Platform Builds

This repository uses GitHub Actions to automatically build and publish multi-platform Docker images to GitHub Container Registry (ghcr.io).

## Supported Platforms

The Docker images are built for the following platforms:

### Linux
- **linux/amd64** - Intel/AMD 64-bit (most common)
- **linux/arm64** - ARM 64-bit (Apple Silicon, AWS Graviton, Raspberry Pi 4/5)
- **linux/arm/v7** - ARM 32-bit (Raspberry Pi 3, older ARM devices)

### macOS
- **Intel Macs** - Use linux/amd64 image via Docker Desktop
- **Apple Silicon (M1/M2/M3)** - Use linux/arm64 image via Docker Desktop

### Windows
- **Windows 10/11** - Use linux/amd64 image via Docker Desktop (WSL2)

## Automatic Builds

Images are automatically built and published when:

1. **Push to master branch** → `ghcr.io/catsec/phoneinfo:latest` and `ghcr.io/catsec/phoneinfo:master`
2. **Version tags** (e.g., `v1.0.0`) → `ghcr.io/catsec/phoneinfo:1.0.0`, `ghcr.io/catsec/phoneinfo:1.0`, `ghcr.io/catsec/phoneinfo:1`
3. **Pull requests** → Build only (not pushed to registry)

## Image Tags

| Tag Pattern | Description | Example |
|-------------|-------------|---------|
| `latest` | Latest build from master | `ghcr.io/catsec/phoneinfo:latest` |
| `master` | Master branch builds | `ghcr.io/catsec/phoneinfo:master` |
| `v*` | Version tags | `ghcr.io/catsec/phoneinfo:v1.0.0` |
| `{version}` | Semantic version | `ghcr.io/catsec/phoneinfo:1.0.0` |
| `{major}.{minor}` | Major.minor version | `ghcr.io/catsec/phoneinfo:1.0` |
| `{major}` | Major version | `ghcr.io/catsec/phoneinfo:1` |
| `sha-{commit}` | Specific commit | `ghcr.io/catsec/phoneinfo:sha-abc1234` |

## Usage by Platform

### Linux (AMD64/Intel)
```bash
docker pull ghcr.io/catsec/phoneinfo:latest
docker run -d -p 5001:5001 ghcr.io/catsec/phoneinfo:latest
```

### Linux (ARM64)
```bash
# Raspberry Pi 4/5, AWS Graviton, etc.
docker pull ghcr.io/catsec/phoneinfo:latest
docker run -d -p 5001:5001 ghcr.io/catsec/phoneinfo:latest
```

### macOS (Intel)
```bash
# Docker Desktop automatically uses linux/amd64
docker pull ghcr.io/catsec/phoneinfo:latest
docker run -d -p 5001:5001 ghcr.io/catsec/phoneinfo:latest
```

### macOS (Apple Silicon - M1/M2/M3)
```bash
# Docker Desktop automatically uses linux/arm64
docker pull ghcr.io/catsec/phoneinfo:latest
docker run -d -p 5001:5001 ghcr.io/catsec/phoneinfo:latest
```

### Windows (Docker Desktop)
```powershell
# Docker Desktop (WSL2) automatically uses linux/amd64
docker pull ghcr.io/catsec/phoneinfo:latest
docker run -d -p 5001:5001 ghcr.io/catsec/phoneinfo:latest
```

## Manual Multi-Platform Build

To build multi-platform images locally:

```bash
# Set up buildx builder (one-time setup)
docker buildx create --name multiplatform --use
docker buildx inspect --bootstrap

# Build for all platforms
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  --tag ghcr.io/catsec/phoneinfo:latest \
  --push \
  .
```

## Workflow Details

### Build Process

1. **Checkout** - Get repository code
2. **QEMU Setup** - Enable cross-platform emulation for ARM builds
3. **Buildx Setup** - Configure Docker buildx for multi-platform builds
4. **Login** - Authenticate to GitHub Container Registry
5. **Metadata** - Extract tags and labels from git context
6. **Build & Push** - Build for all platforms and push to registry
7. **Attestation** - Generate build provenance attestation (security)

### Caching

The workflow uses GitHub Actions cache to speed up builds:
- Cache is shared across platforms
- Dependencies are cached between builds
- Significantly reduces build time

### Security

- **Build Provenance** - Attestation proves image origin
- **Minimal Base Image** - Uses `python:3.11-slim` for security
- **No Secrets in Images** - API credentials via environment variables
- **Automated Scanning** - GitHub automatically scans for vulnerabilities

## Troubleshooting

### Pull the specific platform image

```bash
# Force AMD64 on ARM Mac
docker pull --platform linux/amd64 ghcr.io/catsec/phoneinfo:latest

# Force ARM64 on Intel Mac
docker pull --platform linux/arm64 ghcr.io/catsec/phoneinfo:latest
```

### Check image platforms

```bash
docker buildx imagetools inspect ghcr.io/catsec/phoneinfo:latest
```

### Authentication Issues

If you get "authentication required" errors:

```bash
# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin
```

For personal access tokens, create one at https://github.com/settings/tokens with `read:packages` scope.

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Pull and run PhoneInfo
  run: |
    docker pull ghcr.io/catsec/phoneinfo:latest
    docker run -d \
      -p 5001:5001 \
      -e ME_API_URL=${{ secrets.ME_API_URL }} \
      -e ME_API_SID=${{ secrets.ME_API_SID }} \
      -e ME_API_TOKEN=${{ secrets.ME_API_TOKEN }} \
      ghcr.io/catsec/phoneinfo:latest
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: phoneinfo
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: phoneinfo
        image: ghcr.io/catsec/phoneinfo:latest
        ports:
        - containerPort: 5001
        env:
        - name: ME_API_URL
          valueFrom:
            secretKeyRef:
              name: phoneinfo-secrets
              key: api-url
```

## Performance Notes

### Build Times
- **AMD64** - ~2-3 minutes (native build)
- **ARM64** - ~3-4 minutes (emulated on AMD64 runners)
- **ARM/v7** - ~4-5 minutes (emulated)

### Image Sizes
- **Compressed** - ~189MB (download size)
- **Uncompressed** - ~794MB (disk usage)

### Platform-Specific Performance
- **Native builds** (AMD64 on Intel, ARM64 on Apple Silicon) are fastest
- **Emulated builds** work but are slower
- Docker automatically selects the best platform for your system

## Additional Resources

- [GitHub Container Registry Docs](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Docker Buildx Documentation](https://docs.docker.com/buildx/working-with-buildx/)
- [Multi-platform Images Guide](https://docs.docker.com/build/building/multi-platform/)

## Maintenance

### Updating Workflow

The workflow file is at [`.github/workflows/docker-publish.yml`](../workflows/docker-publish.yml).

To modify platforms, edit the `platforms` line:
```yaml
platforms: linux/amd64,linux/arm64,linux/arm/v7
```

### Triggering Manual Builds

Go to **Actions** → **Build and Publish Docker Images** → **Run workflow**

---

**Last Updated:** 2026-02-16
