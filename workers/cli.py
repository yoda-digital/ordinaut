#!/usr/bin/env python3
# workers/cli.py
"""
Worker management CLI for Ordinaut.
Provides operational tools for monitoring and managing the distributed worker system.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from workers.coordinator import WorkerCoordinator, monitor_worker_health

def print_json(data):
    """Pretty print JSON data."""
    print(json.dumps(data, indent=2, default=str))

def cmd_status(args):
    """Show worker system status and queue statistics."""
    coordinator = WorkerCoordinator(args.db_url)
    
    print("=== Worker System Status ===\n")
    
    # Active workers
    workers = coordinator.get_active_workers(since_minutes=args.minutes)
    print(f"Active Workers ({len(workers)}):")
    if workers:
        for worker in workers:
            status = "🟢" if worker["seconds_since_heartbeat"] < 60 else "🟡"
            print(f"  {status} {worker['worker_id'][:8]}... "
                  f"(processed: {worker['processed_count']}, "
                  f"last seen: {worker['seconds_since_heartbeat']:.0f}s ago, "
                  f"host: {worker['hostname']}, pid: {worker['pid']})")
    else:
        print("  No active workers found")
    
    print()
    
    # Queue statistics
    queue_stats = coordinator.get_queue_stats()
    print("Queue Statistics:")
    q = queue_stats["queue"]
    p = queue_stats["processing"]
    
    print(f"  📋 Total pending: {q['total_pending']}")
    print(f"  🚀 Ready now: {q['ready_now']}")
    print(f"  🔒 Currently leased: {q['currently_leased']}")
    print(f"  ⚠️  Expired leases: {q['expired_leases']}")
    
    if q['oldest_pending']:
        print(f"  ⏰ Oldest pending: {q['oldest_age_seconds']:.0f}s ago")
    
    print(f"\n  ✅ Recent successes: {p['successful_runs']}")
    print(f"  ❌ Recent failures: {p['failed_runs']}")
    if p['avg_duration_seconds']:
        print(f"  ⏱️  Average duration: {p['avg_duration_seconds']:.1f}s")
    
    # Priority distribution
    if queue_stats["priority_distribution"]:
        print(f"\nPending Work by Priority:")
        for priority_stat in queue_stats["priority_distribution"]:
            priority = priority_stat["priority"]
            count = priority_stat["pending_count"]
            bars = "█" * min(count, 20) + "░" * max(0, 20 - count)
            print(f"  Priority {priority}: {count:3d} [{bars}]")

def cmd_workers(args):
    """List detailed information about workers."""
    coordinator = WorkerCoordinator(args.db_url)
    
    if args.worker_id:
        # Show specific worker details
        stats = coordinator.get_worker_stats(args.worker_id)
        if not stats:
            print(f"Worker {args.worker_id} not found")
            sys.exit(1)
        
        print(f"=== Worker Details: {args.worker_id} ===")
        print_json(stats)
    else:
        # List all workers
        workers = coordinator.get_active_workers(since_minutes=args.minutes)
        print(f"=== All Workers (last {args.minutes} minutes) ===")
        print_json(workers)

def cmd_cleanup(args):
    """Clean up stale leases and expired work items."""
    coordinator = WorkerCoordinator(args.db_url)
    
    print("=== Cleanup Operations ===")
    
    # Clean up stale leases
    cleaned_leases = coordinator.cleanup_stale_leases(args.stale_minutes)
    print(f"Cleaned up {cleaned_leases} stale leases")
    
    # Run health monitoring
    health_report = monitor_worker_health(args.db_url, args.stale_minutes)
    print(f"Found {health_report['unhealthy_workers']} unhealthy workers out of {health_report['total_workers']} total")
    
    if args.verbose and health_report['unhealthy_details']:
        print("\nUnhealthy workers:")
        for worker in health_report['unhealthy_details']:
            print(f"  {worker['worker_id']}: last seen {worker['seconds_since_heartbeat']:.0f}s ago")

def cmd_rebalance(args):
    """Rebalance work across active workers."""
    coordinator = WorkerCoordinator(args.db_url)
    
    print("=== Load Rebalancing ===")
    
    result = coordinator.rebalance_work(args.max_leases)
    print(f"Status: {result['status']}")
    print(f"Total redistributed: {result['total_redistributed']}")
    print(f"Active workers: {result['active_workers']}")
    
    if result['actions']:
        print("\nActions taken:")
        for action in result['actions']:
            print(f"  • {action}")

def cmd_queue(args):
    """Show detailed queue information."""
    coordinator = WorkerCoordinator(args.db_url)
    queue_stats = coordinator.get_queue_stats()
    
    print("=== Queue Statistics ===")
    print_json(queue_stats)

def cmd_monitor(args):
    """Run continuous monitoring."""
    print(f"Starting continuous monitoring (checking every {args.interval}s)...")
    print("Press Ctrl+C to stop\n")
    
    try:
        import time
        while True:
            print(f"\n=== {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} ===")
            
            # Run status check
            temp_args = argparse.Namespace(db_url=args.db_url, minutes=5)
            cmd_status(temp_args)
            
            # Check for issues
            coordinator = WorkerCoordinator(args.db_url)
            health_report = monitor_worker_health(args.db_url, 5)
            
            if health_report['unhealthy_workers'] > 0:
                print(f"\n⚠️  WARNING: {health_report['unhealthy_workers']} unhealthy workers detected!")
            
            queue_stats = coordinator.get_queue_stats()
            if queue_stats['queue']['expired_leases'] > 0:
                print(f"⚠️  WARNING: {queue_stats['queue']['expired_leases']} expired leases detected!")
            
            if queue_stats['queue']['oldest_age_seconds'] and queue_stats['queue']['oldest_age_seconds'] > 300:
                print(f"⚠️  WARNING: Oldest pending work is {queue_stats['queue']['oldest_age_seconds']:.0f}s old!")
            
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

def main():
    parser = argparse.ArgumentParser(
        description="Worker management CLI for Ordinaut",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s status                           # Show system status
  %(prog)s workers                          # List all active workers  
  %(prog)s workers --worker-id worker-123   # Show specific worker details
  %(prog)s cleanup --stale-minutes 10      # Clean up stale leases
  %(prog)s rebalance --max-leases 5         # Rebalance work load
  %(prog)s monitor --interval 30            # Continuous monitoring
        """
    )
    
    # Global options
    parser.add_argument('--db-url', 
                       default=os.environ.get('DATABASE_URL'),
                       help='Database URL (default: DATABASE_URL env var)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show worker system status')
    status_parser.add_argument('--minutes', '-m', type=int, default=5,
                              help='Consider workers active within N minutes (default: 5)')
    
    # Workers command
    workers_parser = subparsers.add_parser('workers', help='List workers')
    workers_parser.add_argument('--worker-id', help='Show details for specific worker')
    workers_parser.add_argument('--minutes', '-m', type=int, default=60,
                               help='Show workers active within N minutes (default: 60)')
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up stale leases')
    cleanup_parser.add_argument('--stale-minutes', type=int, default=10,
                               help='Consider workers stale after N minutes (default: 10)')
    
    # Rebalance command
    rebalance_parser = subparsers.add_parser('rebalance', help='Rebalance work load')
    rebalance_parser.add_argument('--max-leases', type=int, default=5,
                                 help='Maximum leases per worker (default: 5)')
    
    # Queue command
    queue_parser = subparsers.add_parser('queue', help='Show queue statistics')
    
    # Monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Continuous monitoring')
    monitor_parser.add_argument('--interval', type=int, default=30,
                               help='Check interval in seconds (default: 30)')
    
    args = parser.parse_args()
    
    if not args.db_url:
        print("Error: DATABASE_URL must be provided via --db-url or environment variable")
        sys.exit(1)
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == 'status':
            cmd_status(args)
        elif args.command == 'workers':
            cmd_workers(args)
        elif args.command == 'cleanup':
            cmd_cleanup(args)
        elif args.command == 'rebalance':
            cmd_rebalance(args)
        elif args.command == 'queue':
            cmd_queue(args)
        elif args.command == 'monitor':
            cmd_monitor(args)
        else:
            print(f"Unknown command: {args.command}")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()