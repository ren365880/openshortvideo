# db_manager.py
import sqlite3
import os
from tabulate import tabulate
from database import get_db


def list_all_images():
    """列出所有图片记录"""
    db = get_db()
    images = db.get_all_images()

    if not images:
        print("数据库中没有图片记录")
        return

    # 格式化输出
    table_data = []
    for img in images:
        table_data.append([
            img['id'],
            os.path.basename(img['local_path']),
            img['image_url'][:50] + "..." if len(img['image_url']) > 50 else img['image_url'],
            img['task_id'],
            "是" if os.path.exists(img['local_path']) else "否",
            img['created_at']
        ])

    headers = ["ID", "文件名", "URL", "任务ID", "文件存在", "创建时间"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    print(f"\n总计: {len(images)} 条记录")


def search_by_local_path(path_pattern: str):
    """根据路径模式搜索"""
    db = get_db()
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM images 
            WHERE local_path LIKE ? AND status = 'active'
            ORDER BY created_at DESC
        ''', (f'%{path_pattern}%',))

        rows = cursor.fetchall()
        if not rows:
            print(f"没有找到包含 '{path_pattern}' 的记录")
            return

        table_data = []
        for row in rows:
            table_data.append([
                row['id'],
                os.path.basename(row['local_path']),
                row['image_url'][:50] + "..." if len(row['image_url']) > 50 else row['image_url'],
                row['task_id'],
                "是" if os.path.exists(row['local_path']) else "否"
            ])

        headers = ["ID", "文件名", "URL", "任务ID", "文件存在"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        print(f"\n找到 {len(rows)} 条记录")


def cleanup_invalid():
    """清理无效记录"""
    db = get_db()
    deleted = db.cleanup_invalid_records()
    print(f"清理了 {deleted} 条无效记录")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="数据库管理工具")
    subparsers = parser.add_subparsers(dest="command", help="命令",)

    # list命令
    subparsers.add_parser("list", help="列出所有图片记录")

    # search命令
    search_parser = subparsers.add_parser("search", help="搜索图片记录")
    search_parser.add_argument("pattern", help="路径搜索模式")

    # cleanup命令
    subparsers.add_parser("cleanup", help="清理无效记录")

    args = parser.parse_args()

    if args.command == "list":
        list_all_images()
    elif args.command == "search":
        search_by_local_path(args.pattern)
    elif args.command == "cleanup":
        cleanup_invalid()
    else:
        parser.print_help()