"""
日志管理服务模块
提供文件日志轮转和数据库日志记录功能
"""
import os
import json
import gzip
import shutil
import logging
import logging.handlers
from datetime import datetime, timedelta
from functools import wraps
from flask import request, g, current_app
from models import LogEntry, db

# 日志配置
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
MAX_LOG_SIZE = 50 * 1024 * 1024  # 50MB
MAX_LOG_DAYS = 30  # 30天保留期
LOG_BACKUP_COUNT = 10  # 保留的备份文件数量

# 确保日志目录存在
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)


class LogManager:
    """日志管理器"""
    _instance = None
    _logger = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LogManager, cls).__new__(cls)
            cls._instance._init_logger()
        return cls._instance
    
    def _init_logger(self):
        """初始化日志记录器"""
        self._logger = logging.getLogger('app_logger')
        self._logger.setLevel(logging.DEBUG)
        
        # 清除现有的处理器
        self._logger.handlers = []
        
        # 主日志文件处理器 - 按大小轮转
        main_log_file = os.path.join(LOG_DIR, 'app.log')
        file_handler = logging.handlers.RotatingFileHandler(
            main_log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        
        # 格式化器
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)
        
        # AI调用专用日志
        ai_log_file = os.path.join(LOG_DIR, 'ai_calls.log')
        ai_handler = logging.handlers.RotatingFileHandler(
            ai_log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        ai_handler.setLevel(logging.INFO)
        ai_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [AI] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        ai_handler.setFormatter(ai_formatter)
        self._logger.addHandler(ai_handler)
        
        # 错误日志
        error_log_file = os.path.join(LOG_DIR, 'error.log')
        error_handler = logging.handlers.RotatingFileHandler(
            error_log_file,
            maxBytes=MAX_LOG_SIZE,
            backupCount=LOG_BACKUP_COUNT,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s\n%(exc_info)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(error_formatter)
        self._logger.addHandler(error_handler)
    
    @property
    def logger(self):
        return self._logger
    
    def log_to_file(self, level, message, category='GENERAL'):
        """记录到文件日志"""
        full_message = f"[{category}] {message}"
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
    
    def log_to_db(self, level, category, action, **kwargs):
        """记录到数据库"""
        try:
            log_entry = LogEntry(
                level=level,
                category=category,
                action=action,
                user_id=kwargs.get('user_id'),
                project_id=kwargs.get('project_id'),
                episode_id=kwargs.get('episode_id'),
                ip_address=kwargs.get('ip_address') or self._get_client_ip(),
                user_agent=kwargs.get('user_agent') or self._get_user_agent(),
                request_data=json.dumps(kwargs.get('request_data')) if kwargs.get('request_data') else None,
                response_data=json.dumps(kwargs.get('response_data')) if kwargs.get('response_data') else None,
                error_message=kwargs.get('error_message'),
                duration_ms=kwargs.get('duration_ms'),
                status=kwargs.get('status', 'success'),
                extra_data=json.dumps(kwargs.get('extra_data')) if kwargs.get('extra_data') else None
            )
            db.session.add(log_entry)
            db.session.commit()
            return log_entry.id
        except Exception as e:
            # 如果数据库记录失败，记录到文件
            self.log_to_file('ERROR', f"Failed to save log to database: {str(e)}", 'SYSTEM')
            db.session.rollback()
            return None
    
    def _get_client_ip(self):
        """获取客户端IP"""
        try:
            if request:
                if request.headers.get('X-Forwarded-For'):
                    return request.headers.get('X-Forwarded-For').split(',')[0].strip()
                elif request.headers.get('X-Real-IP'):
                    return request.headers.get('X-Real-IP')
                else:
                    return request.remote_addr
        except:
            pass
        return None
    
    def _get_user_agent(self):
        """获取用户代理"""
        try:
            if request:
                return request.user_agent.string
        except:
            pass
        return None
    
    def cleanup_old_logs(self, days=MAX_LOG_DAYS):
        """清理旧日志文件"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cleaned_count = 0
        
        # 清理轮转的旧日志文件
        for filename in os.listdir(LOG_DIR):
            if filename.endswith('.log') or filename.endswith('.gz'):
                file_path = os.path.join(LOG_DIR, filename)
                try:
                    file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_modified < cutoff_date:
                        os.remove(file_path)
                        cleaned_count += 1
                        self.log_to_file('INFO', f"Cleaned old log file: {filename}", 'SYSTEM')
                except Exception as e:
                    self.log_to_file('ERROR', f"Failed to clean log file {filename}: {str(e)}", 'SYSTEM')
        
        # 清理数据库中的旧日志
        try:
            db_count = LogEntry.cleanup_old_logs(days)
            cleaned_count += db_count
            self.log_to_file('INFO', f"Cleaned {db_count} old database logs", 'SYSTEM')
        except Exception as e:
            self.log_to_file('ERROR', f"Failed to clean database logs: {str(e)}", 'SYSTEM')
        
        return cleaned_count
    
    def compress_old_logs(self, days=7):
        """压缩7天前的日志文件"""
        cutoff_date = datetime.now() - timedelta(days=days)
        compressed_count = 0
        
        for filename in os.listdir(LOG_DIR):
            if filename.endswith('.log') and not filename.endswith('.gz'):
                file_path = os.path.join(LOG_DIR, filename)
                try:
                    file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if file_modified < cutoff_date:
                        compressed_path = file_path + '.gz'
                        with open(file_path, 'rb') as f_in:
                            with gzip.open(compressed_path, 'wb') as f_out:
                                shutil.copyfileobj(f_in, f_out)
                        os.remove(file_path)
                        compressed_count += 1
                        self.log_to_file('INFO', f"Compressed log file: {filename}", 'SYSTEM')
                except Exception as e:
                    self.log_to_file('ERROR', f"Failed to compress log file {filename}: {str(e)}", 'SYSTEM')
        
        return compressed_count
    
    def get_log_stats(self):
        """获取日志统计信息"""
        stats = {
            'log_dir': LOG_DIR,
            'total_files': 0,
            'total_size': 0,
            'oldest_file': None,
            'newest_file': None,
            'db_logs_count': 0
        }
        
        try:
            files = []
            for filename in os.listdir(LOG_DIR):
                file_path = os.path.join(LOG_DIR, filename)
                if os.path.isfile(file_path):
                    file_stat = os.stat(file_path)
                    files.append({
                        'name': filename,
                        'size': file_stat.st_size,
                        'modified': datetime.fromtimestamp(file_stat.st_mtime)
                    })
            
            if files:
                stats['total_files'] = len(files)
                stats['total_size'] = sum(f['size'] for f in files)
                stats['oldest_file'] = min(files, key=lambda x: x['modified'])['modified'].isoformat()
                stats['newest_file'] = max(files, key=lambda x: x['modified'])['modified'].isoformat()
            
            # 数据库日志数量
            stats['db_logs_count'] = LogEntry.query.count()
            
        except Exception as e:
            self.log_to_file('ERROR', f"Failed to get log stats: {str(e)}", 'SYSTEM')
        
        return stats


# 全局日志管理器实例
log_manager = LogManager()


# 便捷的日志记录函数
def log_ai_call(action, model, prompt, response, duration_ms, status='success', error=None, **kwargs):
    """记录AI调用日志"""
    message = f"AI Call: {action} | Model: {model} | Status: {status} | Duration: {duration_ms}ms"
    if error:
        message += f" | Error: {error}"
    
    level = 'ERROR' if error else 'INFO'
    log_manager.log_to_file(level, message, 'AI')
    
    # 同时记录到数据库
    user_id = kwargs.get('user_id') or (g.user.id if hasattr(g, 'user') and g.user else None)
    log_manager.log_to_db(
        level=level,
        category='AI调用',
        action=action,
        user_id=user_id,
        project_id=kwargs.get('project_id'),
        episode_id=kwargs.get('episode_id'),
        request_data={'model': model, 'prompt': prompt[:1000] if prompt else None},
        response_data={'response': response[:1000] if response else None},
        error_message=error,
        duration_ms=duration_ms,
        status=status,
        extra_data={'model': model, 'full_prompt_length': len(prompt) if prompt else 0}
    )


def log_user_action(action, description, level='INFO', **kwargs):
    """记录用户操作日志"""
    message = f"User Action: {action} | {description}"
    log_manager.log_to_file(level, message, 'USER')
    
    user_id = kwargs.get('user_id') or (g.user.id if hasattr(g, 'user') and g.user else None)
    log_manager.log_to_db(
        level=level,
        category='用户操作',
        action=action,
        user_id=user_id,
        project_id=kwargs.get('project_id'),
        episode_id=kwargs.get('episode_id'),
        request_data=kwargs.get('request_data'),
        status=kwargs.get('status', 'success'),
        extra_data={'description': description}
    )


def log_system_event(action, description, level='INFO', **kwargs):
    """记录系统事件日志"""
    message = f"System: {action} | {description}"
    log_manager.log_to_file(level, message, 'SYSTEM')
    
    log_manager.log_to_db(
        level=level,
        category='系统事件',
        action=action,
        error_message=kwargs.get('error'),
        extra_data={'description': description}
    )


def log_error(action, error, **kwargs):
    """记录错误日志"""
    message = f"Error in {action}: {str(error)}"
    log_manager.log_to_file('ERROR', message, 'ERROR')
    
    user_id = kwargs.get('user_id') or (g.user.id if hasattr(g, 'user') and g.user else None)
    log_manager.log_to_db(
        level='ERROR',
        category='系统错误',
        action=action,
        user_id=user_id,
        project_id=kwargs.get('project_id'),
        error_message=str(error),
        status='failed',
        extra_data=kwargs.get('extra_data')
    )


# 装饰器用于自动记录函数调用
def log_operation(category, action_name=None, log_args=False):
    """装饰器：自动记录函数调用"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = datetime.now()
            action = action_name or func.__name__
            
            try:
                result = func(*args, **kwargs)
                duration = int((datetime.now() - start_time).total_seconds() * 1000)
                
                request_data = None
                if log_args:
                    request_data = {
                        'args': str(args),
                        'kwargs': {k: str(v) for k, v in kwargs.items()}
                    }
                
                log_manager.log_to_db(
                    level='INFO',
                    category=category,
                    action=action,
                    duration_ms=duration,
                    status='success',
                    request_data=request_data
                )
                
                return result
            except Exception as e:
                duration = int((datetime.now() - start_time).total_seconds() * 1000)
                log_manager.log_to_db(
                    level='ERROR',
                    category=category,
                    action=action,
                    duration_ms=duration,
                    status='failed',
                    error_message=str(e)
                )
                raise
        
        return wrapper
    return decorator


def log_ai_operation(model_name):
    """装饰器：专门用于记录AI模型调用"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = datetime.now()
            action = func.__name__
            
            # 提取prompt参数
            prompt = kwargs.get('prompt') or (args[0] if args else None)
            
            try:
                result = func(*args, **kwargs)
                duration = int((datetime.now() - start_time).total_seconds() * 1000)
                
                log_ai_call(
                    action=action,
                    model=model_name,
                    prompt=prompt,
                    response=str(result) if result else None,
                    duration_ms=duration,
                    status='success'
                )
                
                return result
            except Exception as e:
                duration = int((datetime.now() - start_time).total_seconds() * 1000)
                log_ai_call(
                    action=action,
                    model=model_name,
                    prompt=prompt,
                    response=None,
                    duration_ms=duration,
                    status='failed',
                    error=str(e)
                )
                raise
        
        return wrapper
    return decorator


# 定时清理任务（需要在应用启动时设置）
def schedule_log_cleanup(app):
    """设置日志清理定时任务"""
    from flask_apscheduler import APScheduler
    
    scheduler = APScheduler()
    scheduler.init_app(app)
    
    @scheduler.task('cron', id='cleanup_logs', hour=2, minute=0)
    def cleanup_task():
        """每天凌晨2点执行日志清理"""
        with app.app_context():
            log_manager.log_to_file('INFO', 'Starting scheduled log cleanup', 'SYSTEM')
            
            # 压缩7天前的日志
            compressed = log_manager.compress_old_logs(days=7)
            log_manager.log_to_file('INFO', f'Compressed {compressed} log files', 'SYSTEM')
            
            # 清理30天前的日志
            cleaned = log_manager.cleanup_old_logs(days=30)
            log_manager.log_to_file('INFO', f'Cleaned {cleaned} old logs', 'SYSTEM')
    
    scheduler.start()
    return scheduler
