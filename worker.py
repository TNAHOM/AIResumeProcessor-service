#!/usr/bin/env python3
"""
Celery worker startup script.

Usage:
    python worker.py

This script starts a Celery worker that will process resume jobs from the Redis queue.
"""

from app.core.celery_app import celery_app

if __name__ == "__main__":
    celery_app.start()