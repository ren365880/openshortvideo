# __init__.py - 包初始化文件
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_cors import CORS
import os

# 创建扩展对象
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
cors = CORS()


def create_app(config_class='config.Config'):
    """应用工厂函数"""
    app = Flask(__name__)

    # 加载配置
    if isinstance(config_class, str):
        from config import Config
        app.config.from_object(Config)
    else:
        app.config.from_object(config_class)

    # 确保上传目录存在
    upload_dirs = [
        'uploads', 'uploads/avatars', 'uploads/covers', 'uploads/videos',
        'uploads/thumbnails', 'uploads/character_avatars', 'uploads/images',
        'uploads/audio', 'uploads/documents', 'uploads/general'
    ]

    for directory in upload_dirs:
        os.makedirs(directory, exist_ok=True)

    # 初始化扩展
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    cors.init_app(app, supports_credentials=True, resources={r"/*": {"origins": "*"}})

    # 配置登录管理器
    login_manager.login_view = 'auth.login'
    login_manager.login_message = '请先登录'
    login_manager.login_message_category = 'info'

    # 导入并注册蓝图
    from routes.auth import bp as auth_bp
    from routes.projects import bp as projects_bp
    from routes.episodes import bp as episodes_bp
    from routes.characters import bp as characters_bp
    from routes.dashboard import bp as dashboard_bp
    from routes.uploads import bp as uploads_bp
    from routes.main import bp as main_bp
    from routes.logs import logs_bp
    from routes.generation import bp as generation_bp
    from routes.character_library import bp as character_library_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(episodes_bp)
    app.register_blueprint(characters_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(uploads_bp)
    app.register_blueprint(generation_bp)
    app.register_blueprint(character_library_bp)


    app.register_blueprint(main_bp)
    app.register_blueprint(logs_bp)

    # 用户加载器
    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # 注册路由
    from flask import render_template

    @app.route('/')
    def index():
        from flask_login import current_user
        if current_user.is_authenticated:
            return render_template('dashboard.html')
        return render_template('login.html')

    @app.route('/health')
    def health():
        from datetime import datetime
        return {'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}

    # 错误处理
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('500.html'), 500

    # 创建数据库表
    with app.app_context():
        db.create_all()
        print("数据库表已创建")

    return app