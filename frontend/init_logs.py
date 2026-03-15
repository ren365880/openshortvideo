"""
日志系统初始化脚本
运行此脚本创建日志表并测试日志功能
"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from __init__ import create_app, db
from models import LogEntry
from services.log_service import log_manager, log_user_action, log_ai_call, log_error

def init_logs():
    """初始化日志系统"""
    app = create_app()
    
    with app.app_context():
        # 创建日志表
        print("正在创建日志表...")
        db.create_all()
        print("✅ 日志表创建成功")
        
        # 测试日志记录
        print("\n正在测试日志记录...")
        
        # 测试用户操作日志
        log_user_action(
            '系统初始化',
            '日志系统初始化完成',
            level='INFO'
        )
        print("✅ 用户操作日志测试成功")
        
        # 测试AI调用日志
        log_ai_call(
            action='测试AI调用',
            model='test-model',
            prompt='测试提示词',
            response='测试响应',
            duration_ms=100,
            status='success'
        )
        print("✅ AI调用日志测试成功")
        
        # 测试错误日志
        try:
            raise ValueError("测试错误")
        except Exception as e:
            log_error('测试错误', e)
        print("✅ 错误日志测试成功")
        
        # 获取日志统计
        print("\n日志统计:")
        stats = log_manager.get_log_stats()
        print(f"  日志目录: {stats['log_dir']}")
        print(f"  日志文件数: {stats['total_files']}")
        print(f"  日志总大小: {stats['total_size']} bytes")
        print(f"  数据库日志数: {stats['db_logs_count']}")
        
        # 查看数据库日志
        logs = LogEntry.query.all()
        print(f"\n数据库中的日志记录:")
        for log in logs:
            print(f"  [{log.level}] {log.category} - {log.action}")
        
        print("\n✅ 日志系统初始化完成！")
        print("\n访问日志管理页面: http://localhost:5000/logs")

if __name__ == '__main__':
    init_logs()
