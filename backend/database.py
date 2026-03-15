# database.py
import sqlite3
from datetime import datetime
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass
from contextlib import contextmanager


@dataclass
class ImageRecord:
    """图片记录数据类"""
    id: int
    local_path: str
    image_url: str
    task_id: str
    prompt: Optional[str] = None
    created_at: Optional[str] = None
    aspect_ratio: Optional[str] = None
    status: str = 'active'


class ImageDatabase:
    """图片数据库管理类"""

    def __init__(self, db_path: str = 'images.db'):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """初始化数据库表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 创建图片记录表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    local_path TEXT UNIQUE NOT NULL,
                    image_url TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    prompt TEXT,
                    aspect_ratio TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_local_path ON images (local_path)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_id ON images (task_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON images (status)')

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def add_image_record(self, local_path: str, image_url: str, task_id: str,
                         prompt: Optional[str] = None, aspect_ratio: Optional[str] = None) -> int:
        """添加图片记录"""
        # 确保本地路径是绝对路径
        local_path = os.path.abspath(local_path)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO images (local_path, image_url, task_id, prompt, aspect_ratio)
                    VALUES (?, ?, ?, ?, ?)
                ''', (local_path, image_url, task_id, prompt, aspect_ratio))
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                # 如果已存在，则更新
                cursor.execute('''
                    UPDATE images 
                    SET image_url = ?, task_id = ?, prompt = ?, aspect_ratio = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE local_path = ?
                ''', (image_url, task_id, prompt, aspect_ratio, local_path))
                conn.commit()
                return cursor.lastrowid

    def get_image_url(self, local_path: str) -> Optional[str]:
        """根据本地路径获取图片URL"""
        local_path = os.path.abspath(local_path)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT image_url FROM images 
                WHERE local_path = ? AND status = 'active'
            ''', (local_path,))
            result = cursor.fetchone()
            return result['image_url'] if result else None

    def get_local_path(self, image_url: str) -> Optional[str]:
        """根据图片URL获取本地路径"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT local_path FROM images 
                WHERE image_url = ? AND status = 'active'
            ''', (image_url,))
            result = cursor.fetchone()
            return result['local_path'] if result else None

    def get_image_by_task_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """根据任务ID获取图片记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM images 
                WHERE task_id = ? AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            ''', (task_id,))
            result = cursor.fetchone()
            return dict(result) if result else None

    def get_all_images(self) -> list:
        """获取所有图片记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM images WHERE status = "active" ORDER BY created_at DESC')
            return [dict(row) for row in cursor.fetchall()]

    def update_image_url(self, local_path: str, image_url: str) -> bool:
        """更新图片URL"""
        local_path = os.path.abspath(local_path)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE images 
                SET image_url = ?, updated_at = CURRENT_TIMESTAMP
                WHERE local_path = ?
            ''', (image_url, local_path))
            conn.commit()
            return cursor.rowcount > 0

    def delete_image_record(self, local_path: str) -> bool:
        """删除图片记录（软删除）"""
        local_path = os.path.abspath(local_path)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE images 
                SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                WHERE local_path = ?
            ''', (local_path,))
            conn.commit()
            return cursor.rowcount > 0

    def batch_get_urls(self, local_paths: list) -> Dict[str, str]:
        """批量获取本地路径对应的URL"""
        local_paths = [os.path.abspath(path) for path in local_paths]
        result = {}

        with self._get_connection() as conn:
            cursor = conn.cursor()
            for path in local_paths:
                cursor.execute('''
                    SELECT image_url FROM images 
                    WHERE local_path = ? AND status = 'active'
                ''', (path,))
                row = cursor.fetchone()
                if row:
                    result[path] = row['image_url']

        return result

    def cleanup_invalid_records(self) -> int:
        """清理本地文件不存在的记录"""
        deleted_count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT local_path FROM images WHERE status = "active"')
            rows = cursor.fetchall()

            for row in rows:
                local_path = row['local_path']
                if not os.path.exists(local_path):
                    cursor.execute('''
                        UPDATE images 
                        SET status = 'deleted', updated_at = CURRENT_TIMESTAMP
                        WHERE local_path = ?
                    ''', (local_path,))
                    deleted_count += 1

            conn.commit()

        return deleted_count

    def get_paginated_images(self, page: int = 1, per_page: int = 20) -> dict:
        """获取分页的图片记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 获取总数
            cursor.execute('SELECT COUNT(*) as total FROM images WHERE status = "active"')
            total = cursor.fetchone()['total']

            # 计算分页
            offset = (page - 1) * per_page

            # 获取分页数据
            cursor.execute('''
                SELECT * FROM images 
                WHERE status = "active" 
                ORDER BY created_at DESC 
                LIMIT ? OFFSET ?
            ''', (per_page, offset))

            rows = cursor.fetchall()
            # 确保转换为普通字典
            images = []
            for row in rows:
                image = dict(row)
                # 确保所有字段都存在
                image.setdefault('prompt', '')
                image.setdefault('aspect_ratio', '')
                images.append(image)

            return {
                'images': images,
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': (total + per_page - 1) // per_page
            }

    def search_images(self, keyword: str) -> list:
        """搜索图片记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM images 
                WHERE status = "active" AND 
                (local_path LIKE ? OR 
                 prompt LIKE ? OR 
                 task_id LIKE ? OR 
                 image_url LIKE ?)
                ORDER BY created_at DESC
            ''', (f'%{keyword}%', f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_image_by_id(self, image_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取图片记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM images 
                WHERE id = ? AND status = "active"
            ''', (image_id,))
            result = cursor.fetchone()
            return dict(result) if result else None


# 全局数据库实例
db_instance: Optional[ImageDatabase] = None


def get_db() -> ImageDatabase:
    """获取数据库实例（单例模式）"""
    global db_instance
    if db_instance is None:
        db_instance = ImageDatabase()
    return db_instance