# Backup Procedures
## Enterprise Task Scheduling System Data Protection

### Backup Strategy Overview
- **PostgreSQL**: Full daily backups + WAL-E continuous archiving
- **Redis**: RDB snapshots every 6 hours
- **Configuration**: Daily backup of all config files
- **Retention**: 30 days local, 90 days off-site
- **Testing**: Weekly restore verification

---

## 1. AUTOMATED BACKUP SETUP

### PostgreSQL Continuous Backup Configuration
```bash
#!/bin/bash
# setup_postgres_backup.sh - Configure PostgreSQL for continuous backup

# 1. Create backup directories
mkdir -p /backups/postgres/{base,wal,daily}
mkdir -p /backups/postgres/archive
chown -R 999:999 /backups/postgres/  # PostgreSQL user in container

# 2. Configure PostgreSQL for WAL archiving
cat >> /var/lib/docker/volumes/task_scheduler_pgdata/_data/postgresql.conf << EOF

# WAL archiving configuration
wal_level = replica
archive_mode = on
archive_command = 'cp %p /backups/postgres/wal/%f'
archive_timeout = 300  # Force WAL switch every 5 minutes
max_wal_senders = 3
wal_keep_segments = 32

# Backup configuration  
hot_standby = on
log_statement = 'all'  # Full query logging for audit
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
EOF

# 3. Restart PostgreSQL to apply configuration
docker-compose -f ops/docker-compose.yml restart postgres

# 4. Verify WAL archiving is working
sleep 30
docker exec postgres psql -U orchestrator -c "SELECT pg_switch_wal();"
sleep 10
ls -la /backups/postgres/wal/ | tail -5
```

### Daily Backup Script Setup
```bash
#!/bin/bash
# daily_backup.sh - Comprehensive daily backup script

LOG_FILE="/var/log/backups/$(date +%Y-%m-%d).log"
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

exec > >(tee -a "$LOG_FILE") 2>&1

echo "=== TASK SCHEDULER DAILY BACKUP STARTED: $(date) ==="

# 1. PostgreSQL Full Backup
echo "### PostgreSQL Backup ###"
POSTGRES_BACKUP_FILE="/backups/postgres/daily/task_scheduler_${BACKUP_DATE}.sql"

if docker exec postgres pg_dump -U orchestrator -v orchestrator > "$POSTGRES_BACKUP_FILE"; then
  echo "✅ PostgreSQL backup completed: $POSTGRES_BACKUP_FILE"
  
  # Compress backup
  gzip "$POSTGRES_BACKUP_FILE"
  echo "✅ PostgreSQL backup compressed: ${POSTGRES_BACKUP_FILE}.gz"
  
  # Verify backup integrity
  if gunzip -t "${POSTGRES_BACKUP_FILE}.gz"; then
    echo "✅ PostgreSQL backup integrity verified"
  else
    echo "❌ PostgreSQL backup corruption detected!"
    exit 1
  fi
  
  # Extract backup statistics
  BACKUP_SIZE=$(du -h "${POSTGRES_BACKUP_FILE}.gz" | cut -f1)
  echo "PostgreSQL backup size: $BACKUP_SIZE"
  
else
  echo "❌ PostgreSQL backup FAILED!"
  exit 1
fi

# 2. Redis Backup
echo -e "\n### Redis Backup ###"
REDIS_BACKUP_FILE="/backups/redis/redis_${BACKUP_DATE}.rdb"

# Force Redis to save current state
if docker exec redis redis-cli BGSAVE; then
  # Wait for background save to complete
  sleep 10
  while docker exec redis redis-cli LASTSAVE | grep -q $(docker exec redis redis-cli LASTSAVE); do
    sleep 5
    echo "Waiting for Redis BGSAVE to complete..."
  done
  
  # Copy RDB file
  if docker cp redis:/data/dump.rdb "$REDIS_BACKUP_FILE"; then
    echo "✅ Redis backup completed: $REDIS_BACKUP_FILE"
    
    # Compress Redis backup
    gzip "$REDIS_BACKUP_FILE"
    echo "✅ Redis backup compressed: ${REDIS_BACKUP_FILE}.gz"
    
    REDIS_SIZE=$(du -h "${REDIS_BACKUP_FILE}.gz" | cut -f1)
    echo "Redis backup size: $REDIS_SIZE"
  else
    echo "❌ Redis backup copy FAILED!"
  fi
else
  echo "❌ Redis BGSAVE FAILED!"
fi

# 3. Configuration Backup
echo -e "\n### Configuration Backup ###"
CONFIG_BACKUP_FILE="/backups/config/task_scheduler_config_${BACKUP_DATE}.tar.gz"

if tar czf "$CONFIG_BACKUP_FILE" \
  ops/docker-compose*.yml \
  ops/prometheus/ \
  ops/grafana/ \
  ops/alertmanager/ \
  ops/loki/ \
  ops/promtail/ \
  migrations/ \
  CLAUDE.md \
  plan.md; then
  echo "✅ Configuration backup completed: $CONFIG_BACKUP_FILE"
  
  CONFIG_SIZE=$(du -h "$CONFIG_BACKUP_FILE" | cut -f1)
  echo "Configuration backup size: $CONFIG_SIZE"
else
  echo "❌ Configuration backup FAILED!"
fi

# 4. Application Code Backup (Git repository)
echo -e "\n### Application Code Backup ###"
CODE_BACKUP_FILE="/backups/code/task_scheduler_code_${BACKUP_DATE}.tar.gz"

if tar czf "$CODE_BACKUP_FILE" \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.venv' \
  --exclude='node_modules' \
  .; then
  echo "✅ Application code backup completed: $CODE_BACKUP_FILE"
  
  CODE_SIZE=$(du -h "$CODE_BACKUP_FILE" | cut -f1)
  echo "Application code backup size: $CODE_SIZE"
else
  echo "❌ Application code backup FAILED!"
fi

# 5. Backup Verification
echo -e "\n### Backup Verification ###"
echo "Verifying backup files exist and are non-empty..."

for backup_file in "${POSTGRES_BACKUP_FILE}.gz" "${REDIS_BACKUP_FILE}.gz" "$CONFIG_BACKUP_FILE" "$CODE_BACKUP_FILE"; do
  if [ -f "$backup_file" ] && [ -s "$backup_file" ]; then
    echo "✅ $(basename $backup_file): $(du -h $backup_file | cut -f1)"
  else
    echo "❌ $(basename $backup_file): Missing or empty!"
  fi
done

# 6. Cleanup Old Backups (retention policy)
echo -e "\n### Backup Retention Cleanup ###"
echo "Cleaning backups older than $RETENTION_DAYS days..."

find /backups/postgres/daily/ -name "*.gz" -mtime +$RETENTION_DAYS -delete
find /backups/redis/ -name "*.gz" -mtime +$RETENTION_DAYS -delete
find /backups/config/ -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
find /backups/code/ -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

# Clean WAL files older than 7 days (shorter retention)
find /backups/postgres/wal/ -name "*" -mtime +7 -delete

echo "Cleanup completed"

# 7. Off-site Backup Sync (if configured)
if [ -n "$OFFSITE_BACKUP_LOCATION" ]; then
  echo -e "\n### Off-site Backup Sync ###"
  
  # Example: rsync to remote location
  rsync -av --delete /backups/ "$OFFSITE_BACKUP_LOCATION"
  
  # Example: AWS S3 sync (if aws cli configured)
  # aws s3 sync /backups/ s3://orchestrator-backups/$(date +%Y/%m/%d)/
  
  echo "Off-site sync completed"
fi

# 8. Backup Summary Report
echo -e "\n### Backup Summary ###"
TOTAL_BACKUP_SIZE=$(du -sh /backups/ | cut -f1)
echo "Total backup storage used: $TOTAL_BACKUP_SIZE"

echo "Backup files created today:"
find /backups/ -name "*${BACKUP_DATE%_*}*" -type f -exec ls -lh {} \;

echo "=== TASK SCHEDULER DAILY BACKUP COMPLETED: $(date) ==="

# Send backup report (if configured)
if [ -n "$BACKUP_REPORT_EMAIL" ]; then
  mail -s "Task Scheduler Backup Report - $(date +%Y-%m-%d)" "$BACKUP_REPORT_EMAIL" < "$LOG_FILE"
fi
```

### Cron Job Setup
```bash
# Install backup scripts
sudo cp daily_backup.sh /usr/local/bin/
sudo cp setup_postgres_backup.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/{daily_backup.sh,setup_postgres_backup.sh}

# Create backup log directory
sudo mkdir -p /var/log/backups
sudo chown $USER:$USER /var/log/backups

# Add to crontab
(crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/daily_backup.sh") | crontab -

# Verify cron job
crontab -l | grep backup
```

---

## 2. MANUAL BACKUP PROCEDURES

### On-Demand Full Backup
```bash
#!/bin/bash
# manual_backup.sh - Manual backup for maintenance windows

BACKUP_REASON=${1:-"manual"}
BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== MANUAL BACKUP INITIATED: $BACKUP_REASON - $(date) ==="

# 1. Create maintenance backup directory
BACKUP_DIR="/backups/manual/${BACKUP_TIMESTAMP}_${BACKUP_REASON}"
mkdir -p "$BACKUP_DIR"

# 2. Stop application services (preserve data services)
echo "Stopping application services for consistent backup..."
docker-compose -f ops/docker-compose.yml stop api scheduler worker

# 3. PostgreSQL consistent backup
echo "Creating consistent PostgreSQL backup..."
docker exec postgres pg_dump -U orchestrator orchestrator > "$BACKUP_DIR/postgres_consistent.sql"

# 4. PostgreSQL base backup (for PITR)
echo "Creating PostgreSQL base backup..."
docker exec postgres pg_basebackup -U orchestrator -D /tmp/base_backup -Ft -z
docker cp postgres:/tmp/base_backup/base.tar.gz "$BACKUP_DIR/"

# 5. Redis snapshot
echo "Creating Redis snapshot..."
docker exec redis redis-cli BGSAVE
sleep 5
docker cp redis:/data/dump.rdb "$BACKUP_DIR/redis_snapshot.rdb"

# 6. Full configuration snapshot
echo "Backing up configuration..."
tar czf "$BACKUP_DIR/complete_config.tar.gz" \
  ops/ migrations/ api/ engine/ scheduler/ workers/ \
  CLAUDE.md plan.md requirements.txt

# 7. Docker volumes backup
echo "Backing up Docker volumes..."
docker run --rm -v task_scheduler_pgdata:/data -v "$BACKUP_DIR":/backup busybox tar czf /backup/pgdata_volume.tar.gz -C /data .
docker run --rm -v task_scheduler_redisdata:/data -v "$BACKUP_DIR":/backup busybox tar czf /backup/redisdata_volume.tar.gz -C /data .

# 8. System state capture
echo "Capturing system state..."
docker ps -a > "$BACKUP_DIR/docker_containers.txt"
docker images > "$BACKUP_DIR/docker_images.txt"
docker network ls > "$BACKUP_DIR/docker_networks.txt"
docker volume ls > "$BACKUP_DIR/docker_volumes.txt"

# 9. Restart services
echo "Restarting application services..."
docker-compose -f ops/docker-compose.yml up -d api scheduler worker

# 10. Backup verification
echo "Verifying backup integrity..."
for file in "$BACKUP_DIR"/*.{sql,tar.gz,rdb}; do
  if [ -f "$file" ]; then
    echo "✅ $(basename $file): $(du -h $file | cut -f1)"
  fi
done

echo "Manual backup completed: $BACKUP_DIR"
echo "Total backup size: $(du -sh $BACKUP_DIR | cut -f1)"
```

### Quick Database Export
```bash
#!/bin/bash
# quick_db_export.sh - Fast database export without service interruption

EXPORT_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPORT_FILE="/tmp/task_scheduler_export_${EXPORT_TIMESTAMP}.sql"

echo "Creating quick database export..."

# Schema-only export (fast)
docker exec postgres pg_dump -U orchestrator --schema-only orchestrator > "${EXPORT_FILE}.schema"

# Data-only export (may take longer)
docker exec postgres pg_dump -U orchestrator --data-only orchestrator > "${EXPORT_FILE}.data"

# Complete export (structure + data)
docker exec postgres pg_dump -U orchestrator orchestrator > "$EXPORT_FILE"

echo "Database export completed:"
echo "Schema: ${EXPORT_FILE}.schema ($(du -h ${EXPORT_FILE}.schema | cut -f1))"
echo "Data: ${EXPORT_FILE}.data ($(du -h ${EXPORT_FILE}.data | cut -f1))"
echo "Complete: $EXPORT_FILE ($(du -h $EXPORT_FILE | cut -f1))"

# Compress exports
gzip "${EXPORT_FILE}"*

echo "Compressed exports available in /tmp/"
```

---

## 3. BACKUP VERIFICATION & TESTING

### Weekly Backup Verification Script
```bash
#!/bin/bash
# verify_backups.sh - Weekly backup integrity verification

echo "=== BACKUP VERIFICATION - $(date) ==="

# 1. Find most recent backups
LATEST_POSTGRES=$(ls -t /backups/postgres/daily/*.gz | head -1)
LATEST_REDIS=$(ls -t /backups/redis/*.gz | head -1)
LATEST_CONFIG=$(ls -t /backups/config/*.tar.gz | head -1)

echo "Verifying backup files:"
echo "PostgreSQL: $LATEST_POSTGRES"
echo "Redis: $LATEST_REDIS"  
echo "Config: $LATEST_CONFIG"

# 2. PostgreSQL backup verification
echo -e "\n### PostgreSQL Backup Verification ###"
if [ -f "$LATEST_POSTGRES" ]; then
  # Test decompression
  if gunzip -t "$LATEST_POSTGRES"; then
    echo "✅ PostgreSQL backup decompresses successfully"
    
    # Test SQL syntax (basic check)
    if gunzip -c "$LATEST_POSTGRES" | head -50 | grep -q "PostgreSQL database dump"; then
      echo "✅ PostgreSQL backup has valid SQL header"
    else
      echo "❌ PostgreSQL backup missing valid SQL header"
    fi
    
    # Extract key statistics
    BACKUP_SIZE=$(du -h "$LATEST_POSTGRES" | cut -f1)
    BACKUP_DATE=$(stat -c %y "$LATEST_POSTGRES" | cut -d' ' -f1)
    echo "PostgreSQL backup: $BACKUP_SIZE (created: $BACKUP_DATE)"
    
  else
    echo "❌ PostgreSQL backup failed decompression test"
  fi
else
  echo "❌ No PostgreSQL backup found"
fi

# 3. Redis backup verification
echo -e "\n### Redis Backup Verification ###"
if [ -f "$LATEST_REDIS" ]; then
  if gunzip -t "$LATEST_REDIS"; then
    echo "✅ Redis backup decompresses successfully"
    
    REDIS_SIZE=$(du -h "$LATEST_REDIS" | cut -f1)
    REDIS_DATE=$(stat -c %y "$LATEST_REDIS" | cut -d' ' -f1)
    echo "Redis backup: $REDIS_SIZE (created: $REDIS_DATE)"
    
  else
    echo "❌ Redis backup failed decompression test"
  fi
else
  echo "❌ No Redis backup found"
fi

# 4. Configuration backup verification
echo -e "\n### Configuration Backup Verification ###"
if [ -f "$LATEST_CONFIG" ]; then
  if tar -tzf "$LATEST_CONFIG" > /dev/null 2>&1; then
    echo "✅ Configuration backup is valid tar.gz"
    
    # Check for key configuration files
    if tar -tzf "$LATEST_CONFIG" | grep -q "docker-compose.yml"; then
      echo "✅ Configuration backup contains Docker Compose files"
    else
      echo "⚠️  Configuration backup missing Docker Compose files"
    fi
    
    CONFIG_SIZE=$(du -h "$LATEST_CONFIG" | cut -f1)
    CONFIG_DATE=$(stat -c %y "$LATEST_CONFIG" | cut -d' ' -f1)
    echo "Configuration backup: $CONFIG_SIZE (created: $CONFIG_DATE)"
    
  else
    echo "❌ Configuration backup is corrupted"
  fi
else
  echo "❌ No configuration backup found"
fi

# 5. Backup age verification
echo -e "\n### Backup Freshness Check ###"
YESTERDAY=$(date -d '1 day ago' +%Y-%m-%d)

for backup_dir in /backups/postgres/daily /backups/redis /backups/config; do
  RECENT_BACKUPS=$(find "$backup_dir" -name "*" -newermt "$YESTERDAY" | wc -l)
  if [ "$RECENT_BACKUPS" -gt 0 ]; then
    echo "✅ $backup_dir: $RECENT_BACKUPS recent backup(s)"
  else
    echo "❌ $backup_dir: No backups from last 24 hours"
  fi
done

# 6. Storage capacity check
echo -e "\n### Storage Capacity Check ###"
BACKUP_USAGE=$(du -sh /backups | cut -f1)
BACKUP_AVAILABLE=$(df -h /backups | tail -1 | awk '{print $4}')
echo "Backup storage used: $BACKUP_USAGE"
echo "Available space: $BACKUP_AVAILABLE"

# Check if we're using >80% of available space
USAGE_PERCENT=$(df /backups | tail -1 | awk '{print $5}' | tr -d '%')
if [ "$USAGE_PERCENT" -gt 80 ]; then
  echo "⚠️  Backup storage >80% full - cleanup recommended"
else
  echo "✅ Backup storage capacity OK"
fi

echo -e "\n=== BACKUP VERIFICATION COMPLETED ==="
```

### Test Restore Procedure (Monthly)
```bash
#!/bin/bash
# test_restore.sh - Monthly backup restore test

TEST_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEST_DIR="/tmp/restore_test_$TEST_TIMESTAMP"
mkdir -p "$TEST_DIR"

echo "=== BACKUP RESTORE TEST - $(date) ==="

# 1. Setup test environment
echo "Setting up test environment..."

# Create test docker-compose for isolated testing
cat > "$TEST_DIR/docker-compose.test.yml" << EOF
version: '3.8'
services:
  test-postgres:
    image: postgres:16.4
    environment:
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_pass
      POSTGRES_DB: test_orchestrator
    ports:
      - "5433:5432"
    volumes:
      - test_pgdata:/var/lib/postgresql/data

  test-redis:
    image: redis:7.2.5
    ports:
      - "6380:6379"
    volumes:
      - test_redisdata:/data

volumes:
  test_pgdata:
  test_redisdata:
EOF

# 2. Start test containers
echo "Starting test containers..."
cd "$TEST_DIR"
docker-compose -f docker-compose.test.yml up -d

# Wait for containers to be ready
sleep 15
timeout 60s bash -c 'until docker exec test_restore_${TEST_TIMESTAMP}_test-postgres_1 pg_isready -U test_user; do sleep 2; done'

# 3. Test PostgreSQL restore
echo -e "\n### Testing PostgreSQL Restore ###"
LATEST_POSTGRES_BACKUP=$(ls -t /backups/postgres/daily/*.gz | head -1)

if [ -f "$LATEST_POSTGRES_BACKUP" ]; then
  echo "Restoring from: $LATEST_POSTGRES_BACKUP"
  
  # Restore backup to test database
  gunzip -c "$LATEST_POSTGRES_BACKUP" | \
    docker exec -i test_restore_${TEST_TIMESTAMP}_test-postgres_1 \
    psql -U test_user -d test_orchestrator
  
  if [ $? -eq 0 ]; then
    echo "✅ PostgreSQL restore completed successfully"
    
    # Verify restored data
    TABLE_COUNT=$(docker exec test_restore_${TEST_TIMESTAMP}_test-postgres_1 \
      psql -U test_user -d test_orchestrator -t -c \
      "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';")
    
    echo "Restored tables: $TABLE_COUNT"
    
    # Check specific table data
    TASK_COUNT=$(docker exec test_restore_${TEST_TIMESTAMP}_test-postgres_1 \
      psql -U test_user -d test_orchestrator -t -c \
      "SELECT COUNT(*) FROM task;" 2>/dev/null || echo "0")
    
    echo "Restored tasks: $TASK_COUNT"
    
    if [ "$TABLE_COUNT" -gt 5 ]; then
      echo "✅ PostgreSQL restore verification PASSED"
    else
      echo "❌ PostgreSQL restore verification FAILED - insufficient tables"
    fi
    
  else
    echo "❌ PostgreSQL restore FAILED"
  fi
else
  echo "❌ No PostgreSQL backup found for testing"
fi

# 4. Test Redis restore  
echo -e "\n### Testing Redis Restore ###"
LATEST_REDIS_BACKUP=$(ls -t /backups/redis/*.gz | head -1)

if [ -f "$LATEST_REDIS_BACKUP" ]; then
  echo "Restoring from: $LATEST_REDIS_BACKUP"
  
  # Stop test Redis, replace RDB file, restart
  docker-compose -f docker-compose.test.yml stop test-redis
  
  # Copy and restore RDB file
  gunzip -c "$LATEST_REDIS_BACKUP" > "$TEST_DIR/dump.rdb"
  docker cp "$TEST_DIR/dump.rdb" test_restore_${TEST_TIMESTAMP}_test-redis_1:/data/
  
  docker-compose -f docker-compose.test.yml start test-redis
  sleep 10
  
  # Verify Redis restore
  if docker exec test_restore_${TEST_TIMESTAMP}_test-redis_1 redis-cli ping | grep -q PONG; then
    echo "✅ Redis restore completed successfully"
    
    # Check for data
    KEY_COUNT=$(docker exec test_restore_${TEST_TIMESTAMP}_test-redis_1 \
      redis-cli info keyspace | grep -c "keys=" || echo "0")
    echo "Restored Redis keyspaces: $KEY_COUNT"
    
  else
    echo "❌ Redis restore FAILED"
  fi
else
  echo "❌ No Redis backup found for testing"
fi

# 5. Configuration restore test
echo -e "\n### Testing Configuration Restore ###"
LATEST_CONFIG_BACKUP=$(ls -t /backups/config/*.tar.gz | head -1)

if [ -f "$LATEST_CONFIG_BACKUP" ]; then
  CONFIG_TEST_DIR="$TEST_DIR/config_test"
  mkdir -p "$CONFIG_TEST_DIR"
  
  if tar -xzf "$LATEST_CONFIG_BACKUP" -C "$CONFIG_TEST_DIR"; then
    echo "✅ Configuration backup extracted successfully"
    
    # Verify key files exist
    KEY_FILES="docker-compose.yml prometheus/prometheus.yml"
    ALL_FOUND=true
    
    for file in $KEY_FILES; do
      if [ -f "$CONFIG_TEST_DIR/ops/$file" ]; then
        echo "✅ Found: $file"
      else
        echo "❌ Missing: $file"
        ALL_FOUND=false
      fi
    done
    
    if $ALL_FOUND; then
      echo "✅ Configuration restore verification PASSED"
    else
      echo "❌ Configuration restore verification FAILED"
    fi
  else
    echo "❌ Configuration backup extraction FAILED"
  fi
else
  echo "❌ No configuration backup found for testing"
fi

# 6. Cleanup test environment
echo -e "\n### Cleanup Test Environment ###"
cd "$TEST_DIR"
docker-compose -f docker-compose.test.yml down -v
rm -rf "$TEST_DIR"

echo "=== BACKUP RESTORE TEST COMPLETED ==="
```

---

## 4. DISASTER RECOVERY INTEGRATION

### Point-in-Time Recovery Setup
```bash
#!/bin/bash
# setup_pitr.sh - Configure Point-in-Time Recovery

echo "Setting up Point-in-Time Recovery (PITR)..."

# 1. Enable WAL archiving if not already done
docker exec postgres psql -U orchestrator -c "
ALTER SYSTEM SET wal_level = 'replica';
ALTER SYSTEM SET archive_mode = 'on';
ALTER SYSTEM SET archive_command = 'cp %p /backups/postgres/wal/%f';
ALTER SYSTEM SET archive_timeout = '300';
"

# 2. Create base backup script
cat > /usr/local/bin/create_base_backup.sh << 'EOF'
#!/bin/bash
BASE_BACKUP_DIR="/backups/postgres/base/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BASE_BACKUP_DIR"

echo "Creating base backup: $BASE_BACKUP_DIR"

# Create base backup
docker exec postgres pg_basebackup \
  -U orchestrator \
  -D "/tmp/base_backup" \
  -Ft -z -P

# Copy base backup out of container
docker cp postgres:/tmp/base_backup/base.tar.gz "$BASE_BACKUP_DIR/"
docker cp postgres:/tmp/base_backup/pg_wal.tar.gz "$BASE_BACKUP_DIR/"

# Create backup_label with timestamp
echo "BASE_BACKUP_TIMESTAMP=$(date -Iseconds)" > "$BASE_BACKUP_DIR/backup_label"

echo "Base backup completed: $BASE_BACKUP_DIR"

# Cleanup old base backups (keep last 7)
ls -t /backups/postgres/base/ | tail -n +8 | xargs -I {} rm -rf /backups/postgres/base/{}
EOF

chmod +x /usr/local/bin/create_base_backup.sh

# 3. Schedule base backup (daily at 1 AM)
(crontab -l 2>/dev/null; echo "0 1 * * * /usr/local/bin/create_base_backup.sh") | crontab -

echo "PITR setup completed"
```

### Cross-Region Backup Replication
```bash
#!/bin/bash
# setup_offsite_backup.sh - Configure off-site backup replication

REMOTE_HOST=${1:-"backup-server.example.com"}
REMOTE_PATH=${2:-"/backups/task_scheduler"}
BACKUP_KEY=${3:-"~/.ssh/backup_key"}

echo "Setting up off-site backup replication to $REMOTE_HOST:$REMOTE_PATH"

# 1. Test SSH connectivity
if ssh -i "$BACKUP_KEY" "$REMOTE_HOST" "mkdir -p $REMOTE_PATH"; then
  echo "✅ Remote backup location accessible"
else
  echo "❌ Cannot access remote backup location"
  exit 1
fi

# 2. Create sync script
cat > /usr/local/bin/sync_offsite_backups.sh << EOF
#!/bin/bash
# Sync backups to off-site location

LOCK_FILE="/tmp/backup_sync.lock"

# Prevent concurrent runs
if [ -f "\$LOCK_FILE" ]; then
  echo "Backup sync already running"
  exit 1
fi

echo "\$\$" > "\$LOCK_FILE"

echo "Starting off-site backup sync: \$(date)"

# Sync PostgreSQL backups
rsync -avz --delete \
  -e "ssh -i $BACKUP_KEY" \
  /backups/postgres/ \
  $REMOTE_HOST:$REMOTE_PATH/postgres/

# Sync Redis backups
rsync -avz --delete \
  -e "ssh -i $BACKUP_KEY" \
  /backups/redis/ \
  $REMOTE_HOST:$REMOTE_PATH/redis/

# Sync configuration backups
rsync -avz --delete \
  -e "ssh -i $BACKUP_KEY" \
  /backups/config/ \
  $REMOTE_HOST:$REMOTE_PATH/config/

echo "Off-site backup sync completed: \$(date)"

rm "\$LOCK_FILE"
EOF

chmod +x /usr/local/bin/sync_offsite_backups.sh

# 3. Schedule off-site sync (every 6 hours)
(crontab -l 2>/dev/null; echo "0 */6 * * * /usr/local/bin/sync_offsite_backups.sh") | crontab -

echo "Off-site backup replication configured"
```

**Last Updated**: 2025-01-10  
**Next Review**: 2025-04-10  
**Owner**: Operations Team  
**Approver**: Technical Lead