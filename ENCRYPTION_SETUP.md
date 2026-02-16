# Database Encryption Setup (SQLCipher)

PhoneInfo uses **SQLCipher** for database file-level encryption. This encrypts the entire SQLite database file at rest using AES-256 encryption.

**Note:** This is file-level encryption only. Column-level encryption is NOT used in this implementation.

---

## Quick Start (5 minutes)

### Step 1: Generate Encryption Key

\`\`\`bash
python generate_encryption_key.py
\`\`\`

**Output example:**
\`\`\`
DB_ENCRYPTION_KEY=BQimz9CpQfbhtvH8p3xk3T7Kli+SHZkAngo1waxSnGc=
\`\`\`

This generates a base64-encoded 256-bit (32 byte) key that is safe for config files.

### Step 2: Add Key to .env

Open \`.env\` file and add the generated key:

\`\`\`bash
# Database Encryption (SQLCipher) - Base64 encoded 256-bit key
DB_ENCRYPTION_KEY=BQimz9CpQfbhtvH8p3xk3T7Kli+SHZkAngo1waxSnGc=
\`\`\`

### Step 3: Restart Server

**Docker (Recommended for Encryption):**
\`\`\`bash
docker-compose up -d --build
\`\`\`

**Local (Windows - Requires Visual C++ Build Tools):**
\`\`\`bash
python server.py
\`\`\`

**Note:** On Windows, pysqlcipher3 requires Microsoft Visual C++ 14.0+ Build Tools. For local development without these tools, the application will fall back to unencrypted mode with a warning. **Encryption works fully in Docker on all platforms.**

**You'll see:**
\`\`\`
[Security] Database encryption: ENABLED (SQLCipher)
[Security] Database db/db.db is encrypted with SQLCipher AES-256
\`\`\`

✅ **Done!** Your database is now encrypted with AES-256.

---

## What's Encrypted?

- ✅ **Entire database file** (\`db/db.db\`)
  - ME API cached data (phone numbers, names, emails, etc.)
  - SYNC API cached data
  - User authentication data
  - Session data
  - All tables and indexes

- ✅ **At rest**: File is encrypted on disk
- ✅ **Transparent**: No code changes needed for queries
- ✅ **Fast**: Minimal performance overhead (~5-10%)

---

## Migration (Existing Database)

If you already have an unencrypted \`db/db.db\` with cached data, see [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for automatic migration instructions.

**Quick Summary:**
1. Generate new encryption key
2. Set \`DB_ENCRYPTION_KEY=<new-key>\` in .env
3. Set \`DB_ENCRYPTION_KEY_OLD=""\` in .env (empty = unencrypted)
4. Restart server - migration happens automatically
5. Remove \`DB_ENCRYPTION_KEY_OLD\` from .env after successful migration

---

## Verification

Test that encryption is working:

\`\`\`python
# test_encryption.py
import os
os.environ['DB_ENCRYPTION_KEY'] = 'your-key-here'

from functions import init_db

# Should work with correct key
conn = init_db('db/db.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
print("Tables:", cursor.fetchall())
conn.close()
\`\`\`

**With wrong key:**
\`\`\`bash
# Will fail with:
# sqlite3.DatabaseError: file is not a database
\`\`\`

---

## Docker Deployment

### docker-compose.yml

\`\`\`yaml
services:
  phoneinfo:
    environment:
      - DB_ENCRYPTION_KEY=\${DB_ENCRYPTION_KEY}
    volumes:
      - ./db:/app/db
\`\`\`

### .env (on Docker host)

\`\`\`bash
DB_ENCRYPTION_KEY=BQimz9CpQfbhtvH8p3xk3T7Kli+SHZkAngo1waxSnGc=
\`\`\`

### Deploy

\`\`\`bash
docker-compose up -d --build
\`\`\`

---

## Troubleshooting

### "file is not a database"

**Cause:** Wrong encryption key or database was not encrypted.

**Fix:**
1. Check \`DB_ENCRYPTION_KEY\` in .env matches the key used to encrypt
2. If migrating, ensure migration completed successfully
3. Check migration logs for errors

### "SQLCipher not installed" (Windows)

**Cause:** \`pysqlcipher3\` requires C++ Build Tools on Windows.

**Fix:**

**Option 1: Use Docker (Recommended)**
\`\`\`bash
docker-compose up -d --build
\`\`\`

**Option 2: Install Build Tools**
Download and install: https://visualstudio.microsoft.com/visual-cpp-build-tools/

**Option 3: Development Mode (Unencrypted)**
For local development only, you can run without encryption (fallback mode). The application will show a warning but continue.

---

## Security Checklist

- [ ] Encryption key generated (\`python generate_encryption_key.py\`)
- [ ] Key added to \`.env\` or secrets manager
- [ ] \`.env\` in \`.gitignore\` (should already be there)
- [ ] Key backed up in secure location
- [ ] Server restarted with encryption enabled
- [ ] Verified encryption works (test query)
- [ ] Database file permissions set to 600 (\`chmod 600 db/db.db\`)
- [ ] Old unencrypted backup deleted securely (if migrated)
- [ ] Key rotation plan established (quarterly recommended)

---

## Key Rotation

For rotating encryption keys (recommended quarterly), see [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for detailed instructions.

**Quick Summary:**
1. Generate new key: \`python generate_encryption_key.py\`
2. Set both keys in .env
3. Restart server - automatic re-encryption
4. Remove \`DB_ENCRYPTION_KEY_OLD\` after verification

---

## FAQ

**Q: What if I lose the encryption key?**
A: Database is **permanently unrecoverable**. Back up your key!

**Q: Can I search encrypted fields?**
A: Yes! Encryption is transparent. All queries work normally.

**Q: What encryption algorithm is used?**
A: AES-256 in CBC mode (industry standard).

**Q: Does encryption work on Windows?**
A: Yes, but only in Docker. Local Windows development requires Visual C++ Build Tools.

---

## Support

- SQLCipher docs: https://www.zetetic.net/sqlcipher/
- Migration Guide: [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
- Security Documentation: [SECURITY.md](SECURITY.md)
