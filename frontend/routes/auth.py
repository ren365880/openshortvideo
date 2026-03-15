# routes/auth.py - 认证路由
from flask import Blueprint, request, jsonify, session, render_template, redirect, url_for
from flask_login import login_user, logout_user, current_user, login_required
from __init__ import db, bcrypt  # 修改这里
from models import User
import re
from datetime import datetime

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    data = request.get_json() if request.is_json else request.form

    # 支持通过email或phone登录
    email = data.get('email')
    phone = data.get('phone')
    password = data.get('password')

    if not password:
        return jsonify({'error': '密码是必填项'}), 400

    # 根据提供的账号类型查询用户
    user = None
    if email:
        user = User.query.filter_by(email=email).first()
    elif phone:
        user = User.query.filter_by(phone=phone).first()
    else:
        return jsonify({'error': '请输入账号（邮箱或手机号）'}), 400

    if not user:
        return jsonify({'error': '账号未注册'}), 401

    if not user.check_password(password):
        return jsonify({'error': '密码错误'}), 401

    if not user.is_active:
        return jsonify({'error': '账户已被禁用，请联系管理员'}), 403

    # 登录成功
    login_user(user, remember=data.get('remember', False))
    user.last_login = datetime.utcnow()
    db.session.commit()

    if request.is_json:
        return jsonify({
            'success': True,
            'message': '登录成功',
            'user': user.to_dict()
        })
    return redirect(url_for('dashboard.dashboard_page'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('register.html')

    data = request.get_json() if request.is_json else request.form

    username = data.get('username')
    email = data.get('email')
    phone = data.get('phone')
    password = data.get('password')
    confirm_password = data.get('confirm_password')

    # 验证输入
    errors = []

    if not username or len(username) < 3:
        errors.append('用户名至少需要3个字符')

    # 验证账号（邮箱或手机号）
    if email:
        if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
            errors.append('邮箱格式不正确')
    elif phone:
        if not re.match(r'^1\d{10}$', phone):
            errors.append('手机号格式不正确')
    else:
        errors.append('请输入邮箱或手机号')

    if not password or len(password) < 6:
        errors.append('密码至少需要6个字符')

    if password != confirm_password:
        errors.append('两次输入的密码不一致')

    # 检查用户名是否已存在
    if User.query.filter_by(username=username).first():
        errors.append('用户名已存在')

    # 检查邮箱或手机号是否已存在
    if email and User.query.filter_by(email=email).first():
        errors.append('邮箱已存在')
    if phone and User.query.filter_by(phone=phone).first():
        errors.append('手机号已存在')

    if errors:
        return jsonify({'error': '; '.join(errors)}), 400

    # 创建新用户
    user = User(
        username=username,
        email=email,
        phone=phone,
        bio='暂无个人简介'
    )
    user.set_password(password)

    db.session.add(user)
    db.session.commit()

    login_user(user, remember=True)

    if request.is_json:
        return jsonify({
            'message': '注册成功',
            'user': user.to_dict()
        }), 201

    return redirect(url_for('dashboard.dashboard_page'))


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    if request.is_json:
        return jsonify({'message': '已退出登录'})
    return redirect(url_for('auth.login'))


@bp.route('/api/auth/me', methods=['GET'])
def get_current_user_info():
    if current_user.is_authenticated:
        return jsonify({'user': current_user.to_dict()})
    return jsonify({'error': '未登录'}), 401


@bp.route('/profile')
@login_required
def profile_page():
    """个人资料页面"""
    return render_template('profile.html')


@bp.route('/api/auth/profile', methods=['GET', 'PUT'])
@login_required
def profile():
    if request.method == 'GET':
        return jsonify({'user': current_user.to_dict()})

    # 更新用户信息
    data = request.get_json()

    if 'username' in data and data['username'] != current_user.username:
        if User.query.filter_by(username=data['username']).first():
            return jsonify({'error': '用户名已存在'}), 400
        current_user.username = data['username']

    if 'email' in data and data['email'] != current_user.email:
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'error': '邮箱已存在'}), 400
        current_user.email = data['email']

    if 'bio' in data:
        current_user.bio = data['bio']

    if 'password' in data and data['password']:
        if len(data['password']) < 6:
            return jsonify({'error': '密码至少需要6个字符'}), 400
        current_user.set_password(data['password'])

    db.session.commit()

    return jsonify({
        'message': '个人信息更新成功',
        'user': current_user.to_dict()
    })


@bp.route('/api/auth/upload-avatar', methods=['POST'])
@login_required
def upload_avatar():
    if 'avatar' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400

    file = request.files['avatar']

    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400

    # 保存文件
    import os
    from werkzeug.utils import secure_filename
    from datetime import datetime

    filename = secure_filename(f"{current_user.id}_{datetime.now().timestamp()}_{file.filename}")
    filepath = os.path.join('uploads/avatars', filename)

    # 确保目录存在
    os.makedirs('uploads/avatars', exist_ok=True)

    file.save(filepath)

    # 更新用户头像
    current_user.avatar = filename
    db.session.commit()

    return jsonify({
        'message': '头像上传成功',
        'avatar_url': f'/uploads/avatars/{filename}'
    })