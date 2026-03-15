# config.py - 配置文件
import os
from datetime import timedelta


class Config:
    # 基础配置
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Web服务器地址（前端端口）
    WEB_HOST = os.environ.get('WEB_HOST', 'http://192.168.2.15:5000')
    
    # API服务器地址（后端端口）
    API_HOST = os.environ.get('API_HOST', 'http://192.168.2.15:5001')

    # 数据库配置
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///short_video.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # 文件上传配置
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max file size
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'mov', 'avi', 'mkv', 'webm', 'mp3', 'wav'}

    # 会话配置
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_SECURE = False  # 生产环境设为True
    SESSION_COOKIE_HTTPONLY = True

    # 分页配置
    ITEMS_PER_PAGE = 12