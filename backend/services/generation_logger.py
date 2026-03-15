"""
Simple logging utility for task generation.
"""
import logging
from datetime import datetime
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

logger = logging.getLogger(__name__)


class GenerationLogger:
    """Simple logger for tracking task generation progress."""
    
    def __init__(self):
        self.tasks = {}
    
    def step_started(self, task_id: str, step: str):
        logger.info(f"[{task_id}] Step started: {step}")
    
    def step_completed(self, task_id: str, step: str, **kwargs):
        logger.info(f"[{task_id}] Step completed: {step}")
        for key, value in kwargs.items():
            logger.info(f"[{task_id}]   {key}: {value}")
    
    def step_failed(self, task_id: str, step: str, error: str):
        logger.error(f"[{task_id}] Step failed: {step} - {error}")
    
    def task_completed(self, task_id: str, **kwargs):
        self.info(task_id, 'task', 'Task completed', **kwargs)
    
    def task_failed(self, task_id: str, error: str, **kwargs):
        self.error(task_id, 'task', f'Task failed: {error}')
        for key, value in kwargs.items():
            logger.error(f"[{task_id}]   {key}: {value}")
    
    def info(self, task_id: str, step: str, message: str, **kwargs):
        logger.info(f"[{task_id}] [{step}] {message}")
        for key, value in kwargs.items():
            logger.info(f"[{task_id}]   {key}: {value}")
    
    def debug(self, task_id: str, step: str, message: str, **kwargs):
        logger.debug(f"[{task_id}] [{step}] {message}")
    
    def warning(self, task_id: str, step: str, message: str):
        logger.warning(f"[{task_id}] [{step}] {message}")
    
    def error(self, task_id: str, step: str, message: str):
        logger.error(f"[{task_id}] [{step}] {message}")
    
    def log_file_saved(self, task_id: str, step: str, file_path: str):
        logger.info(f"[{task_id}] [{step}] File saved: {file_path}")
    
    def log_file_loaded(self, task_id: str, step: str, file_path: str, **kwargs):
        logger.info(f"[{task_id}] [{step}] File loaded: {file_path}")
        for key, value in kwargs.items():
            logger.info(f"[{task_id}]   {key}: {value}")
    
    def log_artifact_updated(self, task_id: str, step: str, artifact_name: str, **kwargs):
        logger.info(f"[{task_id}] [{step}] Artifact updated: {artifact_name}")
        for key, value in kwargs.items():
            logger.info(f"[{task_id}]   {key}: {value}")


gen_logger = GenerationLogger()
