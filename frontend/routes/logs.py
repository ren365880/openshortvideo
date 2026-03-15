"""
日志管理路由
提供日志查看、管理和导出功能
"""
from flask import Blueprint, jsonify, request, render_template
from flask_login import login_required, current_user
from models import LogEntry, db
from services.log_service import log_manager, log_user_action
from datetime import datetime, timedelta
import json

logs_bp = Blueprint('logs', __name__, url_prefix='/logs')


@logs_bp.route('/')
@login_required
def index():
    """日志管理页面"""
    # 只允许管理员访问（假设管理员user_id为1，或添加is_admin字段）
    # 这里简化处理，实际应该检查用户权限
    return render_template('logs.html')


@logs_bp.route('/api/list')
@login_required
def list_logs():
    """获取日志列表API"""
    try:
        # 查询参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        level = request.args.get('level')
        category = request.args.get('category')
        action = request.args.get('action')
        user_id = request.args.get('user_id', type=int)
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # 构建查询
        query = LogEntry.query
        
        if level:
            query = query.filter(LogEntry.level == level)
        if category:
            query = query.filter(LogEntry.category == category)
        if action:
            query = query.filter(LogEntry.action.like(f'%{action}%'))
        if user_id:
            query = query.filter(LogEntry.user_id == user_id)
        if start_date:
            query = query.filter(LogEntry.created_at >= datetime.fromisoformat(start_date))
        if end_date:
            query = query.filter(LogEntry.created_at <= datetime.fromisoformat(end_date))
        
        # 按时间倒序
        query = query.order_by(LogEntry.created_at.desc())
        
        # 分页
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        logs = [log.to_dict() for log in pagination.items]
        
        # 记录查看日志操作
        log_user_action('查看日志列表', f'查询条件: level={level}, category={category}')
        
        return jsonify({
            'success': True,
            'logs': logs,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@logs_bp.route('/api/stats')
@login_required
def get_stats():
    """获取日志统计信息"""
    try:
        # 文件日志统计
        file_stats = log_manager.get_log_stats()
        
        # 数据库日志统计
        total_logs = LogEntry.query.count()
        today_logs = LogEntry.query.filter(
            LogEntry.created_at >= datetime.utcnow().date()
        ).count()
        
        # 按级别统计
        level_stats = db.session.query(
            LogEntry.level,
            db.func.count(LogEntry.id)
        ).group_by(LogEntry.level).all()
        
        # 按分类统计
        category_stats = db.session.query(
            LogEntry.category,
            db.func.count(LogEntry.id)
        ).group_by(LogEntry.category).all()
        
        return jsonify({
            'success': True,
            'file_stats': file_stats,
            'db_stats': {
                'total': total_logs,
                'today': today_logs,
                'by_level': {level: count for level, count in level_stats},
                'by_category': {category: count for category, count in category_stats}
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@logs_bp.route('/api/<int:log_id>')
@login_required
def get_log_detail(log_id):
    """获取单条日志详情"""
    try:
        log = LogEntry.query.get_or_404(log_id)
        return jsonify({
            'success': True,
            'log': log.to_dict()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@logs_bp.route('/api/cleanup', methods=['POST'])
@login_required
def cleanup_logs():
    """手动清理旧日志"""
    try:
        days = request.json.get('days', 30)
        cleaned_count = log_manager.cleanup_old_logs(days)
        
        # 记录清理操作
        log_user_action('清理日志', f'清理了{cleaned_count}条{cleans}天前的日志')
        
        return jsonify({
            'success': True,
            'message': f'成功清理{cleaned_count}条日志',
            'cleaned_count': cleaned_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@logs_bp.route('/api/compress', methods=['POST'])
@login_required
def compress_logs():
    """手动压缩旧日志"""
    try:
        days = request.json.get('days', 7)
        compressed_count = log_manager.compress_old_logs(days)
        
        log_user_action('压缩日志', f'压缩了{compressed_count}个{cleaned_count}天前的日志文件')
        
        return jsonify({
            'success': True,
            'message': f'成功压缩{compressed_count}个日志文件',
            'compressed_count': compressed_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@logs_bp.route('/api/export')
@login_required
def export_logs():
    """导出日志"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        query = LogEntry.query
        
        if start_date:
            query = query.filter(LogEntry.created_at >= datetime.fromisoformat(start_date))
        if end_date:
            query = query.filter(LogEntry.created_at <= datetime.fromisoformat(end_date))
        
        logs = query.order_by(LogEntry.created_at.desc()).all()
        
        # 转换为CSV格式
        import csv
        import io
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow([
            'ID', '时间', '级别', '分类', '操作', '用户ID', '项目ID', 
            'IP地址', '耗时(ms)', '状态', '错误信息'
        ])
        
        # 写入数据
        for log in logs:
            writer.writerow([
                log.id,
                log.created_at.isoformat() if log.created_at else '',
                log.level,
                log.category,
                log.action,
                log.user_id,
                log.project_id,
                log.ip_address,
                log.duration_ms,
                log.status,
                log.error_message[:200] if log.error_message else ''
            ])
        
        # 记录导出操作
        log_user_action('导出日志', f'导出了{len(logs)}条日志')
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=logs_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@logs_bp.route('/api/categories')
@login_required
def get_categories():
    """获取所有日志分类"""
    try:
        categories = db.session.query(LogEntry.category).distinct().all()
        return jsonify({
            'success': True,
            'categories': [c[0] for c in categories if c[0]]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@logs_bp.route('/api/levels')
@login_required
def get_levels():
    """获取所有日志级别"""
    try:
        levels = db.session.query(LogEntry.level).distinct().all()
        return jsonify({
            'success': True,
            'levels': [l[0] for l in levels if l[0]]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
