#!/bin/bash
set -e

# Ordinaut - Health Check Script
# Can be used by external monitoring systems or load balancers

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_URL="${API_URL:-http://localhost:8080}"
TIMEOUT="${TIMEOUT:-10}"
VERBOSE="${VERBOSE:-false}"

log() {
    if [ "$VERBOSE" = "true" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
    fi
}

check_api() {
    log "Checking API health endpoint..."
    
    if ! curl -s -f --max-time "$TIMEOUT" "$API_URL/health" > /dev/null 2>&1; then
        echo "❌ API health check failed"
        return 1
    fi
    
    log "✅ API is healthy"
    return 0
}

check_database() {
    log "Checking database connectivity..."
    
    if ! docker compose exec -T postgres pg_isready -U orchestrator > /dev/null 2>&1; then
        echo "❌ Database health check failed"
        return 1
    fi
    
    log "✅ Database is healthy"
    return 0
}

check_redis() {
    log "Checking Redis connectivity..."
    
    if ! docker compose exec -T redis redis-cli ping > /dev/null 2>&1; then
        echo "❌ Redis health check failed"
        return 1
    fi
    
    log "✅ Redis is healthy"
    return 0
}

check_services_running() {
    log "Checking if all services are running..."
    
    local services=("postgres" "redis" "api" "scheduler" "worker")
    local failed_services=()
    
    for service in "${services[@]}"; do
        if ! docker compose ps "$service" --format json | jq -r '.State' | grep -q "running" 2>/dev/null; then
            failed_services+=("$service")
        fi
    done
    
    if [ ${#failed_services[@]} -gt 0 ]; then
        echo "❌ Services not running: ${failed_services[*]}"
        return 1
    fi
    
    log "✅ All services are running"
    return 0
}

check_queue_health() {
    log "Checking job queue health..."
    
    # Check if there are any very old jobs stuck in the queue (older than 10 minutes)
    local old_jobs
    old_jobs=$(docker compose exec -T postgres psql -U orchestrator -t -c "
        SELECT COUNT(*) 
        FROM due_work 
        WHERE run_at < NOW() - INTERVAL '10 minutes'
            AND (locked_until IS NULL OR locked_until < NOW())
    " 2>/dev/null | tr -d ' ')
    
    if [ "$old_jobs" -gt 10 ]; then
        echo "⚠️  Warning: $old_jobs old jobs in queue (possible worker issue)"
        return 1
    fi
    
    log "✅ Job queue is healthy"
    return 0
}

main() {
    local exit_code=0
    
    cd "$SCRIPT_DIR" 2>/dev/null || {
        echo "❌ Cannot change to ops directory"
        exit 1
    }
    
    echo "🏥 Ordinaut - Health Check"
    echo "============================================"
    
    # Basic service checks
    if ! check_services_running; then
        exit_code=1
    fi
    
    if ! check_database; then
        exit_code=1
    fi
    
    if ! check_redis; then
        exit_code=1
    fi
    
    if ! check_api; then
        exit_code=1
    fi
    
    # Application-specific health checks
    if ! check_queue_health; then
        exit_code=1
    fi
    
    echo ""
    if [ $exit_code -eq 0 ]; then
        echo "✅ All health checks passed"
    else
        echo "❌ Some health checks failed"
    fi
    
    return $exit_code
}

# Handle command line options
while [[ $# -gt 0 ]]; do
    case $1 in
        --verbose|-v)
            VERBOSE="true"
            shift
            ;;
        --timeout|-t)
            TIMEOUT="$2"
            shift 2
            ;;
        --api-url|-u)
            API_URL="$2"
            shift 2
            ;;
        --help|-h)
            cat << EOF
Health Check Script for Ordinaut

Usage: $0 [OPTIONS]

OPTIONS:
    --verbose, -v          Enable verbose output
    --timeout, -t SECONDS  Set timeout for checks (default: 10)
    --api-url, -u URL      Set API URL (default: http://localhost:8080)
    --help, -h             Show this help message

Exit Codes:
    0  All health checks passed
    1  One or more health checks failed

Examples:
    $0                              # Basic health check
    $0 --verbose                    # Verbose output
    $0 --timeout 30                 # 30 second timeout
    $0 --api-url http://api:8080    # Custom API URL

EOF
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

main