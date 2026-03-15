# run.py - 启动脚本
import os
from app import app

if __name__ == '__main__':
    # 检查环境变量
    if not os.environ.get('SECRET_KEY'):
        print("警告: 未设置SECRET_KEY环境变量，使用默认值")

    # 运行应用
    app.run(
        host=os.environ.get('HOST', '0.0.0.0'),
        port=int(os.environ.get('PORT', 5000)),
        debug=False
    )