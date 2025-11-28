"""
Worker Manager Service

Automatically manages campaign message workers:
- Starts workers when campaigns are queued
- Monitors queue and stops workers when empty
- Prevents duplicate worker processes
"""

import os
import sys
import time
import logging
import threading
import subprocess
from typing import Optional
import pika

logger = logging.getLogger(__name__)

# Configuration
QUEUE_NAME = "campaign_queue"
DEFAULT_NUM_WORKERS = 4
IDLE_SHUTDOWN_SECONDS = 30  # Stop workers after queue empty for this duration
CHECK_INTERVAL_SECONDS = 5  # How often to check queue status


class WorkerManager:
    """Singleton manager for campaign worker processes"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._workers = []  # List of subprocess.Popen objects
        self._monitor_thread: Optional[threading.Thread] = None
        self._should_stop = False
        self._is_running = False

    def get_queue_size(self) -> int:
        """Get current number of messages in queue"""
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host="localhost")
            )
            channel = connection.channel()
            queue = channel.queue_declare(queue=QUEUE_NAME, durable=True, passive=True)
            message_count = queue.method.message_count
            connection.close()
            return message_count
        except Exception as e:
            logger.error(f"Failed to get queue size: {e}")
            return -1

    def is_running(self) -> bool:
        """Check if workers are currently running"""
        # Clean up dead workers
        self._workers = [w for w in self._workers if w.poll() is None]
        return len(self._workers) > 0

    def start_workers(self, num_workers: int = DEFAULT_NUM_WORKERS) -> bool:
        """
        Start worker processes if not already running.
        Returns True if workers were started, False if already running.
        """
        with self._lock:
            if self.is_running():
                logger.info(f"Workers already running ({len(self._workers)} active)")
                return False

            logger.info(f"🚀 Starting {num_workers} campaign workers...")

            # Get the path to consumer.py
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            consumer_path = os.path.join(project_root, "consumer.py")

            # Start worker processes
            for i in range(num_workers):
                try:
                    # Start each worker as a separate process
                    process = subprocess.Popen(
                        [sys.executable, consumer_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=project_root
                    )
                    self._workers.append(process)
                    logger.info(f"Started worker {i + 1} (PID: {process.pid})")
                    time.sleep(0.2)  # Stagger starts
                except Exception as e:
                    logger.error(f"Failed to start worker {i + 1}: {e}")

            # Start monitor thread
            self._start_monitor()

            logger.info(f"✅ {len(self._workers)} workers started successfully")
            return True

    def stop_workers(self, force: bool = False):
        """Stop all worker processes"""
        with self._lock:
            self._should_stop = True

            if not self._workers:
                logger.info("No workers to stop")
                return

            logger.info(f"🛑 Stopping {len(self._workers)} workers...")

            for worker in self._workers:
                try:
                    if force:
                        worker.kill()
                    else:
                        worker.terminate()
                except Exception as e:
                    logger.error(f"Error stopping worker PID {worker.pid}: {e}")

            # Wait for workers to stop
            for worker in self._workers:
                try:
                    worker.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()

            self._workers = []
            logger.info("✅ All workers stopped")

    def _start_monitor(self):
        """Start the queue monitor thread"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._should_stop = False
        self._monitor_thread = threading.Thread(target=self._monitor_queue, daemon=True)
        self._monitor_thread.start()
        logger.info("Queue monitor started")

    def _monitor_queue(self):
        """Monitor queue and stop workers when empty"""
        idle_start = None

        while not self._should_stop:
            time.sleep(CHECK_INTERVAL_SECONDS)

            # Check if workers are still alive
            if not self.is_running():
                logger.info("All workers have stopped")
                break

            # Check queue size
            queue_size = self.get_queue_size()

            if queue_size == 0:
                if idle_start is None:
                    idle_start = time.time()
                    logger.info("Queue empty, starting idle countdown...")

                idle_duration = time.time() - idle_start
                if idle_duration >= IDLE_SHUTDOWN_SECONDS:
                    logger.info(f"Queue empty for {IDLE_SHUTDOWN_SECONDS}s, stopping workers...")
                    self.stop_workers()
                    break
            else:
                if idle_start is not None:
                    logger.info(f"Queue has {queue_size} messages, resetting idle countdown")
                idle_start = None

        logger.info("Queue monitor stopped")

    def get_status(self) -> dict:
        """Get current worker status"""
        return {
            "is_running": self.is_running(),
            "worker_count": len(self._workers),
            "worker_pids": [w.pid for w in self._workers if w.poll() is None],
            "queue_size": self.get_queue_size()
        }


# Global instance
worker_manager = WorkerManager()


def ensure_workers_running(num_workers: int = DEFAULT_NUM_WORKERS) -> bool:
    """
    Ensure workers are running. Call this when queuing campaign messages.
    Returns True if workers were started, False if already running.
    """
    return worker_manager.start_workers(num_workers)


def stop_all_workers(force: bool = False):
    """Stop all workers immediately"""
    worker_manager.stop_workers(force)


def get_worker_status() -> dict:
    """Get current worker status"""
    return worker_manager.get_status()
