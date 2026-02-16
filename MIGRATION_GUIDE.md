# Database Encryption Migration Guide

Automatic migration and key rotation for PhoneInfo databases.

---

## Scenario 1: Migrate Existing Unencrypted Database

**Situation:** You have an existing `db/db.db` with cached data, and want to encrypt it.

### Steps:

1. **Generate encryption key:**
   ```bash
   python generate_encryption_key.py
   ```

2. **Update .env:**
   ```bash
   # Add new encryption key
   DB_ENCRYPTION_KEY=<your-new-key>

   # Set old key to empty (indicates unencrypted)
   DB_ENCRYPTION_KEY_OLD=""
   ```

3. **Restart server:**
   ```bash
   python server.py
   ```

4. **Watch the migration:**
   ```
   ======================================================================
   DATABASE MIGRATION/KEY ROTATION
   ======================================================================
   [Migration] Created backup: db/db.db.backup_20260216_143022
   [Migration] Old database is UNENCRYPTED
   [Migration] New database will be ENCRYPTED
   [Migration] Migrating from unencrypted to encrypted...
   [Migration] Successfully migrated to encrypted database
   [Migration] Old database renamed to: db/db.db.old
   [Migration] New database active at: db/db.db
   ======================================================================
   MIGRATION COMPLETE
   ======================================================================
   ```

5. **Verify it works:**
   - Test some API calls
   - Check cached data is still there

6. **Clean up:**
   ```bash
   # Remove migration trigger from .env
   # Comment out or delete this line:
   # DB_ENCRYPTION_KEY_OLD=""

   # Restart to confirm normal operation
   python server.py
   ```

7. **Delete backups (optional):**
   ```bash
   rm db/db.db.backup_*
   rm db/db.db.old
   ```

✅ **Done!** Database is now encrypted.

---

## Scenario 2: Key Rotation (Change Encryption Key)

**Situation:** You want to rotate encryption keys (quarterly security practice).

### Steps:

1. **Generate new encryption key:**
   ```bash
   python generate_encryption_key.py
   ```

2. **Update .env:**
   ```bash
   # Keep old key (current encryption key)
   DB_ENCRYPTION_KEY_OLD=<your-current-key>

   # Set new key
   DB_ENCRYPTION_KEY=<your-new-key>
   ```

3. **Restart server:**
   ```bash
   python server.py
   ```

4. **Watch the rotation:**
   ```
   ======================================================================
   DATABASE MIGRATION/KEY ROTATION
   ======================================================================
   [Migration] Created backup: db/db.db.backup_20260216_143522
   [Migration] Old database is ENCRYPTED
   [Migration] Rotating to new encryption key
   [Migration] Rotating encryption key...
   [Migration] Successfully rotated encryption key
   [Migration] Old database renamed to: db/db.db.old
   [Migration] New database active at: db/db.db
   ======================================================================
   MIGRATION COMPLETE
   ======================================================================
   ```

5. **Verify it works:**
   - Test API calls
   - Verify cached data

6. **Clean up .env:**
   ```bash
   # Remove old key from .env
   # Delete this line:
   # DB_ENCRYPTION_KEY_OLD=<old-key>

   # Keep only:
   DB_ENCRYPTION_KEY=<new-key>
   ```

7. **Restart to confirm:**
   ```bash
   python server.py
   ```

8. **Securely delete old backups:**
   ```bash
   shred -u db/db.db.backup_* db/db.db.old  # Linux
   # Or on Windows: permanently delete files
   ```

✅ **Done!** Encryption key rotated.

---

## Scenario 3: Fresh Installation

**Situation:** No existing database, starting from scratch.

### Steps:

1. **Generate encryption key:**
   ```bash
   python generate_encryption_key.py
   ```

2. **Add to .env:**
   ```bash
   DB_ENCRYPTION_KEY=<your-key>
   # DO NOT set DB_ENCRYPTION_KEY_OLD
   ```

3. **Start server:**
   ```bash
   python server.py
   ```

4. **Result:**
   ```
   [Security] Database encryption: ENABLED (SQLCipher)
   [Security] Database db/db.db is encrypted with SQLCipher AES-256
   Starting phoneinfo server on http://0.0.0.0:5001
   ```

✅ **Done!** New encrypted database created.

---

## Docker Deployment

### Scenario 1: Migrate Existing Docker Database

```yaml
# docker-compose.yml
services:
  phoneinfo:
    environment:
      # New key
      - DB_ENCRYPTION_KEY=${DB_ENCRYPTION_KEY}
      # Old key (empty = unencrypted)
      - DB_ENCRYPTION_KEY_OLD=${DB_ENCRYPTION_KEY_OLD}
    volumes:
      - ./db:/app/db
```

```bash
# .env
DB_ENCRYPTION_KEY=<new-key>
DB_ENCRYPTION_KEY_OLD=""
```

```bash
# Deploy
docker-compose up -d

# Watch logs
docker-compose logs -f phoneinfo

# After successful migration, remove DB_ENCRYPTION_KEY_OLD from .env
# and restart
docker-compose restart
```

### Scenario 2: Key Rotation in Docker

```bash
# .env
DB_ENCRYPTION_KEY=<new-key>
DB_ENCRYPTION_KEY_OLD=<old-key>
```

```bash
docker-compose restart
docker-compose logs -f phoneinfo

# Clean up
# Remove DB_ENCRYPTION_KEY_OLD from .env
docker-compose restart
```

---

## Migration Safety Features

### Automatic Backups
- Creates timestamped backup before migration
- Format: `db/db.db.backup_YYYYMMDD_HHMMSS`
- Keeps original database as `db/db.db.old`

### Migration Marker
- Creates `.db_migration_complete` marker file
- Prevents accidental re-migration
- Stores the encryption key used (for change detection)

### Error Handling
- If migration fails, restores from backup automatically
- Server startup aborts on migration failure
- Logs detailed error messages

### Rollback Process
If something goes wrong:

```bash
# 1. Stop server
docker-compose down  # or Ctrl+C

# 2. Restore from backup
cp db/db.db.backup_YYYYMMDD_HHMMSS db/db.db

# 3. Fix .env (remove DB_ENCRYPTION_KEY_OLD or fix keys)

# 4. Restart
python server.py
```

---

## How It Works

### Migration Trigger

Migration runs when:
- `DB_ENCRYPTION_KEY_OLD` is set in environment
- Migration marker doesn't exist OR keys have changed
- Server starts

### Migration Types

**Type 1: Unencrypted → Encrypted**
```
DB_ENCRYPTION_KEY_OLD=""
DB_ENCRYPTION_KEY="new-key"
```
- Reads unencrypted `db.db`
- Writes to encrypted `db.db.migrating`
- Replaces original with migrated

**Type 2: Key Rotation**
```
DB_ENCRYPTION_KEY_OLD="old-key"
DB_ENCRYPTION_KEY="new-key"
```
- Decrypts with old key
- Re-encrypts with new key
- Replaces original

**Type 3: Normal Operation**
```
# DB_ENCRYPTION_KEY_OLD not set
DB_ENCRYPTION_KEY="current-key"
```
- No migration
- Uses database as-is

### Migration Flow

```
1. Check if DB_ENCRYPTION_KEY_OLD is set
   ├─ No  → Normal operation (no migration)
   └─ Yes → Continue

2. Check migration marker
   ├─ Exists + same key → Skip (already done)
   └─ Doesn't exist OR different key → Continue

3. Create backup
   db/db.db → db/db.db.backup_TIMESTAMP

4. Migrate database
   ├─ OLD=""  → Unencrypted to Encrypted
   └─ OLD=key → Re-encrypt with new key

5. Replace original
   db/db.db      → db/db.db.old
   db/db.db.migrating → db/db.db

6. Create marker
   .db_migration_complete (contains new key)

7. Continue normal startup
```

---

## Troubleshooting

### "file is not a database"

**Cause:** Wrong old encryption key.

**Fix:**
1. Check `DB_ENCRYPTION_KEY_OLD` matches the actual key used
2. If unsure, restore from backup and start over

### Migration hangs

**Cause:** Large database taking time.

**Fix:**
- Be patient (can take 1-2 minutes for 1GB+ databases)
- Check disk space
- Monitor logs for progress

### "Migration failed: ..."

**Cause:** Various (disk space, permissions, wrong key)

**Fix:**
1. Check error message
2. Database automatically restored from backup
3. Fix issue (disk space, permissions, etc.)
4. Try again

### Migration runs every startup

**Cause:** `.db_migration_complete` marker missing or being deleted.

**Fix:**
- Check file permissions
- Ensure db folder is writable
- Don't delete `.db_migration_complete` manually

### Want to migrate again

**Situation:** Migration completed but want to re-run.

**Fix:**
```bash
# Delete migration marker
rm db/.db_migration_complete

# Restart server (will re-run migration)
python server.py
```

---

## Testing Migration (Safe)

Test migration without affecting production:

```bash
# 1. Copy production database
cp db/db.db db/verify_test.db

# 2. Set test database in environment
export DATABASE=db/verify_test.db
export DB_ENCRYPTION_KEY=<new-key>
export DB_ENCRYPTION_KEY_OLD=""  # or old key

# 3. Test migration
python db_migration.py db/verify_test.db

# 4. Verify test database
python -c "
import os
os.environ['DB_ENCRYPTION_KEY'] = '<new-key>'
from functions import init_db
conn = init_db('db/verify_test.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM me_data')
print(f'Records: {cursor.fetchone()[0]}')
"

# 5. Clean up test
rm db/verify_test.db*
```

---

## Quarterly Key Rotation Schedule

**Recommended:** Rotate encryption keys every 90 days.

### Automation Script

```bash
#!/bin/bash
# rotate_db_key.sh

echo "Generating new encryption key..."
NEW_KEY=$(python generate_encryption_key.py | grep DB_ENCRYPTION_KEY | cut -d= -f2)

echo "Current key will be set as OLD key"
CURRENT_KEY=$(grep "^DB_ENCRYPTION_KEY=" .env | cut -d= -f2)

# Update .env
cp .env .env.backup
cat > .env << EOF
DB_ENCRYPTION_KEY=$NEW_KEY
DB_ENCRYPTION_KEY_OLD=$CURRENT_KEY

# ... rest of .env ...
EOF

echo "Restarting server for key rotation..."
docker-compose restart

echo "Monitor logs:"
echo "  docker-compose logs -f phoneinfo"
echo ""
echo "After successful rotation:"
echo "  1. Remove DB_ENCRYPTION_KEY_OLD from .env"
echo "  2. Restart: docker-compose restart"
```

---

## Production Checklist

Before migrating production database:

- [ ] Backup database manually: `cp db/db.db ~/backup/db.db.$(date +%Y%m%d)`
- [ ] Test migration on copy first
- [ ] Have old encryption key ready
- [ ] Have new encryption key generated
- [ ] Plan maintenance window (expect 5-10 minutes downtime)
- [ ] Alert users of maintenance
- [ ] Monitor migration logs
- [ ] Test application after migration
- [ ] Keep backups for 30 days
- [ ] Document old key in secure vault (recovery)
- [ ] Remove `DB_ENCRYPTION_KEY_OLD` after verification
- [ ] Securely delete old backups after 30 days

---

## FAQ

**Q: Can I migrate back to unencrypted?**
A: Yes, set `DB_ENCRYPTION_KEY_OLD=<current-key>` and `DB_ENCRYPTION_KEY=""`, then use custom migration script.

**Q: How long does migration take?**
A: Typically 1-5 seconds for <100MB databases. Larger databases take proportionally longer.

**Q: Will migration lose data?**
A: No, all data is preserved. Automatic backup is created before migration.

**Q: Can I rotate keys without downtime?**
A: No, server must restart for migration. Plan a maintenance window.

**Q: What if I lose the old encryption key?**
A: If database is already encrypted and you lost the key, data is UNRECOVERABLE. Always backup keys!

**Q: How often should I rotate keys?**
A: Quarterly (every 90 days) is a good security practice.

**Q: Does this work with SQLite without SQLCipher?**
A: No, SQLCipher is required for encryption. Regular SQLite doesn't support encryption.

---

## Support

For issues:
1. Check logs: `docker-compose logs phoneinfo` or `python server.py` output
2. Verify environment variables: `echo $DB_ENCRYPTION_KEY`
3. Test migration manually: `python db_migration.py`
4. Restore from backup if needed
5. Review this guide for your scenario
