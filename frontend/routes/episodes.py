# routes/episodes.py - 分集管理路由
from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required, current_user
from __init__ import db, bcrypt  # 修改这里
from models import Project, Episode
from services.log_service import log_user_action, log_error
from datetime import datetime

bp = Blueprint('episodes', __name__)


@bp.route('/api/projects/<int:project_id>/episodes', methods=['GET'])
@login_required
def get_episodes(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    episodes = Episode.query.filter_by(project_id=project_id).order_by(Episode.episode_number).all()

    return jsonify({
        'episodes': [episode.to_dict() for episode in episodes]
    })


@bp.route('/api/projects/<int:project_id>/episodes', methods=['POST'])
@login_required
def create_episode(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    # 支持JSON和FormData两种格式
    if request.content_type and 'application/json' in request.content_type:
        data = request.get_json() or {}
    else:
        # FormData格式
        data = request.form.to_dict()
    
    # 确定分集号
    if 'episode_number' in data and data['episode_number']:
        episode_number = int(data['episode_number'])
    else:
        # 如果没有指定，则使用当前最大分集号+1
        last_episode = Episode.query.filter_by(project_id=project_id).order_by(Episode.episode_number.desc()).first()
        episode_number = last_episode.episode_number + 1 if last_episode else 1

    episode = Episode(
        title=data.get('title', f'第{episode_number}集'),
        episode_number=episode_number,
        content=data.get('content', ''),
        duration=int(data.get('duration', 0)) if data.get('duration') else 0,
        status=data.get('status', 'draft'),
        project_id=project_id
    )

    db.session.add(episode)

    # 更新项目的总集数
    project.total_episodes = Episode.query.filter_by(project_id=project_id).count()
    project.updated_at = datetime.utcnow()

    db.session.commit()

    # 记录分集创建日志
    log_user_action(
        '创建分集',
        f"创建分集: {episode.title} (第{episode.episode_number}集)",
        level='INFO',
        project_id=project_id,
        episode_id=episode.id,
        request_data={'title': episode.title, 'episode_number': episode.episode_number}
    )

    return jsonify({
        'message': '分集创建成功',
        'episode': episode.to_dict()
    }), 201


@bp.route('/api/episodes/<int:episode_id>', methods=['GET'])
@login_required
def get_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    return jsonify({'episode': episode.to_dict()})


@bp.route('/api/episodes/<int:episode_id>', methods=['PUT'])
@login_required
def update_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    data = request.get_json()

    if 'title' in data:
        episode.title = data['title']
    if 'content' in data:
        episode.content = data['content']
    if 'duration' in data:
        episode.duration = data['duration']
    if 'status' in data:
        episode.status = data['status']
    if 'episode_number' in data:
        episode.episode_number = data['episode_number']

    episode.updated_at = datetime.utcnow()

    # 更新项目的更新时间
    project.updated_at = datetime.utcnow()

    db.session.commit()

    # 记录分集更新日志
    log_user_action(
        '更新分集',
        f"更新分集: {episode.title} (第{episode.episode_number}集)",
        level='INFO',
        project_id=episode.project_id,
        episode_id=episode.id,
        request_data={'title': episode.title, 'status': episode.status}
    )

    return jsonify({
        'message': '分集更新成功',
        'episode': episode.to_dict()
    })


@bp.route('/api/episodes/<int:episode_id>', methods=['DELETE'])
@login_required
def delete_episode(episode_id):
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()

    if not project:
        log_error('删除分集', '无权访问此分集', episode_id=episode_id)
        return jsonify({'error': '无权访问此分集'}), 403

    episode_title = episode.title
    episode_number = episode.episode_number
    project_id = episode.project_id

    db.session.delete(episode)

    # 更新项目的总集数
    project.total_episodes = Episode.query.filter_by(project_id=project.id).count()
    project.updated_at = datetime.utcnow()

    db.session.commit()

    # 记录分集删除日志
    log_user_action(
        '删除分集',
        f"删除分集: {episode_title} (第{episode_number}集)",
        level='WARNING',
        project_id=project_id,
        request_data={'episode_id': episode_id, 'title': episode_title}
    )

    return jsonify({'message': '分集删除成功'})


@bp.route('/api/episodes/<int:episode_id>/video', methods=['POST'])
@login_required
def upload_episode_video(episode_id):
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    if 'video' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400

    file = request.files['video']

    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400

    # 检查文件类型
    allowed_extensions = {'mp4', 'mov', 'avi', 'mkv', 'webm'}
    if '.' in file.filename:
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext not in allowed_extensions:
            return jsonify({'error': '只支持视频文件格式：mp4, mov, avi, mkv, webm'}), 400

    import os
    from werkzeug.utils import secure_filename
    from datetime import datetime

    filename = secure_filename(f"video_{episode_id}_{datetime.now().timestamp()}_{file.filename}")
    filepath = os.path.join('uploads/videos', filename)

    # 确保目录存在
    os.makedirs('uploads/videos', exist_ok=True)

    file.save(filepath)

    # 更新分集视频
    episode.video_url = filename
    episode.status = 'processing'  # 设置为处理中状态

    db.session.commit()

    return jsonify({
        'message': '视频上传成功，正在处理中...',
        'video_url': f'/uploads/videos/{filename}'
    })


@bp.route('/api/episodes/<int:episode_id>/thumbnail', methods=['POST'])
@login_required
def upload_episode_thumbnail(episode_id):
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    if 'thumbnail' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400

    file = request.files['thumbnail']

    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400

    # 检查文件类型
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    if '.' in file.filename:
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext not in allowed_extensions:
            return jsonify({'error': '只支持图片文件格式：png, jpg, jpeg, gif'}), 400

    import os
    from werkzeug.utils import secure_filename
    from datetime import datetime

    filename = secure_filename(f"thumbnail_{episode_id}_{datetime.now().timestamp()}_{file.filename}")
    filepath = os.path.join('uploads/thumbnails', filename)

    # 确保目录存在
    os.makedirs('uploads/thumbnails', exist_ok=True)

    file.save(filepath)

    # 更新分集缩略图
    episode.thumbnail = filename
    db.session.commit()

    return jsonify({
        'message': '缩略图上传成功',
        'thumbnail_url': f'/uploads/thumbnails/{filename}'
    })


@bp.route('/episodes/create', methods=['GET'])
@login_required
def create_episode_page():
    """创建分集页面"""
    project_id = request.args.get('project_id')
    if not project_id:
        return "缺少项目ID", 400
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()
    if not project:
        return "项目不存在或无权访问", 403
    
    return render_template('create_episode.html', project=project)


@bp.route('/episodes/<int:episode_id>', methods=['GET'])
@login_required
def episode_detail_page(episode_id):
    """分集详情页面"""
    episode = Episode.query.get_or_404(episode_id)
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return "无权访问此分集", 403
    
    return render_template('episode_detail.html', episode=episode, project=project)


@bp.route('/episodes/<int:episode_id>/edit', methods=['GET'])
@login_required
def edit_episode_page(episode_id):
    """编辑分集页面"""
    episode = Episode.query.get_or_404(episode_id)
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return "无权访问此分集", 403
    
    return render_template('edit_episode.html', episode=episode, project=project)


@bp.route('/episodes/<int:episode_id>/generate')
@login_required
def generate_episode_page(episode_id):
    """生成分集页面"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return "无权访问此分集", 403

    # 获取API服务器地址配置
    api_host = current_app.config.get('API_HOST', 'http://localhost:5001')
    
    return render_template('episode_generate.html', episode=episode, project=project, api_host=api_host)


@bp.route('/episodes/<int:episode_id>/preview')
@login_required
def preview_episode_page(episode_id):
    """预览分集页面"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return "无权访问此分集", 403

    return render_template('episode_preview.html', episode=episode, project=project)


@bp.route('/api/episodes/<int:episode_id>/publish', methods=['POST'])
@login_required
def publish_episode(episode_id):
    """发布分集"""
    episode = Episode.query.get_or_404(episode_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=episode.project_id, user_id=current_user.id).first()
    if not project:
        return jsonify({'error': '无权访问此分集'}), 403

    # 确保分集已准备好
    if episode.status != 'ready':
        return jsonify({'error': '分集尚未准备就绪，无法发布'}), 400

    episode.status = 'published'
    episode.published_at = datetime.utcnow()
    db.session.commit()

    log_user_action(
        '发布分集',
        f"发布分集: {episode.title} (第{episode.episode_number}集)",
        level='INFO',
        project_id=episode.project_id,
        episode_id=episode.id,
        request_data={'title': episode.title, 'status': episode.status}
    )

    return jsonify({
        'message': '分集发布成功',
        'episode': episode.to_dict()
    })