# FaceGuard — Security Scan Runbook (Phase 3)
# All tools are pre-installed on Kali Linux

---

## 1. Nikto Web Server Scan

Nikto checks for misconfigurations, outdated headers, and common vulnerabilities.

```bash
# Basic scan
nikto -h https://yourdomain.com -output /tmp/nikto_report.txt

# With authentication (add JWT header)
nikto -h https://yourdomain.com \
      -id "Authorization:Bearer YOUR_JWT_TOKEN" \
      -output /tmp/nikto_auth_report.txt \
      -Format htm

# API endpoints scan
nikto -h https://yourdomain.com/api/ \
      -output /tmp/nikto_api_report.txt
```

**Hardening checklist based on Nikto output:**

| Check | Expected | Fix if failing |
|-------|----------|----------------|
| X-Frame-Options | DENY | Add in Nginx: `add_header X-Frame-Options "DENY"` |
| X-Content-Type-Options | nosniff | Add in Nginx |
| Strict-Transport-Security | present | Add HSTS header |
| Server header | hidden | `server_tokens off` in Nginx |
| X-Powered-By | absent | Django already removes this |
| Directory listing | disabled | `autoindex off` in Nginx |

---

## 2. OWASP ZAP Automated Scan

ZAP is the most comprehensive DAST scanner. Run from Kali.

```bash
# Start ZAP in daemon mode
zaproxy -daemon -port 8090 -config api.disablekey=true &
sleep 10

# Run baseline scan (passive + active)
zap-baseline.py \
  -t https://yourdomain.com \
  -r zap_baseline_report.html \
  -x zap_baseline_report.xml \
  -J zap_baseline_report.json \
  -I  # don't fail on warnings, just report

# Full API scan with OpenAPI spec (if you generate one)
zap-api-scan.py \
  -t https://yourdomain.com/api/ \
  -f openapi \
  -r zap_api_report.html
```

**ZAP findings to address before sign-off:**

| Alert Level | Finding | Remediation |
|-------------|---------|-------------|
| HIGH | SQL Injection | Django ORM parameterises all queries — verify no raw SQL |
| HIGH | Missing HTTPS | Enforced by Nginx redirect |
| MEDIUM | CSP Header missing | Added in Nginx config |
| MEDIUM | Cookie without Secure flag | Set `SESSION_COOKIE_SECURE=True` in settings |
| LOW | Server leaks version | `server_tokens off` in Nginx |

**Django settings to add before production:**

```python
# settings.py — production security flags
SECURE_SSL_REDIRECT          = True
SECURE_HSTS_SECONDS          = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD          = True
SECURE_CONTENT_TYPE_NOSNIFF  = True
SESSION_COOKIE_SECURE        = True
SESSION_COOKIE_HTTPONLY      = True
CSRF_COOKIE_SECURE           = True
CSRF_COOKIE_HTTPONLY         = True
X_FRAME_OPTIONS              = 'DENY'
```

---

## 3. Burp Suite — JWT & API Auth Testing

Use Burp Suite Community Edition (pre-installed on Kali).

### Setup
1. Open Burp → Proxy → Intercept ON
2. Configure browser to proxy through 127.0.0.1:8080
3. Browse to `http://127.0.0.1:8000` and log in

### JWT Tampering Tests (use Burp Repeater)

**Test 1 — Algorithm confusion (alg:none)**
```
Intercept login response → copy access token
Decode header: {"alg":"HS256","typ":"JWT"}
Change to: {"alg":"none","typ":"JWT"}
Re-encode → remove signature → send
Expected: 401 Unauthorized ✓
```

**Test 2 — Payload tampering**
```
Decode JWT payload
Change "role":"viewer" to "role":"admin"
Re-encode with same signature
Expected: 401 Unauthorized (signature invalid) ✓
```

**Test 3 — IDOR on /api/persons/{id}/**
```
Login as viewer
GET /api/persons/1/   → expect 403 ✓
GET /api/persons/2/   → expect 403 ✓
POST /api/enrol/      → expect 403 ✓
```

**Test 4 — Forced browsing**
```
GET /api/auth/users/      (as guard)  → expect 403 ✓
GET /api/zones/           (as viewer) → expect 403 ✓
DELETE /api/persons/1/    (as guard)  → expect 403 ✓
```

**Test 5 — Refresh token replay after logout**
```
1. Login → save refresh token
2. POST /api/auth/logout/ with refresh token → 205
3. POST /api/auth/refresh/ with same token → expect 401 (blacklisted) ✓
```

### Burp Intruder — Brute force check
```
Target: POST /api/auth/login/
Payload: common passwords list
Send 20 attempts
Expected: All return 401, no lockout bypass
Note: Add django-axes or similar for production rate limiting
```

---

## 4. Let's Encrypt Certificate Setup

```bash
# Install certbot (Kali / Debian)
sudo apt install certbot python3-certbot-nginx -y

# Obtain certificate (Nginx plugin)
sudo certbot --nginx \
  -d yourdomain.com \
  -d www.yourdomain.com \
  --email admin@yourdomain.com \
  --agree-tos \
  --no-eff-email

# Verify auto-renewal
sudo certbot renew --dry-run

# Add renewal cron (certbot usually does this automatically)
sudo systemctl status certbot.timer
```

---

## 5. Server Hardening Checklist

```bash
# Check SSL grade (should be A or A+)
curl https://api.ssllabs.com/api/v3/analyze?host=yourdomain.com | python3 -m json.tool

# Check security headers
curl -I https://yourdomain.com | grep -i 'strict\|x-frame\|x-content\|content-security'

# Verify no open ports except 80/443
sudo nmap -sV yourdomain.com

# Check Django deployment checklist
python manage.py check --deploy
```

**Expected output of `python manage.py check --deploy`:**
```
System check identified no issues (0 silenced).
```
If issues appear, fix each one before going live.
