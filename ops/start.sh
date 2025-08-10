#!/bin/bash
set -e

# Ordinaut - Docker Startup Script
# Usage: ./start.sh [dev|prod|--help]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

show_help() {
    cat << EOF
Ordinaut - Docker Startup Script

Usage: $0 [ENVIRONMENT] [OPTIONS]

ENVIRONMENT:
    dev     Start in development mode (default)
    prod    Start in production mode

OPTIONS:
    --build     Force rebuild of Docker images
    --clean     Clean up volumes and containers before starting
    --logs      Follow logs after starting
    --help      Show this help message

Examples:
    $0                  # Start in development mode
    $0 dev --build      # Start in dev mode, force rebuild
    $0 prod --clean     # Start in prod mode, clean first
    $0 dev --logs       # Start in dev mode and follow logs

EOF
}

check_requirements() {
    if ! command -v docker &> /dev/null; then
        echo "Error: Docker is not installed or not in PATH"
        exit 1
    fi

    if ! command -v docker compose &> /dev/null; then
        echo "Error: Docker Compose is not available"
        echo "Please install Docker Compose plugin or use 'docker-compose' instead"
        exit 1
    fi

    if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
        echo "Error: requirements.txt not found in project root"
        exit 1
    fi

    if [ ! -f "$PROJECT_ROOT/migrations/version_0001.sql" ]; then
        echo "Error: Database migration file not found"
        exit 1
    fi
}

setup_environment() {
    local env="$1"
    
    if [ "$env" = "prod" ] && [ ! -f "$SCRIPT_DIR/.env" ]; then
        echo "Creating production environment file from template..."
        cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
        echo ""
        echo "⚠️  IMPORTANT: Edit $SCRIPT_DIR/.env with your production values before starting!"
        echo "   Especially update passwords and secret keys."
        echo ""
        read -p "Press Enter to continue or Ctrl+C to abort..."
    fi
}

clean_environment() {
    echo "🧹 Cleaning up existing containers and volumes..."
    
    cd "$SCRIPT_DIR"
    
    # Stop and remove containers
    docker compose down --remove-orphans 2>/dev/null || true
    docker compose -f docker-compose.yml -f docker-compose.dev.yml down --remove-orphans 2>/dev/null || true
    docker compose -f docker-compose.yml -f docker-compose.prod.yml down --remove-orphans 2>/dev/null || true
    
    # Remove volumes
    docker volume rm yoda-tasker_pgdata yoda-tasker_redisdata 2>/dev/null || true
    docker volume rm yoda-tasker_pgdata-dev yoda-tasker_redisdata-dev 2>/dev/null || true
    docker volume rm yoda-tasker_pgdata-prod yoda-tasker_redisdata-prod 2>/dev/null || true
    
    # Prune unused images
    docker image prune -f
    
    echo "✅ Cleanup completed"
}

start_services() {
    local env="$1"
    local build_flag="$2"
    local follow_logs="$3"
    
    cd "$SCRIPT_DIR"
    
    echo "🚀 Starting Ordinaut in $env mode..."
    
    local compose_cmd="docker compose -f docker-compose.yml"
    local build_args=""
    
    if [ "$env" = "dev" ]; then
        compose_cmd="$compose_cmd -f docker-compose.dev.yml"
    elif [ "$env" = "prod" ]; then
        compose_cmd="$compose_cmd -f docker-compose.prod.yml"
        if [ -f ".env" ]; then
            compose_cmd="$compose_cmd --env-file .env"
        fi
    fi
    
    if [ "$build_flag" = "true" ]; then
        build_args="--build"
    fi
    
    # Start services
    echo "Running: $compose_cmd up -d $build_args"
    $compose_cmd up -d $build_args
    
    # Wait for services to be healthy
    echo "⏳ Waiting for services to be ready..."
    sleep 10
    
    # Check service status
    echo "📊 Service Status:"
    $compose_cmd ps
    
    echo ""
    echo "✅ Ordinaut is running!"
    echo ""
    echo "📋 Service URLs:"
    echo "   API:        http://localhost:8080"
    echo "   PostgreSQL: localhost:5432"
    echo "   Redis:      localhost:6379"
    echo ""
    echo "🔧 Useful commands:"
    echo "   View logs:       $compose_cmd logs -f"
    echo "   Stop services:   $compose_cmd down"
    echo "   Restart:         $compose_cmd restart"
    echo "   Shell into API:  $compose_cmd exec api bash"
    echo ""
    
    if [ "$follow_logs" = "true" ]; then
        echo "📝 Following logs (Ctrl+C to stop)..."
        $compose_cmd logs -f
    fi
}

# Parse arguments
ENVIRONMENT="dev"
BUILD_FLAG="false"
CLEAN_FLAG="false"
FOLLOW_LOGS="false"

while [[ $# -gt 0 ]]; do
    case $1 in
        dev|prod)
            ENVIRONMENT="$1"
            shift
            ;;
        --build)
            BUILD_FLAG="true"
            shift
            ;;
        --clean)
            CLEAN_FLAG="true"
            shift
            ;;
        --logs)
            FOLLOW_LOGS="true"
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Main execution
echo "🏗️  Ordinaut - Docker Startup"
echo "============================================="

check_requirements
setup_environment "$ENVIRONMENT"

if [ "$CLEAN_FLAG" = "true" ]; then
    clean_environment
fi

start_services "$ENVIRONMENT" "$BUILD_FLAG" "$FOLLOW_LOGS"