# models.py - 数据库模型
from __init__ import db, bcrypt
from flask_login import UserMixin
from datetime import datetime
import json


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=True)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    avatar = db.Column(db.String(255), default='default_avatar.png')
    bio = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime, nullable=True)
    email_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # API密钥字段
    openai_api_key = db.Column(db.String(256), nullable=True)
    stability_api_key = db.Column(db.String(256), nullable=True)
    anthropic_api_key = db.Column(db.String(256), nullable=True)
    deepseek_api_key = db.Column(db.String(256), nullable=True)
    midjourney_api_key = db.Column(db.String(256), nullable=True)
    
    # 本地部署UnifiedGenerator配置
    unified_generator_url = db.Column(db.String(256), nullable=True)  # 服务器URL
    unified_generator_api_key = db.Column(db.String(256), nullable=True)  # API Key

    # 关系
    projects = db.relationship('Project', backref='creator', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'avatar': self.avatar,
            'bio': self.bio,
            'is_active': self.is_active,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'email_verified': self.email_verified,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'project_count': len(self.projects)
        }


class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    cover_image = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(50), default='其他')
    status = db.Column(db.String(20), default='draft')  # draft, active, completed, archived
    is_public = db.Column(db.Boolean, default=False)
    total_episodes = db.Column(db.Integer, default=0)
    total_duration = db.Column(db.Integer, default=0)  # 总时长（秒）
    tags = db.Column(db.Text, nullable=True)  # JSON格式的标签数组
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # 添加新字段
    theme = db.Column(db.String(200), nullable=True)  # 短剧主题
    background = db.Column(db.Text, nullable=True)  # 内容背景


    # 关系
    episodes = db.relationship('Episode', back_populates='project', lazy=True, cascade='all, delete-orphan')
    characters = db.relationship('Character', back_populates='project', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'cover_image': self.cover_image,
            'category': self.category,
            'status': self.status,
            'is_public': self.is_public,
            'total_episodes': self.total_episodes,
            'total_duration': self.total_duration,
            'tags': json.loads(self.tags) if self.tags else [],
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'user_id': self.user_id,
            'episode_count': max(self.total_episodes, len(self.episodes)),
            'character_count': len(self.characters),
            'theme': self.theme,  # 添加主题
            'background': self.background,  # 添加背景
        }


class Episode(db.Model):
    __tablename__ = 'episodes'  # 表名是 'episodes'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    episode_number = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)  # 新增：描述字段
    content = db.Column(db.Text, nullable=True)
    video_url = db.Column(db.String(500), nullable=True)
    duration = db.Column(db.Integer, default=0)  # 时长（秒）
    thumbnail = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='draft')  # draft, processing, ready, published
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 注意：这里的外键引用应该是 'episodes.id' 而不是 'episode.id'
    # 由于表名是 'episodes'，所以外键应该是 'episodes.id'
    # 但是这里引用的是其他表的id，所以应该检查Project模型的表名
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)  # 修正为 'projects.id'

    # 生成相关字段
    idea = db.Column(db.Text, nullable=True)
    user_requirement = db.Column(db.Text, nullable=True)
    style = db.Column(db.String(50), default='anime')
    generation_mode = db.Column(db.String(20), default='step_by_step')  # 新增：生成方式
    generation_config = db.Column(db.Text, nullable=True)

    # 生成状态字段
    generation_story = db.Column(db.Text, nullable=True)
    generation_story_status = db.Column(db.String(20), default='pending')  # pending, processing, completed, failed

    generation_characters_status = db.Column(db.String(20), default='pending')
    generation_portraits_status = db.Column(db.String(20), default='pending')
    generation_scene_0_status = db.Column(db.String(20), default='pending')
    generation_shots_status = db.Column(db.String(20), default='pending')
    generation_final_status = db.Column(db.String(20), default='pending')
    generation_status = db.Column(db.String(20), default='pending')

    generation_completed_at = db.Column(db.DateTime, nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)

    # 关系
    project = db.relationship('Project', back_populates='episodes')

    @property
    def status_text(self):
        status_map = {
            'draft': '草稿',
            'processing': '处理中',
            'ready': '就绪',
            'published': '已发布'
        }
        return status_map.get(self.status, self.status)

    @property
    def generation_status_text(self):
        status_map = {
            'pending': '未开始',
            'processing': '生成中',
            'completed': '已完成',
            'failed': '失败'
        }
        return status_map.get(self.generation_status, self.generation_status or '未开始')

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'episode_number': self.episode_number,
            'description': self.description,  # 新增
            'content': self.content,
            'video_url': self.video_url,
            'duration': self.duration,
            'thumbnail': self.thumbnail,
            'status': self.status,
            'status_text': self.status_text,
            'views': self.views,
            'likes': self.likes,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'project_id': self.project_id,
            'duration_formatted': self.format_duration(),

            # 生成相关字段
            'idea': self.idea,
            'user_requirement': self.user_requirement,
            'style': self.style,
            'generation_mode': self.generation_mode,  # 新增
            'generation_config': json.loads(self.generation_config) if self.generation_config else None,

            'generation_story': self.generation_story,
            'generation_story_status': self.generation_story_status,
            'generation_characters_status': self.generation_characters_status,
            'generation_portraits_status': self.generation_portraits_status,
            'generation_scene_0_status': self.generation_scene_0_status,
            'generation_shots_status': self.generation_shots_status,
            'generation_final_status': self.generation_final_status,
            'generation_status': self.generation_status,
            'generation_status_text': self.generation_status_text,
            'generation_completed_at': self.generation_completed_at.isoformat() if self.generation_completed_at else None,
            'published_at': self.published_at.isoformat() if self.published_at else None,
        }

    @property
    def duration_formatted(self):
        return self.format_duration()

    def format_duration(self):
        minutes = self.duration // 60
        seconds = self.duration % 60
        return f"{minutes}:{seconds:02d}"


class Character(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # 主角、配角、反派等
    gender = db.Column(db.String(10), nullable=True)
    age = db.Column(db.String(20), nullable=True)  # 改为字符串，支持"约500岁"这种格式
    description = db.Column(db.Text, nullable=True)  # 背景故事
    personality = db.Column(db.Text, nullable=True)  # 性格特点
    appearance = db.Column(db.Text, nullable=True)  # 外貌描述（用于AI绘画）
    function = db.Column(db.Text, nullable=True)  # 在故事中的作用
    avatar = db.Column(db.String(255), nullable=True)  # 正面头像（主头像）
    avatar_front = db.Column(db.String(255), nullable=True)  # 正面
    avatar_back = db.Column(db.String(255), nullable=True)  # 背面
    avatar_side = db.Column(db.String(255), nullable=True)  # 侧面
    color = db.Column(db.String(7), default='#4F46E5')  # 角色标识颜色
    episode_number = db.Column(db.Integer, nullable=True)  # 所属集数（一键生成时使用）
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    # 关系
    project = db.relationship('Project', back_populates='characters')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'role': self.role,
            'gender': self.gender,
            'age': self.age,
            'description': self.description,
            'personality': self.personality,
            'appearance': self.appearance,
            'function': self.function,
            'avatar': self.avatar,
            'avatar_front': self.avatar_front,
            'avatar_back': self.avatar_back,
            'avatar_side': self.avatar_side,
            'color': self.color,
            'episode_number': self.episode_number,
            'created_at': self.created_at.isoformat(),
            'project_id': self.project_id
        }


class LogEntry(db.Model):
    """系统日志记录模型"""
    __tablename__ = 'log_entry'

    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(20), nullable=False, default='INFO')  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    category = db.Column(db.String(50), nullable=False)  # AI调用、用户操作、系统错误等
    action = db.Column(db.String(100), nullable=False)  # 具体操作名称
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # 操作用户ID
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)  # 相关项目ID
    episode_id = db.Column(db.Integer, db.ForeignKey('episodes.id'), nullable=True)  # 相关分集ID
    ip_address = db.Column(db.String(45), nullable=True)  # 用户IP地址
    user_agent = db.Column(db.String(500), nullable=True)  # 用户代理信息
    request_data = db.Column(db.Text, nullable=True)  # 请求数据（JSON格式）
    response_data = db.Column(db.Text, nullable=True)  # 响应数据（JSON格式）
    error_message = db.Column(db.Text, nullable=True)  # 错误信息
    duration_ms = db.Column(db.Integer, nullable=True)  # 操作耗时（毫秒）
    status = db.Column(db.String(20), nullable=True)  # 操作状态：success, failed, pending
    extra_data = db.Column(db.Text, nullable=True)  # 额外元数据（JSON格式）
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)  # 创建时间，添加索引

    # 关系
    user = db.relationship('User', backref='logs', lazy=True)
    project = db.relationship('Project', backref='logs', lazy=True)
    episode = db.relationship('Episode', backref='logs', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'level': self.level,
            'category': self.category,
            'action': self.action,
            'user_id': self.user_id,
            'username': self.user.username if self.user else None,
            'project_id': self.project_id,
            'episode_id': self.episode_id,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'request_data': self.request_data,
            'response_data': self.response_data,
            'error_message': self.error_message,
            'duration_ms': self.duration_ms,
            'status': self.status,
            'extra_data': self.extra_data,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    @staticmethod
    def cleanup_old_logs(days=30):
        """清理指定天数之前的日志"""
        from datetime import datetime, timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        old_logs = LogEntry.query.filter(LogEntry.created_at < cutoff_date).all()
        count = len(old_logs)
        for log in old_logs:
            db.session.delete(log)
        db.session.commit()
        return count


class Tutorial(db.Model):
    """教程文章模型"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    cover_image = db.Column(db.String(255), nullable=True)
    category = db.Column(db.String(50), default='其他')
    level = db.Column(db.String(20), default='初级')  # 初级、中级、高级
    duration = db.Column(db.String(20), nullable=True)  # 如 "2小时"
    tags = db.Column(db.Text, nullable=True)  # JSON格式的标签数组
    status = db.Column(db.String(20), default='draft')  # draft, published, archived
    views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    is_free = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    # 关系
    author = db.relationship('User', backref='tutorials', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'cover_image': self.cover_image,
            'category': self.category,
            'level': self.level,
            'duration': self.duration,
            'tags': json.loads(self.tags) if self.tags else [],
            'status': self.status,
            'views': self.views,
            'likes': self.likes,
            'is_free': self.is_free,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'author_id': self.author_id,
            'author_name': self.author.username if self.author else None
        }