#!/usr/bin/env python3
"""
Celery worker script for processing resume jobs
"""

import os
import sys

# Add the app directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.core.celery_app import celery_app

if __name__ == '__main__':
    celery_app.start()