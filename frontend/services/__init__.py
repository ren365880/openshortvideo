# services/__init__.py
from .log_service import (
    log_manager,
    log_ai_call,
    log_user_action,
    log_system_event,
    log_error,
    log_operation,
    log_ai_operation,
    schedule_log_cleanup,
    LogManager
)

__all__ = [
    'log_manager',
    'log_ai_call',
    'log_user_action',
    'log_system_event',
    'log_error',
    'log_operation',
    'log_ai_operation',
    'schedule_log_cleanup',
    'LogManager'
]
