"""
Health monitoring module for tracking system health during long-running operations.

Monitors:
- Memory usage
- Thread count
- Database size
- Enrichment queue depth
- API error rates
"""

import logging
import os
import threading
import time
from pathlib import Path

import psutil

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitor system health metrics during long-running operations."""

    def __init__(self, db_path: str = "assistant_memory.db", check_interval: int = 300):
        """
        Initialize health monitor.

        Args:
            db_path: Path to database file for size monitoring
            check_interval: Seconds between health checks (default: 300 = 5 minutes)
        """
        self.db_path = db_path
        self.check_interval = check_interval
        self.process = psutil.Process()
        self._monitoring = False
        self._monitor_thread: threading.Thread | None = None
        self.last_check_time = None
        self.metrics_history = []
        self.max_history = 288  # 24 hours of 5-minute intervals

    def get_current_metrics(self) -> Dict:
        """
        Get current health metrics.

        Returns:
            Dictionary with current metrics
        """
        try:
            # Memory usage
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)

            # Thread count
            thread_count = threading.active_count()

            # Database size
            db_size_mb = 0
            if os.path.exists(self.db_path):
                db_size_mb = os.path.getsize(self.db_path) / (1024 * 1024)

            # CPU usage (averaged over 1 second)
            cpu_percent = self.process.cpu_percent(interval=1.0)

            metrics = {
                "timestamp": time.time(),
                "memory_mb": round(memory_mb, 2),
                "thread_count": thread_count,
                "db_size_mb": round(db_size_mb, 2),
                "cpu_percent": round(cpu_percent, 2),
            }

            return metrics

        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            return {}

    def check_health(self) -> Dict:
        """
        Perform health check and return status.

        Returns:
            Dictionary with health status and metrics
        """
        metrics = self.get_current_metrics()

        # Define thresholds
        warnings = []
        critical = []

        # Memory warnings (adjusted for 1.5B model ~1.5GB + embeddings ~0.1GB + overhead)
        if metrics.get("memory_mb", 0) > 3000:  # > 3GB (indicating leak or issue)
            critical.append(f"High memory usage: {metrics['memory_mb']:.1f}MB")
        elif metrics.get("memory_mb", 0) > 2200:  # > 2.2GB (higher than expected)
            warnings.append(f"Elevated memory usage: {metrics['memory_mb']:.1f}MB")

        # Thread warnings
        if metrics.get("thread_count", 0) > 50:
            critical.append(f"High thread count: {metrics['thread_count']}")
        elif metrics.get("thread_count", 0) > 20:
            warnings.append(f"Elevated thread count: {metrics['thread_count']}")

        # Database size warnings
        if metrics.get("db_size_mb", 0) > 500:  # > 500MB
            warnings.append(f"Large database size: {metrics['db_size_mb']:.1f}MB")

        # CPU warnings
        if metrics.get("cpu_percent", 0) > 80:
            warnings.append(f"High CPU usage: {metrics['cpu_percent']:.1f}%")

        # Determine overall status
        if critical:
            status = "CRITICAL"
        elif warnings:
            status = "WARNING"
        else:
            status = "HEALTHY"

        health_check = {
            "status": status,
            "metrics": metrics,
            "warnings": warnings,
            "critical": critical,
        }

        # Log issues
        if critical:
            logger.error(f"Health check CRITICAL: {', '.join(critical)}")
        elif warnings:
            logger.warning(f"Health check WARNING: {', '.join(warnings)}")
        else:
            logger.info(
                f"Health check HEALTHY - Memory: {metrics.get('memory_mb', 0):.1f}MB, "
                f"Threads: {metrics.get('thread_count', 0)}, "
                f"DB: {metrics.get('db_size_mb', 0):.1f}MB"
            )

        return health_check

    def _monitor_loop(self):
        """Background monitoring loop."""
        logger.info(
            f"Health monitoring started (check interval: {self.check_interval}s)"
        )

        while self._monitoring:
            try:
                health = self.check_health()
                self.last_check_time = time.time()

                # Store metrics history
                self.metrics_history.append(health["metrics"])
                if len(self.metrics_history) > self.max_history:
                    self.metrics_history.pop(0)

            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")

            # Sleep for interval
            time.sleep(self.check_interval)

        logger.info("Health monitoring stopped")

    def start_monitoring(self):
        """Start background health monitoring."""
        if self._monitoring:
            logger.warning("Health monitoring already running")
            return

        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="health-monitor"
        )
        self._monitor_thread.start()
        logger.info("Health monitoring thread started")

    def stop_monitoring(self):
        """Stop background health monitoring."""
        if not self._monitoring:
            return

        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("Health monitoring stopped")

    def get_metrics_summary(self) -> Dict:
        """
        Get summary statistics from metrics history.

        Returns:
            Dictionary with min/max/avg metrics
        """
        if not self.metrics_history:
            return {}

        memory_values = [m["memory_mb"] for m in self.metrics_history]
        thread_values = [m["thread_count"] for m in self.metrics_history]
        cpu_values = [m["cpu_percent"] for m in self.metrics_history]

        return {
            "memory_mb": {
                "min": round(min(memory_values), 2),
                "max": round(max(memory_values), 2),
                "avg": round(sum(memory_values) / len(memory_values), 2),
            },
            "thread_count": {
                "min": min(thread_values),
                "max": max(thread_values),
                "avg": round(sum(thread_values) / len(thread_values), 1),
            },
            "cpu_percent": {
                "min": round(min(cpu_values), 2),
                "max": round(max(cpu_values), 2),
                "avg": round(sum(cpu_values) / len(cpu_values), 2),
            },
            "samples": len(self.metrics_history),
        }
