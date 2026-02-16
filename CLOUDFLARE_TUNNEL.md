# Cloudflare Tunnel Setup

## Overview

PhoneInfo is accessible via **Cloudflare Tunnel** at https://phoneinfo.catsec.com

This provides:
- ✅ **HTTPS encryption** - Automatic SSL/TLS
- ✅ **No port forwarding** - No firewall changes needed
- ✅ **DDoS protection** - Cloudflare's network protection
- ✅ **Access control** - Can add authentication at Cloudflare level

---

## Configuration

### 1. Tunnel Token

The Cloudflare Tunnel token is stored in `.env`:

```env
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiZTA3Y2FjZTdjM2Q2ZDlkOWVlNjYzYjY0NjYyMTNjNDkiLCJ0IjoiNWM1OWQ5ZWMtNDU3My00YmJiLTk5MjAtMzBhNTIxMmNlZjRmIiwicyI6IlpXTXlNREV6WXpRdE0yRmtZeTAwWldFekxUbGpZV010WlRWa01tWTFNekU1TnpFNCJ9
```

### 2. Docker Compose Setup

The `docker-compose.yml` includes two services:

**phoneinfo** - The Flask application
```yaml
phoneinfo:
  build: .
  container_name: phoneinfo
  restart: unless-stopped
  ports:
    - "5001:5001"
  environment:
    - PRODUCTION=true
```

**cloudflared** - The Cloudflare Tunnel client
```yaml
cloudflared:
  image: cloudflare/cloudflared:latest
  container_name: phoneinfo-tunnel
  restart: unless-stopped
  command: tunnel --no-autoupdate run
  environment:
    - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
  depends_on:
    - phoneinfo
```

### 3. Production Security Settings

When `PRODUCTION=true`, the following security settings are enabled:

```python
# In server.py
if os.environ.get('PRODUCTION', '').lower() == 'true':
    app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS-only cookies
```

This ensures session cookies are only sent over HTTPS, preventing session hijacking.

---

## Deployment

### Quick Start

1. **Ensure .env is configured:**
   ```bash
   # Verify tunnel token is present
   grep CLOUDFLARE_TUNNEL_TOKEN .env
   ```

2. **Start the services:**
   ```bash
   docker-compose up -d
   ```

3. **Verify services are running:**
   ```bash
   docker-compose ps
   ```

   Expected output:
   ```
   NAME                  STATUS
   phoneinfo             Up (healthy)
   phoneinfo-tunnel      Up
   ```

4. **Check logs:**
   ```bash
   # Application logs
   docker-compose logs -f phoneinfo

   # Tunnel logs
   docker-compose logs -f cloudflared
   ```

5. **Access the application:**
   - External: https://phoneinfo.catsec.com
   - Local: http://localhost:5001

---

## Tunnel Architecture

```
Internet → Cloudflare Edge → Cloudflare Tunnel (cloudflared)
    ↓
    → phoneinfo.catsec.com (HTTPS)
    ↓
    → Cloudflare Tunnel Container (docker network)
    ↓
    → PhoneInfo App Container (port 5001)
```

**Benefits:**
- No public IP exposure
- No inbound firewall rules needed
- Cloudflare handles SSL/TLS termination
- Built-in DDoS protection
- Can add Cloudflare Access for additional authentication

---

## Tunnel Configuration

### Tunnel Details
- **Domain:** phoneinfo.catsec.com
- **Service:** http://phoneinfo:5001 (internal docker network)
- **Token:** Stored in .env (CLOUDFLARE_TUNNEL_TOKEN)

### Cloudflare Dashboard Settings

To view/modify tunnel settings:
1. Go to https://dash.cloudflare.com
2. Select your account
3. Navigate to **Zero Trust** → **Access** → **Tunnels**
4. Find your tunnel and click **Configure**

**Tunnel Configuration:**
```yaml
Public Hostname:
  Domain: phoneinfo.catsec.com
  Service: http://phoneinfo:5001

Security:
  - HTTPS: Enabled (automatic)
  - TLS version: 1.2+
  - HTTP/2: Enabled
```

---

## Troubleshooting

### Tunnel Not Connecting

**Check tunnel logs:**
```bash
docker-compose logs cloudflared
```

**Common issues:**
- Invalid tunnel token → Verify CLOUDFLARE_TUNNEL_TOKEN in .env
- Network connectivity → Check docker network
- Service not ready → Check phoneinfo container health

**Restart tunnel:**
```bash
docker-compose restart cloudflared
```

### Application Not Accessible

**Check application logs:**
```bash
docker-compose logs phoneinfo
```

**Verify health check:**
```bash
docker exec phoneinfo python -c "import requests; print(requests.get('http://localhost:5001/health').text)"
```

**Expected output:**
```json
{"status": "healthy"}
```

### Session Cookies Not Working

If session cookies aren't working over HTTPS:

1. **Verify PRODUCTION flag:**
   ```bash
   docker exec phoneinfo printenv PRODUCTION
   # Should output: true
   ```

2. **Verify cookie settings in browser:**
   - Open DevTools → Application → Cookies
   - Check `session` cookie has:
     - `Secure: ✓`
     - `HttpOnly: ✓`
     - `SameSite: Lax`

### Port Conflicts

If port 5001 is already in use:

1. **Option 1: Change port in docker-compose.yml:**
   ```yaml
   ports:
     - "5002:5001"  # External:Internal
   ```

2. **Option 2: Stop conflicting service:**
   ```bash
   # Find process using port 5001
   netstat -ano | findstr :5001
   # Stop it
   taskkill /PID <PID> /F
   ```

---

## Maintenance

### View Running Containers
```bash
docker-compose ps
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f phoneinfo
docker-compose logs -f cloudflared
```

### Restart Services
```bash
# All services
docker-compose restart

# Specific service
docker-compose restart phoneinfo
docker-compose restart cloudflared
```

### Update Application
```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose up -d --build
```

### Stop Services
```bash
docker-compose down
```

### Full Reset (including data)
```bash
# WARNING: This deletes the database!
docker-compose down -v
docker-compose up -d --build
```

---

## Security Considerations

### HTTPS-Only Access

With Cloudflare Tunnel, all traffic is encrypted:
- External clients → Cloudflare: **HTTPS (TLS 1.2+)**
- Cloudflare → Tunnel: **Encrypted tunnel**
- Tunnel → App: **HTTP (internal docker network)**

**Security flags enabled in production:**
```python
SESSION_COOKIE_SECURE = True    # Cookies only over HTTPS
SESSION_COOKIE_HTTPONLY = True  # No JavaScript access
SESSION_COOKIE_SAMESITE = 'Lax' # CSRF protection
```

### Additional Security Options

**Cloudflare Access** (optional):
- Add authentication before reaching the app
- Supports SSO, SAML, OAuth
- IP allowlisting/denylisting
- Geographic restrictions

**To enable Cloudflare Access:**
1. Go to Cloudflare Dashboard
2. Zero Trust → Access → Applications
3. Add application for phoneinfo.catsec.com
4. Configure authentication rules

---

## Monitoring

### Health Checks

Docker compose includes health checks:
```yaml
healthcheck:
  test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:5001/health', timeout=5)"]
  interval: 30s
  timeout: 10s
  retries: 3
```

**Check health status:**
```bash
docker inspect phoneinfo | grep Health -A 10
```

### Cloudflare Analytics

View traffic analytics at:
- Cloudflare Dashboard → Analytics & Logs
- Shows requests, bandwidth, threats blocked

---

## Backup and Recovery

### Backup Database
```bash
# Copy database from container
docker cp phoneinfo:/app/db/db.db ./db/db.db.backup

# Or use volume backup
docker run --rm -v phoneinfo_db:/data -v $(pwd):/backup alpine tar czf /backup/db-backup.tar.gz /data
```

### Restore Database
```bash
# Copy backup to container
docker cp ./db/db.db.backup phoneinfo:/app/db/db.db

# Restart to apply
docker-compose restart phoneinfo
```

---

## Summary

✅ **Setup Complete:**
- Cloudflare Tunnel configured
- HTTPS enabled at phoneinfo.catsec.com
- Production security flags active
- Automatic SSL/TLS
- DDoS protection included

✅ **Access:**
- External: https://phoneinfo.catsec.com
- Local: http://localhost:5001

✅ **Management:**
- Start: `docker-compose up -d`
- Stop: `docker-compose down`
- Logs: `docker-compose logs -f`
- Status: `docker-compose ps`
