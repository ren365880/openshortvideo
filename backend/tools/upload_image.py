#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片上传脚本（优化版）
支持上传图片文件到平台，封装为类，简化流程
"""

import os
import sys
import time
import mimetypes
import yaml
from pathlib import Path

try:
    import requests
except ImportError:
    print("=" * 60)
    print("错误：未安装 requests 库")
    print("请先安装：pip install requests")
    print("=" * 60)
    sys.exit(1)


def load_uploader_config(config_path="configs/idea2video_deepseek_veo3_fast.yaml"):
    """从配置文件加载图片上传配置"""
    config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), config_path)
    if os.path.exists(config_file):
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        uploader_config = config.get("image_uploader", {})
        if uploader_config:
            return uploader_config
    return None


class ImageUploader:
    """图片上传器，封装所有上传逻辑"""

    def __init__(self, username=None, password=None, email=None, image_path=None, title=None,
                 description=None, category=None, tags=None, is_public=None, config_path="configs/idea2video_deepseek_veo3_fast.yaml"):
        
        # 如果传入 config_path，则从配置文件加载
        uploader_config = load_uploader_config(config_path) if config_path else None
        
        # 使用传入的参数或从配置文件读取
        self.username = username or (uploader_config.get("username") if uploader_config else None)
        self.password = password or (uploader_config.get("password") if uploader_config else None)
        self.email = email or (uploader_config.get("email") if uploader_config else None)
        self.image_path = Path(image_path) if image_path else None
        self.title = title or "我的图片"
        self.description = description or ""
        self.category = category or "knowledge"
        self.tags = tags if tags else []
        self.is_public = is_public if is_public is not None else True

        # 运行时状态
        self.access_token = None
        self.user_id = None
        self.file_url = None

        # API 端点从配置文件加载或使用默认值
        self.base_url = (uploader_config.get("supabase_url") if uploader_config else None)
        self.anon_key = (uploader_config.get("supabase_anon_key") if uploader_config else None)
        self.bucket_name = (uploader_config.get("bucket_name") if uploader_config else None)

    def _print_step(self, num, msg):
        """打印步骤标题"""
        print(f"\n[{num}/4] {msg}")

    def _print_result(self, success, msg):
        """打印操作结果（带✅❌）"""
        mark = "✅" if success else "❌"
        print(f"      {mark} {msg}")

    def _get_login_email(self):
        """根据配置确定登录邮箱"""
        if self.email:
            return self.email, f"邮箱: {self.email}"
        elif self.username:
            return f"{self.username}@miaoda.com", f"用户名: {self.username}"
        else:
            raise ValueError("请提供用户名或邮箱")

    def login(self):
        """Step 1: 登录获取 token 和 user_id"""
        self._print_step(1, "正在登录")
        login_email, display = self._get_login_email()
        print(f"      {display}")

        try:
            auth_url = f"{self.base_url}/auth/v1/token?grant_type=password"
            headers = {
                "apikey": self.anon_key,
                "Content-Type": "application/json"
            }
            payload = {"email": login_email, "password": self.password}

            resp = requests.post(auth_url, headers=headers, json=payload, timeout=10)
            if resp.status_code != 200:
                error = resp.json()
                msg = error.get('error_description', error.get('msg', '未知错误'))
                raise RuntimeError(f"登录失败: {msg}")

            data = resp.json()
            self.access_token = data.get("access_token")
            self.user_id = data.get("user", {}).get("id")
            if not self.access_token or not self.user_id:
                raise RuntimeError("登录响应缺少 token 或 user_id")

            self._print_result(True, f"登录成功，用户ID: {self.user_id}")
        except Exception as e:
            self._print_result(False, f"登录错误: {e}")
            raise

    def check_file(self):
        """Step 2: 检查本地图片文件"""
        self._print_step(2, "检查文件")
        print(f"      路径: {self.image_path}")

        if not self.image_path.exists():
            raise FileNotFoundError(f"文件不存在: {self.image_path}")

        mime_type, _ = mimetypes.guess_type(str(self.image_path))
        if not mime_type or not mime_type.startswith('image/'):
            raise ValueError("不是有效的图片文件（支持 jpg/png/gif/webp/bmp 等）")

        file_size = self.image_path.stat().st_size
        if file_size > 100 * 1024 * 1024:  # 100 MB
            raise ValueError(f"文件超过100MB: {file_size / 1024 / 1024:.2f}MB")

        self._print_result(True, f"文件检查通过，类型: {mime_type}，大小: {file_size / 1024:.2f}KB")
        return mime_type, file_size

    def upload_file(self, mime_type):
        """Step 3: 上传文件到 Supabase Storage"""
        self._print_step(3, "上传文件到云存储")

        # 生成唯一文件名
        timestamp = int(time.time() * 1000)
        file_ext = self.image_path.suffix
        random_str = hex(int(time.time() * 1000000) % 1000000)[2:]
        file_name = f"{self.user_id}/{timestamp}_{random_str}{file_ext}"
        bucket_name = self.bucket_name

        try:
            with open(self.image_path, 'rb') as f:
                file_data = f.read()

            upload_headers = {
                "apikey": self.anon_key,
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": mime_type,
                "x-upsert": "false"
            }
            storage_url = f"{self.base_url}/storage/v1/object/{bucket_name}/{file_name}"

            resp = requests.post(storage_url, headers=upload_headers,
                                 data=file_data, timeout=60)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"上传失败: {resp.text}")

            self.file_url = f"{self.base_url}/storage/v1/object/public/{bucket_name}/{file_name}"
            self._print_result(True, f"上传成功，URL: {self.file_url}")
        except requests.exceptions.Timeout:
            raise RuntimeError("上传超时，请检查网络或文件大小")
        except Exception as e:
            raise RuntimeError(f"上传异常: {e}")

    def create_record(self):
        """Step 4: 在数据库中创建视频记录"""
        self._print_step(4, "创建发布记录")
        print(f"      标题: {self.title}，分类: {self.category}")

        video_data = {
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description or None,
            "category": self.category,
            "tags": self.tags,
            "is_public": self.is_public,
            "status": "published",
            "video_type": "uploaded",
            "image_url": self.file_url,
            "duration": 0,
            "views_count": 0,
            "likes_count": 0,
            "comments_count": 0,
            "favorites_count": 0
        }

        headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        rest_url = f"{self.base_url}/rest/v1/videos"

        try:
            resp = requests.post(rest_url, headers=headers, json=video_data, timeout=10)
            if resp.status_code not in (200, 201):
                raise RuntimeError(f"创建记录失败: {resp.text}")
            self._print_result(True, "发布成功")
        except Exception as e:
            raise RuntimeError(f"创建记录异常: {e}")

    def run(self):
        """执行完整的上传流程"""
        try:
            self.login()
            mime_type, _ = self.check_file()
            self.upload_file(mime_type)
            self.create_record()
            return True
        except Exception as e:
            print(f"\n❌ 流程中断: {e}")
            return False
