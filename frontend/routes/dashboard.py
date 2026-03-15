# routes/dashboard.py - 仪表板路由
from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from __init__ import db, bcrypt  # 修改这里
from models import Project, Episode, Character
from datetime import datetime, timedelta

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard')
@login_required
def dashboard_page():
    return render_template('dashboard.html')


@bp.route('/api/dashboard', methods=['GET'])
@login_required
def get_dashboard_data():
    # 获取用户的项目统计
    total_projects = Project.query.filter_by(user_id=current_user.id).count()
    active_projects = Project.query.filter_by(user_id=current_user.id, status='active').count()
    completed_projects = Project.query.filter_by(user_id=current_user.id, status='completed').count()

    # 获取所有项目的分集统计
    user_projects = Project.query.filter_by(user_id=current_user.id).all()
    total_episodes = 0
    total_duration = 0
    total_views = 0
    total_likes = 0

    for project in user_projects:
        episodes = Episode.query.filter_by(project_id=project.id).all()
        total_episodes += len(episodes)
        total_duration += sum(ep.duration for ep in episodes)
        total_views += sum(ep.views for ep in episodes)
        total_likes += sum(ep.likes for ep in episodes)

    # 获取最近的项目
    recent_projects = Project.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Project.updated_at.desc()
    ).limit(5).all()

    # 获取最近30天的活动统计
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    recent_episodes = Episode.query.join(
        Project, Episode.project_id == Project.id
    ).filter(
        Project.user_id == current_user.id,
        Episode.created_at >= thirty_days_ago
    ).order_by(
        Episode.created_at.desc()
    ).limit(10).all()

    recent_characters = Character.query.join(
        Project, Character.project_id == Project.id
    ).filter(
        Project.user_id == current_user.id,
        Character.created_at >= thirty_days_ago
    ).order_by(
        Character.created_at.desc()
    ).limit(10).all()

    # 项目类别分布
    category_distribution = {}
    for project in user_projects:
        category = project.category or '其他'
        category_distribution[category] = category_distribution.get(category, 0) + 1

    # 项目状态分布
    status_distribution = {}
    for project in user_projects:
        status = project.status
        status_distribution[status] = status_distribution.get(status, 0) + 1

    return jsonify({
        'stats': {
            'total_projects': total_projects,
            'active_projects': active_projects,
            'completed_projects': completed_projects,
            'total_episodes': total_episodes,
            'total_duration': total_duration,
            'total_views': total_views,
            'total_likes': total_likes,
            'total_characters': Character.query.join(
                Project, Character.project_id == Project.id
            ).filter(
                Project.user_id == current_user.id
            ).count()
        },
        'recent_projects': [project.to_dict() for project in recent_projects],
        'recent_activity': {
            'episodes': [episode.to_dict() for episode in recent_episodes],
            'characters': [character.to_dict() for character in recent_characters]
        },
        'distributions': {
            'categories': category_distribution,
            'statuses': status_distribution
        }
    })


@bp.route('/api/dashboard/project-stats/<int:project_id>', methods=['GET'])
@login_required
def get_project_stats(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    episodes = Episode.query.filter_by(project_id=project_id).all()

    # 计算统计数据
    total_views = sum(ep.views for ep in episodes)
    total_likes = sum(ep.likes for ep in episodes)
    total_duration = sum(ep.duration for ep in episodes)

    # 获取按状态的分布
    status_counts = {}
    for ep in episodes:
        status = ep.status
        status_counts[status] = status_counts.get(status, 0) + 1

    # 获取最近7天的数据
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    recent_episodes = Episode.query.filter_by(
        project_id=project_id
    ).filter(
        Episode.created_at >= seven_days_ago
    ).order_by(
        Episode.created_at.desc()
    ).all()

    # 每日统计数据
    daily_stats = {}
    for ep in recent_episodes:
        date = ep.created_at.date().isoformat()
        if date not in daily_stats:
            daily_stats[date] = {'episodes': 0, 'views': 0, 'likes': 0}
        daily_stats[date]['episodes'] += 1
        daily_stats[date]['views'] += ep.views
        daily_stats[date]['likes'] += ep.likes

    return jsonify({
        'project': project.to_dict(),
        'stats': {
            'total_episodes': len(episodes),
            'total_views': total_views,
            'total_likes': total_likes,
            'total_duration': total_duration,
            'avg_views_per_episode': total_views / len(episodes) if episodes else 0,
            'avg_likes_per_episode': total_likes / len(episodes) if episodes else 0,
            'avg_duration_per_episode': total_duration / len(episodes) if episodes else 0
        },
        'status_distribution': status_counts,
        'daily_stats': daily_stats,
        'top_episodes': sorted(
            [ep.to_dict() for ep in episodes],
            key=lambda x: x['views'],
            reverse=True
        )[:5]
    })


@bp.route('/api/dashboard/activities', methods=['GET'])
@login_required
def get_recent_activities():
    """获取用户的最近活动记录"""
    activities = []
    
    # 获取最近创建的项目（最多3个）
    recent_projects = Project.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Project.created_at.desc()
    ).limit(3).all()
    
    for project in recent_projects:
        activities.append({
            'type': 'project_created',
            'icon': 'fa-plus-circle',
            'title': f'创建了新项目',
            'description': f'《{project.title}》',
            'time': project.created_at,
            'project_id': project.id
        })
    
    # 获取最近更新的项目（编辑过的）
    recent_updated_projects = Project.query.filter_by(
        user_id=current_user.id
    ).filter(
        Project.updated_at != Project.created_at
    ).order_by(
        Project.updated_at.desc()
    ).limit(2).all()
    
    for project in recent_updated_projects:
        # 避免重复添加同一个项目
        if not any(a.get('project_id') == project.id and a['type'] == 'project_updated' for a in activities):
            activities.append({
                'type': 'project_updated',
                'icon': 'fa-edit',
                'title': '更新了项目',
                'description': f'《{project.title}》',
                'time': project.updated_at,
                'project_id': project.id
            })
    
    # 获取最近添加的角色
    recent_characters = Character.query.join(
        Project, Character.project_id == Project.id
    ).filter(
        Project.user_id == current_user.id
    ).order_by(
        Character.created_at.desc()
    ).limit(2).all()
    
    for character in recent_characters:
        project = Project.query.get(character.project_id)
        if project:
            activities.append({
                'type': 'character_added',
                'icon': 'fa-users',
                'title': '添加了新角色',
                'description': f'{character.name} 到《{project.title}》',
                'time': character.created_at,
                'project_id': project.id
            })
    
    # 按时间排序，取最近的10条
    activities.sort(key=lambda x: x['time'], reverse=True)
    activities = activities[:10]
    
    # 格式化时间
    now = datetime.utcnow()
    for activity in activities:
        time_diff = now - activity['time']
        if time_diff.days == 0:
            if time_diff.seconds < 3600:
                minutes = time_diff.seconds // 60
                activity['time_display'] = f'{minutes}分钟前' if minutes > 0 else '刚刚'
            else:
                hours = time_diff.seconds // 3600
                activity['time_display'] = f'{hours}小时前'
        elif time_diff.days == 1:
            activity['time_display'] = '昨天'
        elif time_diff.days < 7:
            activity['time_display'] = f'{time_diff.days}天前'
        else:
            activity['time_display'] = activity['time'].strftime('%m月%d日')
    
    return jsonify({
        'activities': activities
    })


@bp.route('/api/dashboard/overview', methods=['GET'])
@login_required
def get_dashboard_overview():
    # 获取当前月的统计数据
    now = datetime.utcnow()
    current_month_start = datetime(now.year, now.month, 1)

    # 本月创建的项目
    projects_this_month = Project.query.filter_by(
        user_id=current_user.id
    ).filter(
        Project.created_at >= current_month_start
    ).count()

    # 本月创建的分集
    episodes_this_month = Episode.query.join(
        Project, Episode.project_id == Project.id
    ).filter(
        Project.user_id == current_user.id,
        Episode.created_at >= current_month_start
    ).count()

    # 本月的总观看量
    views_this_month = db.session.query(db.func.sum(Episode.views)).join(
        Project, Episode.project_id == Project.id
    ).filter(
        Project.user_id == current_user.id,
        Episode.created_at >= current_month_start
    ).scalar() or 0

    # 本月的总点赞数
    likes_this_month = db.session.query(db.func.sum(Episode.likes)).join(
        Project, Episode.project_id == Project.id
    ).filter(
        Project.user_id == current_user.id,
        Episode.created_at >= current_month_start
    ).scalar() or 0

    # 与上个月的比较
    if now.month == 1:
        last_month_start = datetime(now.year - 1, 12, 1)
    else:
        last_month_start = datetime(now.year, now.month - 1, 1)

    last_month_end = current_month_start - timedelta(seconds=1)

    projects_last_month = Project.query.filter_by(
        user_id=current_user.id
    ).filter(
        Project.created_at >= last_month_start,
        Project.created_at <= last_month_end
    ).count()

    episodes_last_month = Episode.query.join(
        Project, Episode.project_id == Project.id
    ).filter(
        Project.user_id == current_user.id,
        Episode.created_at >= last_month_start,
        Episode.created_at <= last_month_end
    ).count()

    views_last_month = db.session.query(db.func.sum(Episode.views)).join(
        Project, Episode.project_id == Project.id
    ).filter(
        Project.user_id == current_user.id,
        Episode.created_at >= last_month_start,
        Episode.created_at <= last_month_end
    ).scalar() or 0

    likes_last_month = db.session.query(db.func.sum(Episode.likes)).join(
        Project, Episode.project_id == Project.id
    ).filter(
        Project.user_id == current_user.id,
        Episode.created_at >= last_month_start,
        Episode.created_at <= last_month_end
    ).scalar() or 0

    # 计算增长率
    def calculate_growth(current, last):
        if last == 0:
            return 100 if current > 0 else 0
        return ((current - last) / last) * 100

    return jsonify({
        'monthly_stats': {
            'projects': {
                'current': projects_this_month,
                'last': projects_last_month,
                'growth': calculate_growth(projects_this_month, projects_last_month)
            },
            'episodes': {
                'current': episodes_this_month,
                'last': episodes_last_month,
                'growth': calculate_growth(episodes_this_month, episodes_last_month)
            },
            'views': {
                'current': views_this_month,
                'last': views_last_month,
                'growth': calculate_growth(views_this_month, views_last_month)
            },
            'likes': {
                'current': likes_this_month,
                'last': likes_last_month,
                'growth': calculate_growth(likes_this_month, likes_last_month)
            }
        },
        'current_time': now.isoformat()
    })