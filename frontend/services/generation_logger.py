"""
Generation Step Logger - 统一的生成步骤日志记录模块
提供文件日志和数据库日志功能，用于追踪视频生成的各个关键步骤
"""
import os
import json
import logging
import logging.handlers
from datetime import datetime
from typing import Optional, Dict, Any
from functools import wraps

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs', 'generation')
MAX_LOG_SIZE = 20 * 1024 * 1024  # 20MB
MAX_LOG_FILES = 5


class GenerationLogger:
    """生成步骤日志记录器"""
    _instance = None
    _logger = None
    
    # 步骤定义
    STEPS = {
        'develop_story': '故事开发',
        'extract_characters': '角色提取',
        'generate_character_portraits': '角色肖像生成',
        'write_script': '脚本撰写',
        'design_storyboard': '故事板设计',
        'generate_scenes': '场景生成',
        'generate_shots': '镜头生成',
        'compose_video': '视频合成',
        'full_pipeline': '完整流水线'
    }
    
    # 状态定义
    STATUS = {
        'started': '开始',
        'completed': '完成',
        'failed': '失败',
        'skipped': '跳过'
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GenerationLogger, cls).__new__(cls)
            cls._instance._init_logger()
        return cls._instance
    
    def _init_logger(self):
        """初始化日志记录器"""
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        
        self._logger = logging.getLogger('generation_logger')
        self._logger.setLevel(logging.DEBUG)
        self._logger.handlers = []
        
        # 所有生成日志
        all_log_file = os.path.join(LOG_DIR, 'all_steps.log')
        all_handler = logging.handlers.RotatingFileHandler(
            all_log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=MAX_LOG_FILES,
            encoding='utf-8'
        )
        all_handler.setLevel(logging.DEBUG)
        
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        all_handler.setFormatter(formatter)
        self._logger.addHandler(all_handler)
        
        # 错误日志
        error_log_file = os.path.join(LOG_DIR, 'errors.log')
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=MAX_LOG_FILES,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        self._logger.addHandler(error_handler)
    
    def log(self, level: str, task_id: str, step: str, message: str, **kwargs):
        """记录日志"""
        # 构建完整消息
        step_name = self.STEPS.get(step, step)
        status = kwargs.get('status', '')
        status_text = self.STATUS.get(status, status) if status else ''
        
        full_message = f"[Task: {task_id}] [Step: {step_name}]"
        if status_text:
            full_message += f" [{status_text}]"
        full_message += f" {message}"
        
        # 添加额外数据
        if kwargs:
            extra_data = {k: v for k, v in kwargs.items() if k not in ['status']}
            if extra_data:
                full_message += f" | Extra: {json.dumps(extra_data, ensure_ascii=False)}"
        
        # 记录到日志
        if level == 'DEBUG':
            self._logger.debug(full_message)
        elif level == 'INFO':
            self._logger.info(full_message)
        elif level == 'WARNING':
            self._logger.warning(full_message)
        elif level == 'ERROR':
            self._logger.error(full_message)
        elif level == 'CRITICAL':
            self._logger.critical(full_message)
        
        return full_message
    
    def info(self, task_id: str, step: str, message: str, **kwargs):
        return self.log('INFO', task_id, step, message, **kwargs)
    
    def error(self, task_id: str, step: str, message: str, **kwargs):
        return self.log('ERROR', task_id, step, message, **kwargs)
    
    def warning(self, task_id: str, step: str, message: str, **kwargs):
        return self.log('WARNING', task_id, step, message, **kwargs)
    
    def debug(self, task_id: str, step: str, message: str, **kwargs):
        return self.log('DEBUG', task_id, step, message, **kwargs)
    
    # ========== 便捷方法 ==========
    
    def step_started(self, task_id: str, step: str, **kwargs):
        """记录步骤开始"""
        return self.info(task_id, step, f"步骤开始", status='started', **kwargs)
    
    def step_completed(self, task_id: str, step: str, **kwargs):
        """记录步骤完成"""
        return self.info(task_id, step, f"步骤完成", status='completed', **kwargs)
    
    def step_failed(self, task_id: str, step: str, error: str, **kwargs):
        """记录步骤失败"""
        return self.error(task_id, step, f"步骤失败: {error}", status='failed', **kwargs)
    
    def step_skipped(self, task_id: str, step: str, reason: str = '', **kwargs):
        """记录步骤跳过"""
        msg = f"步骤跳过"
        if reason:
            msg += f": {reason}"
        return self.warning(task_id, step, msg, status='skipped', **kwargs)
    
    # ========== 任务级别日志 ==========
    
    def task_started(self, task_id: str, idea: str, **kwargs):
        """记录任务开始"""
        idea_preview = idea[:50] + '...' if len(idea) > 50 else idea
        return self.info(task_id, 'full_pipeline', f"任务开始: {idea_preview}", **kwargs)
    
    def task_completed(self, task_id: str, **kwargs):
        """记录任务完成"""
        return self.info(task_id, 'full_pipeline', f"任务完成", **kwargs)
    
    def task_failed(self, task_id: str, error: str, **kwargs):
        """记录任务失败"""
        return self.error(task_id, 'full_pipeline', f"任务失败: {error}", **kwargs)
    
    # ========== 关键操作日志 ==========
    
    def log_pipeline_init(self, task_id: str, config: str, **kwargs):
        """记录流水线初始化"""
        return self.info(task_id, 'full_pipeline', f"初始化流水线: {config}", **kwargs)
    
    def log_ai_call(self, task_id: str, step: str, model: str, duration_ms: int, **kwargs):
        """记录AI调用"""
        return self.info(task_id, step, f"AI调用完成: {model}, 耗时: {duration_ms}ms", 
                        model=model, duration_ms=duration_ms, **kwargs)
    
    def log_file_saved(self, task_id: str, step: str, file_path: str, **kwargs):
        """记录文件保存"""
        file_name = os.path.basename(file_path)
        return self.debug(task_id, step, f"文件已保存: {file_name}", file_path=file_path, **kwargs)
    
    def log_file_loaded(self, task_id: str, step: str, file_path: str, **kwargs):
        """记录文件加载"""
        file_name = os.path.basename(file_path)
        return self.debug(task_id, step, f"文件已加载: {file_name}", file_path=file_path, **kwargs)
    
    def log_artifact_updated(self, task_id: str, step: str, artifact_key: str, **kwargs):
        """记录产物更新"""
        return self.debug(task_id, step, f"产物已更新: {artifact_key}", artifact_key=artifact_key, **kwargs)
    
    def log_validation(self, task_id: str, step: str, check_name: str, result: bool, **kwargs):
        """记录验证结果"""
        result_text = '通过' if result else '失败'
        level = 'DEBUG' if result else 'WARNING'
        return self.log(level, task_id, step, f"验证 {check_name}: {result_text}", 
                       check=check_name, passed=result, **kwargs)


# 全局实例
gen_logger = GenerationLogger()


# ========== 装饰器 ==========

def log_step(step_name: str):
    """装饰器：自动记录步骤开始和结束"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            task_id = kwargs.get('task_id') or (args[0] if args else 'unknown')
            
            gen_logger.step_started(task_id, step_name)
            
            try:
                result = func(*args, **kwargs)
                gen_logger.step_completed(task_id, step_name)
                return result
            except Exception as e:
                gen_logger.step_failed(task_id, step_name, str(e))
                raise
        
        return wrapper
    return decorator


def log_ai_step(step_name: str, model_name: str = None):
    """装饰器：记录AI调用步骤"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            task_id = kwargs.get('task_id') or (args[0] if args else 'unknown')
            
            import time
            start_time = time.time()
            gen_logger.step_started(task_id, step_name)
            
            try:
                result = func(*args, **kwargs)
                duration_ms = int((time.time() - start_time) * 1000)
                gen_logger.step_completed(task_id, step_name)
                if model_name:
                    gen_logger.log_ai_call(task_id, step_name, model_name, duration_ms)
                return result
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                gen_logger.step_failed(task_id, step_name, str(e))
                if model_name:
                    gen_logger.log_ai_call(task_id, step_name, model_name, duration_ms, error=str(e))
                raise
        
        return wrapper
    return decorator
