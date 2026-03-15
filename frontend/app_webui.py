# app.py - 简化版，只用于启动
from __init__ import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

