# routes/characters.py - 角色管理路由
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from __init__ import db, bcrypt  # 修改这里
from models import Project, Character
import logging

logger = logging.getLogger('character_image')

bp = Blueprint('characters', __name__)


@bp.route('/api/projects/<int:project_id>/characters', methods=['GET'])
@login_required
def get_characters(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    characters = Character.query.filter_by(project_id=project_id).order_by(Character.created_at.desc()).all()

    return jsonify({
        'characters': [character.to_dict() for character in characters]
    })


@bp.route('/api/projects/<int:project_id>/characters', methods=['POST'])
@login_required
def create_character(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    data = request.get_json()

    if not data or not data.get('name'):
        return jsonify({'error': '角色名称是必填项'}), 400

    character = Character(
        name=data['name'],
        role=data.get('role', '配角'),
        gender=data.get('gender'),
        age=data.get('age'),
        description=data.get('description', ''),
        personality=data.get('personality', ''),
        color=data.get('color', '#4F46E5'),
        project_id=project_id
    )

    db.session.add(character)
    db.session.commit()

    return jsonify({
        'message': '角色创建成功',
        'character': character.to_dict()
    }), 201


@bp.route('/api/projects/<int:project_id>/characters/bulk', methods=['POST'])
@login_required
def create_characters_bulk(project_id):
    """批量创建角色"""
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    data = request.get_json()
    characters_data = data.get('characters', [])

    if not characters_data:
        return jsonify({'error': '角色数据是必填项'}), 400

    created_characters = []
    for char_data in characters_data:
        character = Character(
            name=char_data.get('name', ''),
            role=char_data.get('role', '配角'),
            gender=char_data.get('gender'),
            age=char_data.get('age'),
            description=char_data.get('description', ''),
            personality=char_data.get('personality', ''),
            appearance=char_data.get('appearance', ''),
            function=char_data.get('function', ''),
            avatar=char_data.get('avatar_front', ''),
            avatar_front=char_data.get('avatar_front', ''),
            avatar_side=char_data.get('avatar_side', ''),
            avatar_back=char_data.get('avatar_back', ''),
            color=char_data.get('color', '#4F46E5'),
            episode_number=char_data.get('episode_number'),
            project_id=project_id
        )
        db.session.add(character)
        created_characters.append(character)

    db.session.commit()

    return jsonify({
        'message': f'成功创建{len(created_characters)}个角色',
        'characters': [c.to_dict() for c in created_characters]
    }), 201


@bp.route('/api/projects/<int:project_id>/characters/check', methods=['GET'])
@login_required
def check_characters_exists(project_id):
    """检查指定集数的角色是否已存在"""
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    episode_number = request.args.get('episode_number', type=int)
    
    if not episode_number:
        return jsonify({'exists': False, 'message': '未指定集数'})

    # 检查该集是否有角色
    existing_characters = Character.query.filter_by(
        project_id=project_id, 
        episode_number=episode_number
    ).all()

    return jsonify({
        'exists': len(existing_characters) > 0,
        'count': len(existing_characters),
        'characters': [c.to_dict() for c in existing_characters]
    })


@bp.route('/api/characters/<int:character_id>', methods=['GET'])
@login_required
def get_character(character_id):
    character = Character.query.get_or_404(character_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=character.project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '无权访问此角色'}), 403

    return jsonify({'character': character.to_dict()})


@bp.route('/api/characters/<int:character_id>', methods=['PUT'])
@login_required
def update_character(character_id):
    character = Character.query.get_or_404(character_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=character.project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '无权访问此角色'}), 403

    data = request.get_json()

    if 'name' in data:
        character.name = data['name']
    if 'role' in data:
        character.role = data['role']
    if 'gender' in data:
        character.gender = data['gender']
    if 'age' in data:
        character.age = data['age']
    if 'description' in data:
        character.description = data['description']
    if 'personality' in data:
        character.personality = data['personality']
    if 'color' in data:
        character.color = data['color']

    db.session.commit()

    return jsonify({
        'message': '角色更新成功',
        'character': character.to_dict()
    })


@bp.route('/api/characters/<int:character_id>', methods=['DELETE'])
@login_required
def delete_character(character_id):
    character = Character.query.get_or_404(character_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=character.project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '无权访问此角色'}), 403

    db.session.delete(character)
    db.session.commit()

    return jsonify({'message': '角色删除成功'})


@bp.route('/api/projects/<int:project_id>/characters/batch-delete', methods=['POST'])
@login_required
def batch_delete_characters(project_id):
    """批量删除角色"""
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    data = request.get_json()
    character_ids = data.get('character_ids', [])

    if not character_ids:
        return jsonify({'error': '未指定要删除的角色'}), 400

    # 查找并删除角色
    deleted_count = 0
    for char_id in character_ids:
        character = Character.query.filter_by(id=char_id, project_id=project_id).first()
        if character:
            db.session.delete(character)
            deleted_count += 1

    db.session.commit()

    return jsonify({
        'message': f'成功删除 {deleted_count} 个角色',
        'deleted_count': deleted_count
    })


@bp.route('/api/characters/<int:character_id>/avatar', methods=['POST'])
@login_required
def upload_character_avatar(character_id):
    character = Character.query.get_or_404(character_id)

    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=character.project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '无权访问此角色'}), 403

    if 'avatar' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400

    file = request.files['avatar']

    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400

    # 检查文件类型
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    if '.' in file.filename:
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext not in allowed_extensions:
            return jsonify({'error': '只支持图片文件格式：png, jpg, jpeg, gif'}), 400

    import os
    from werkzeug.utils import secure_filename
    from datetime import datetime

    filename = secure_filename(f"character_{character_id}_{datetime.now().timestamp()}_{file.filename}")
    filepath = os.path.join('uploads/character_avatars', filename)

    # 确保目录存在
    os.makedirs('uploads/character_avatars', exist_ok=True)

    file.save(filepath)

    # 更新角色头像
    character.avatar = filename
    db.session.commit()

    return jsonify({
        'message': '角色头像上传成功',
        'avatar_url': f'/uploads/character_avatars/{filename}'
    })


@bp.route('/api/characters/<int:character_id>/image', methods=['POST'])
@login_required
def upload_character_image(character_id):
    """上传角色图像（支持正面/背面/侧面）"""
    character = Character.query.get_or_404(character_id)
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=character.project_id, user_id=current_user.id).first()
    
    if not project:
        return jsonify({'error': '无权访问此角色'}), 403
    
    # 获取视图类型
    view = request.form.get('view', 'front')
    if view not in ['front', 'back', 'side']:
        view = 'front'
    
    # 处理文件上传
    if 'image' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400
    
    file = request.files['image']
    
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    # 检查文件类型
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
    if '.' in file.filename:
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext not in allowed_extensions:
            return jsonify({'error': '只支持图片文件格式：png, jpg, jpeg, gif'}), 400
    
    import os
    from werkzeug.utils import secure_filename
    from datetime import datetime
    
    filename = secure_filename(f"{view}_{datetime.now().timestamp()}_{file.filename}")
    # 保存到统一路径：uploads/characters/{project_id}/{character_id}/
    character_dir = os.path.join('uploads', 'characters', str(project.id), str(character_id))
    os.makedirs(character_dir, exist_ok=True)
    filepath = os.path.join(character_dir, filename)
    
    file.save(filepath)
    
    # 更新对应视图的头像
    if view == 'front':
        character.avatar_front = filename
        # 如果没有主头像，也更新
        if not character.avatar:
            character.avatar = filename
    elif view == 'back':
        character.avatar_back = filename
    elif view == 'side':
        character.avatar_side = filename
    
    db.session.commit()
    
    return jsonify({
        'message': f'角色{view}图像上传成功',
        'filename': filename,
        'image_path': f'/uploads/characters/{project.id}/{character_id}/{filename}',
        'view': view
    })


@bp.route('/api/characters/<int:character_id>/image/generate', methods=['POST'])
@login_required
def generate_character_image(character_id):
    """AI生成角色图像（支持正面/背面/侧面）"""
    character = Character.query.get_or_404(character_id)
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=character.project_id, user_id=current_user.id).first()
    
    if not project:
        return jsonify({'error': '无权访问此角色'}), 403
    
    data = request.get_json() or {}
    view = data.get('view', 'front')
    prompt = data.get('prompt', '')
    reference_image = data.get('reference_image', '')
    
    # 允许客户端传入图像生成器配置
    image_gen_config = data.get('image_generator_config')
    
    if view not in ['front', 'back', 'side']:
        view = 'front'
    
    # 如果是背面或侧面，需要正面作为参考
    if view in ['back', 'side'] and not reference_image:
        reference_image = character.avatar_front or character.avatar
    
    import os
    from datetime import datetime
    
    # 构建完整的图像生成提示词
    full_prompt = prompt
    if not full_prompt and character.appearance:
        if view == 'front':
            full_prompt = f"{character.appearance}，正面视角，高品质，写实风格"
        elif view == 'back':
            full_prompt = f"{character.appearance}，背面视角，高品质，写实风格"
        elif view == 'side':
            full_prompt = f"{character.appearance}，侧面/3/4侧视角，高品质，写实风格"
    
    # 如果没有传入配置，从项目配置中获取
    if not image_gen_config:
        from services.model_config_service import get_episode_model_config
        model_config = get_episode_model_config(project.id)
        if model_config and model_config.get('image_generator'):
            image_gen_config = model_config.get('image_generator')
    
    if not image_gen_config:
        return jsonify({'error': '未配置图像生成器'}), 400

    logger.info(f"使用图像生成器配置: {image_gen_config}")
    
    # 生成图像
    import asyncio
    from services.image_generation_service import get_image_generator
    
    async def do_generate():
        generator = get_image_generator(image_gen_config)
        if not generator:
            raise Exception("无法创建图像生成器")
        
        # 如果有参考图像，需要使用编辑模式
        if reference_image and view in ['back', 'side']:
            ref_path = os.path.join('uploads/character_avatars', reference_image)
            if os.path.exists(ref_path):
                return await generator.generate_image(
                    prompt=full_prompt,
                    reference_images=[ref_path]
                )
        
        # 正面或无参考图时使用生成模式
        return await generator.generate_image(
            prompt=full_prompt,
            aspect_ratio="1:1"
        )
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(do_generate())
        loop.close()
        
        if not result.get('success'):
            raise Exception(result.get('error', '生成失败'))
        
        # 保存生成的图像到统一路径
        filename = f"{view}_{int(datetime.now().timestamp())}.png"
        character_dir = os.path.join('uploads', 'characters', str(project.id), str(character_id))
        os.makedirs(character_dir, exist_ok=True)
        filepath = os.path.join(character_dir, filename)
        
        # 保存图像
        image_data = result.get('image_data')
        image_url = result.get('image_url')
        
        if image_data:
            image_data.save(filepath)
            logger.info(f"图像已保存到: {filepath}")
        elif image_url:
            # 处理可能的相对URL
            if not image_url.startswith('http'):
                # 可能是相对路径，需要添加基础URL
                base_url = 'http://192.168.2.15:58888'
                image_url = base_url + image_url if image_url.startswith('/') else base_url + '/' + image_url
            
            logger.info(f"从URL下载图像: {image_url}")
            import requests
            response = requests.get(image_url, timeout=60)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                logger.info(f"图像已下载保存到: {filepath}")
            else:
                raise Exception(f"下载图像失败: HTTP {response.status_code}")
        
        # 更新数据库
        if view == 'front':
            character.avatar_front = filename
            if not character.avatar:
                character.avatar = filename
        elif view == 'back':
            character.avatar_back = filename
        elif view == 'side':
            character.avatar_side = filename
        
        db.session.commit()
        
        # 验证文件是否存在
        if os.path.exists(filepath):
            file_size = os.path.getsize(filepath)
            logger.info(f"文件保存成功，大小: {file_size} bytes")
            image_path = f"/uploads/characters/{project.id}/{character_id}/{filename}"
        else:
            logger.warning(f"文件保存失败: {filepath}")
            image_path = image_url if image_url else None
        
        return jsonify({
            'message': f'角色{view}图像生成成功',
            'filename': filename,
            'view': view,
            'image_path': image_path
        })
        
    except Exception as e:
        import logging
        logging.getLogger('character_image').error(f"AI生成角色图像失败: {str(e)}")
        return jsonify({'error': str(e)}), 500


@bp.route('/characters/create', methods=['GET'])
@login_required
def create_character_page():
    """创建角色页面"""
    project_id = request.args.get('project_id')
    if not project_id:
        return "缺少项目ID", 400
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()
    if not project:
        return "项目不存在或无权访问", 403
    
    return render_template('create_character.html', project=project)


@bp.route('/characters/<int:character_id>/edit', methods=['GET'])
@login_required
def edit_character_page(character_id):
    """编辑角色页面"""
    character = Character.query.get_or_404(character_id)
    
    # 验证用户是否有权访问该项目
    project = Project.query.filter_by(id=character.project_id, user_id=current_user.id).first()
    if not project:
        return "无权访问此角色", 403
    
    return render_template('edit_character.html', character=character, project=project)