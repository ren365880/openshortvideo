# routes/uploads.py - 文件上传路由
from flask import Blueprint, send_from_directory, request, jsonify
from flask_login import login_required, current_user
import os
from datetime import datetime

bp = Blueprint('uploads', __name__)


@bp.route('/uploads/<path:filename>')
def serve_file(filename):
    """提供上传的文件"""
    return send_from_directory('uploads', filename)


@bp.route('/uploads/avatars/<filename>')
def serve_avatar(filename):
    """提供用户头像"""
    return send_from_directory('uploads/avatars', filename)


@bp.route('/default_avatar.png')
def serve_default_avatar():
    """提供默认头像"""
    return send_from_directory('uploads/avatars', 'default_avatar.png')


@bp.route('/uploads/covers/<filename>')
def serve_cover(filename):
    """提供项目封面"""
    return send_from_directory('uploads/covers', filename)


@bp.route('/uploads/videos/<filename>')
def serve_video(filename):
    """提供视频文件"""
    return send_from_directory('uploads/videos', filename)


@bp.route('/uploads/thumbnails/<filename>')
def serve_thumbnail(filename):
    """提供视频缩略图"""
    return send_from_directory('uploads/thumbnails', filename)


@bp.route('/uploads/character_avatars/<filename>')
def serve_character_avatar(filename):
    """提供角色头像"""
    return send_from_directory('uploads/character_avatars', filename)


def process_video(filepath, filename):
    """处理视频文件：生成缩略图和获取视频信息"""
    import subprocess
    import os
    
    result = {
        'duration': 0,
        'thumbnail_generated': False,
        'thumbnail_url': None,
        'error': None
    }
    
    try:
        # 检查ffmpeg是否可用
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            ffmpeg_available = True
        except (subprocess.CalledProcessError, FileNotFoundError):
            ffmpeg_available = False
            result['error'] = 'FFmpeg不可用，跳过视频处理'
            return result
        
        # 获取视频时长
        cmd = [
            'ffmpeg', '-i', filepath,
            '-f', 'null', '-'
        ]
        process = subprocess.run(cmd, capture_output=True, text=True, stderr=subprocess.STDOUT)
        
        # 从输出中提取时长信息（简化处理）
        import re
        duration_match = re.search(r'Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})', process.stdout)
        if duration_match:
            hours, minutes, seconds = map(float, duration_match.groups())
            total_seconds = hours * 3600 + minutes * 60 + seconds
            result['duration'] = int(total_seconds)
        
        # 生成缩略图
        thumbnail_filename = f"thumb_{os.path.splitext(filename)[0]}.jpg"
        thumbnail_dir = 'uploads/thumbnails'
        os.makedirs(thumbnail_dir, exist_ok=True)
        thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
        
        # 在视频的第10秒处截取缩略图
        cmd = [
            'ffmpeg', '-i', filepath,
            '-ss', '00:00:10',  # 第10秒
            '-vframes', '1',     # 截取1帧
            '-q:v', '2',         # 质量参数
            thumbnail_path
        ]
        
        subprocess.run(cmd, capture_output=True, check=True)
        
        if os.path.exists(thumbnail_path):
            result['thumbnail_generated'] = True
            result['thumbnail_url'] = f'/uploads/thumbnails/{thumbnail_filename}'
        
    except Exception as e:
        result['error'] = f'视频处理失败: {str(e)}'
    
    return result


@bp.route('/api/uploads', methods=['POST'])
@login_required
def upload_file():
    """通用文件上传接口"""
    if 'file' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400

    file = request.files['file']
    file_type = request.form.get('type', 'general')

    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400

    # 根据文件类型设置允许的扩展名
    allowed_extensions = {
        'image': {'png', 'jpg', 'jpeg', 'gif', 'webp'},
        'video': {'mp4', 'mov', 'avi', 'mkv', 'webm'},
        'audio': {'mp3', 'wav', 'ogg', 'm4a'},
        'document': {'pdf', 'doc', 'docx', 'txt'},
        'general': {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'mp3', 'wav', 'pdf', 'doc', 'docx', 'txt'}
    }

    file_category = file_type
    if file_type not in allowed_extensions:
        file_category = 'general'

    # 检查文件扩展名
    file_ext = ''
    if '.' in file.filename:
        file_ext = file.filename.rsplit('.', 1)[1].lower()
        if file_ext not in allowed_extensions[file_category]:
            return jsonify({
                'error': f'不支持的文件格式：{file_ext}，支持的格式：{", ".join(allowed_extensions[file_category])}'
            }), 400

    from werkzeug.utils import secure_filename

    # 创建安全的文件名
    timestamp = int(datetime.now().timestamp())
    filename = secure_filename(f"{current_user.id}_{timestamp}_{file.filename}")

    # 根据文件类型确定存储目录
    upload_dirs = {
        'image': 'uploads/images',
        'video': 'uploads/videos',
        'audio': 'uploads/audio',
        'document': 'uploads/documents',
        'general': 'uploads/general'
    }

    upload_dir = upload_dirs.get(file_type, 'uploads/general')
    filepath = os.path.join(upload_dir, filename)

    # 确保目录存在
    os.makedirs(upload_dir, exist_ok=True)

    # 保存文件
    file.save(filepath)

    # 获取文件大小
    file_size = os.path.getsize(filepath)

    # 如果是图片，获取尺寸信息
    file_info = {
        'filename': filename,
        'original_name': file.filename,
        'size': file_size,
        'type': file_type,
        'url': f'/{upload_dir}/{filename}',
        'uploaded_at': datetime.utcnow().isoformat()
    }

    # 如果是图片，获取尺寸
    if file_type == 'image' or ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'}:
        try:
            from PIL import Image
            with Image.open(filepath) as img:
                width, height = img.size
                file_info['dimensions'] = {'width': width, 'height': height}
        except ImportError:
            pass
        except Exception as e:
            print(f"获取图片尺寸失败: {e}")

    # 处理视频文件
    if file_type == 'video' or file_ext in {'mp4', 'mov', 'avi', 'mkv', 'webm'}:
        video_info = process_video(filepath, filename)
        file_info['video_info'] = video_info
        
        # 如果生成了缩略图，添加到文件信息中
        if video_info.get('thumbnail_url'):
            file_info['thumbnail_url'] = video_info['thumbnail_url']
        
        # 如果有视频时长，添加到文件信息中
        if video_info.get('duration'):
            file_info['duration'] = video_info['duration']

    return jsonify({
        'message': '文件上传成功',
        'file': file_info
    })


@bp.route('/api/uploads/list', methods=['GET'])
@login_required
def list_files():
    """获取用户上传的文件列表"""
    file_type = request.args.get('type', 'all')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # 定义文件类型对应的目录
    type_dirs = {
        'image': ['uploads/images', 'uploads/covers', 'uploads/avatars', 'uploads/thumbnails',
                  'uploads/character_avatars'],
        'video': ['uploads/videos'],
        'audio': ['uploads/audio'],
        'document': ['uploads/documents'],
        'all': ['uploads/images', 'uploads/videos', 'uploads/audio', 'uploads/documents',
                'uploads/covers', 'uploads/avatars', 'uploads/thumbnails', 'uploads/character_avatars',
                'uploads/general']
    }

    # 获取要扫描的目录
    directories = type_dirs.get(file_type, ['uploads/general'])

    files = []

    import os
    from datetime import datetime

    for directory in directories:
        if os.path.exists(directory):
            for filename in os.listdir(directory):
                # 检查文件是否属于当前用户
                if filename.startswith(f"{current_user.id}_"):
                    filepath = os.path.join(directory, filename)

                    if os.path.isfile(filepath):
                        stat = os.stat(filepath)
                        files.append({
                            'filename': filename,
                            'path': f'/{directory}/{filename}',
                            'size': stat.st_size,
                            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            'type': os.path.splitext(filename)[1].lower().replace('.', '')
                        })

    # 按修改时间排序
    files.sort(key=lambda x: x['modified'], reverse=True)

    # 分页
    total = len(files)
    start = (page - 1) * per_page
    end = start + per_page
    paginated_files = files[start:end]

    return jsonify({
        'files': paginated_files,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page
        }
    })


@bp.route('/api/uploads/<filename>', methods=['DELETE'])
@login_required
def delete_file(filename):
    """删除上传的文件"""
    import os
    from werkzeug.utils import secure_filename

    # 安全处理文件名
    filename = secure_filename(filename)

    # 在所有上传目录中查找文件
    upload_dirs = [
        'uploads/images', 'uploads/videos', 'uploads/audio', 'uploads/documents',
        'uploads/covers', 'uploads/avatars', 'uploads/thumbnails', 'uploads/character_avatars', 'uploads/general'
    ]

    file_found = False
    for directory in upload_dirs:
        filepath = os.path.join(directory, filename)
        if os.path.exists(filepath) and filename.startswith(f"{current_user.id}_"):
            os.remove(filepath)
            file_found = True
            break

    if not file_found:
        return jsonify({'error': '文件不存在或无权删除'}), 404

    return jsonify({'message': '文件删除成功'})


@bp.route('/api/uploads/storage', methods=['GET'])
@login_required
def get_storage_info():
    """获取用户的存储空间使用情况"""
    import os

    total_size = 0
    file_count = 0

    # 扫描所有上传目录中属于当前用户的文件
    upload_dirs = [
        'uploads/images', 'uploads/videos', 'uploads/audio', 'uploads/documents',
        'uploads/covers', 'uploads/avatars', 'uploads/thumbnails', 'uploads/character_avatars', 'uploads/general'
    ]

    for directory in upload_dirs:
        if os.path.exists(directory):
            for filename in os.listdir(directory):
                if filename.startswith(f"{current_user.id}_"):
                    filepath = os.path.join(directory, filename)
                    if os.path.isfile(filepath):
                        total_size += os.path.getsize(filepath)
                        file_count += 1

    # 转换为可读格式
    def format_size(size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    # 假设用户有1GB的免费存储空间
    free_space = 1 * 1024 * 1024 * 1024  # 1GB in bytes
    used_percentage = (total_size / free_space) * 100 if free_space > 0 else 0

    return jsonify({
        'storage': {
            'total': format_size(total_size),
            'total_bytes': total_size,
            'free': format_size(free_space - total_size),
            'free_bytes': free_space - total_size,
            'used_percentage': round(used_percentage, 1),
            'file_count': file_count
        },
        'limits': {
            'free_space': format_size(free_space),
            'free_space_bytes': free_space
        }
    })