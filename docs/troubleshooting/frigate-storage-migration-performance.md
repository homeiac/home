# Frigate Storage Migration Performance Issues

## Overview
This troubleshooting guide addresses performance issues with the Frigate review interface that can occur after storage migrations, specifically when the review timeline becomes slow to load historical footage.

## Symptoms
- Frigate review interface loads very slowly
- Historical video thumbnails fail to load or show broken images
- Browser network tab shows numerous 404 errors for thumbnail requests
- Current live streams and recent recordings work normally
- Performance degradation started after storage migration or container restart

## Root Cause
During storage migrations or service interruptions, the Frigate review segment manager may fail to generate thumbnail files for events that occurred during the downtime window. This results in:

1. **Orphaned database entries** - Events recorded in SQLite database with `thumb_path` references
2. **Missing thumbnail files** - Actual `.webp` files don't exist on disk  
3. **404 cascade** - Web interface tries to load hundreds of missing thumbnails
4. **Performance degradation** - Each 404 request causes timeouts and delays

## Diagnosis Steps

### 1. Identify the Problem Pattern
Check nginx logs for 404 errors on thumbnail requests:
```bash
ssh root@<frigate-host> "pct exec <container-id> -- tail -50 /dev/shm/logs/nginx/current | grep -E '(404.*thumb|No such file)'"
```

Expected output showing missing thumbnails:
```
2025/08/16 14:27:53 [error] 281#281: *1914 open() "/media/frigate/clips/review/thumb-old_ip_camera-1755369972.528299-tvx7wb.webp" failed (2: No such file or directory)
192.168.4.226 - - [16/Aug/2025:14:27:53 -0700] "GET /clips/review/thumb-old_ip_camera-1755369972.528299-tvx7wb.webp HTTP/1.1" 404 124
```

### 2. Count Orphaned Database Entries
Run diagnostic script to identify orphaned entries:
```bash
ssh root@<frigate-host> "pct exec <container-id> -- python3 -c \"
import sqlite3
import os

conn = sqlite3.connect('/config/frigate.db')
cursor = conn.cursor()

# Get all review segments with thumbnail paths
cursor.execute('SELECT id, thumb_path FROM reviewsegment WHERE thumb_path IS NOT NULL;')
all_entries = cursor.fetchall()

orphaned = []
existing = []

for entry_id, thumb_path in all_entries:
    if os.path.exists(thumb_path):
        existing.append(entry_id)
    else:
        orphaned.append(entry_id)

print(f'Total review segments: {len(all_entries)}')
print(f'Valid entries (files exist): {len(existing)}')
print(f'Orphaned entries (missing files): {len(orphaned)}')

# Show sample orphaned entries
if orphaned:
    print('\\nSample orphaned entries:')
    cursor.execute('SELECT id, start_time, thumb_path FROM reviewsegment WHERE id IN (?, ?, ?)', orphaned[:3])
    for row in cursor.fetchall():
        from datetime import datetime
        dt = datetime.fromtimestamp(row[1])
        print(f'  {row[0]} - {dt} - {row[2]}')

conn.close()
\""
```

### 3. Verify Current Functionality
Ensure current clips are working normally:
```bash
# Test API response
curl -s "http://<frigate-ip>:5000/api/review?limit=5" | jq '. | length'

# Test recent thumbnail access
curl -I "http://<frigate-ip>:5000/clips/review/thumb-<recent-thumbnail>.webp"
```

## Resolution Steps

### Step 1: Stop Frigate Service
```bash
ssh root@<frigate-host> "pct exec <container-id> -- systemctl stop frigate"

# Verify stopped (may take time due to graceful shutdown)
ssh root@<frigate-host> "pct exec <container-id> -- systemctl status frigate | grep Active"
```

**Note**: If service hangs during shutdown, you may need to force kill:
```bash
# Find main process
ssh root@<frigate-host> "pct exec <container-id> -- ps aux | grep 'python.*frigate'"

# Force kill if necessary  
ssh root@<frigate-host> "pct exec <container-id> -- kill -9 <pid>"
```

### Step 2: Backup Database
```bash
ssh root@<frigate-host> "pct exec <container-id> -- cp /config/frigate.db /config/frigate.db.backup-\$(date +%Y%m%d_%H%M%S)"

# Verify backup created
ssh root@<frigate-host> "pct exec <container-id> -- ls -la /config/frigate.db*"
```

### Step 3: Clean Orphaned Entries
Execute the cleanup script with referential integrity:
```bash
ssh root@<frigate-host> "pct exec <container-id> -- python3 -c \"
import sqlite3
import os

print('Starting database cleanup with referential integrity...')
conn = sqlite3.connect('/config/frigate.db')
cursor = conn.cursor()

# Get count before cleanup
cursor.execute('SELECT COUNT(*) FROM reviewsegment;')
total_before = cursor.fetchone()[0]
print(f'Total entries before cleanup: {total_before}')

# Find orphaned entries
cursor.execute('SELECT id, thumb_path FROM reviewsegment WHERE thumb_path IS NOT NULL;')
all_entries = cursor.fetchall()

orphaned_ids = []
for entry_id, thumb_path in all_entries:
    if not os.path.exists(thumb_path):
        orphaned_ids.append(entry_id)

print(f'Found {len(orphaned_ids)} orphaned entries to delete')

# Delete in batches for safety
batch_size = 50
deleted_count = 0

for i in range(0, len(orphaned_ids), batch_size):
    batch = orphaned_ids[i:i+batch_size]
    placeholders = ','.join(['?' for _ in batch])
    
    cursor.execute(f'DELETE FROM reviewsegment WHERE id IN ({placeholders})', batch)
    deleted_count += cursor.rowcount
    print(f'Deleted batch {i//batch_size + 1}: {cursor.rowcount} entries')

# Commit changes
conn.commit()

# Verify integrity
cursor.execute('SELECT COUNT(*) FROM reviewsegment;')
total_after = cursor.fetchone()[0]

print(f'\\nCleanup complete:')
print(f'  Entries before: {total_before}')
print(f'  Entries deleted: {deleted_count}')
print(f'  Entries after: {total_after}')
print(f'  Integrity check: {\\\"PASS\\\" if total_after == total_before - deleted_count else \\\"FAIL\\\"}')

conn.close()
print('Database cleanup completed successfully!')
\""
```

### Step 4: Restart and Verify
```bash
# Start Frigate
ssh root@<frigate-host> "pct exec <container-id> -- systemctl start frigate"

# Wait for startup
sleep 10

# Verify service status
ssh root@<frigate-host> "pct exec <container-id> -- systemctl status frigate | grep Active"

# Test API responsiveness
curl -s "http://<frigate-ip>:5000/api/review?limit=10" | jq '. | length'

# Test web interface
curl -I "http://<frigate-ip>:5000/review"
```

## Verification

### Performance Test
1. **Open Frigate review interface** in browser
2. **Check browser network tab** - should see minimal 404 errors
3. **Scroll through timeline** - should load smoothly without long delays
4. **Verify current functionality** - live streams and recent recordings work normally

### Log Verification
Check that 404 errors for thumbnails have stopped:
```bash
ssh root@<frigate-host> "pct exec <container-id> -- tail -20 /dev/shm/logs/nginx/current | grep -E '(404.*thumb|No such file)'"
```

Should return minimal or no 404 errors for thumbnail requests.

## Prevention

### Best Practices for Storage Migrations
1. **Stop Frigate cleanly** before storage operations
2. **Use ZFS snapshots** for atomic migration operations  
3. **Verify thumbnail directory integrity** after migration
4. **Monitor review segment manager** logs during startup
5. **Test review interface** immediately after migration

### Monitoring
Set up alerts for:
- High 404 error rates in nginx logs
- Review interface performance degradation
- Missing thumbnail file patterns

## Rollback Procedure

If issues occur after cleanup:
```bash
# Stop Frigate
ssh root@<frigate-host> "pct exec <container-id> -- systemctl stop frigate"

# Restore database backup
ssh root@<frigate-host> "pct exec <container-id> -- cp /config/frigate.db.backup-<timestamp> /config/frigate.db"

# Restart Frigate
ssh root@<frigate-host> "pct exec <container-id> -- systemctl start frigate"
```

## Related Issues
- Frigate storage migration procedures
- Database integrity maintenance
- Performance optimization after container restarts
- Review segment manager troubleshooting

## References
- [Frigate Documentation](https://docs.frigate.video/)
- [Storage Migration Guide](../md/samsung-to-hdd-migration-plan.md)
- [Frigate Home Assistant Integration](../md/frigate-homeassistant-integration-guide.md)