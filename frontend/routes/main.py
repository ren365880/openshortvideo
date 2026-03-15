# routes/main.py
import json
import logging
import sys
from datetime import datetime
import os
import uuid
from flask import Blueprint, render_template, jsonify, request, flash,Response
from flask_login import login_required, current_user
from models import db, User, Project, Episode, Character, Tutorial

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('ai_generate_field')


bp = Blueprint('main', __name__)


@bp.route('/discover')
def discover():
    """发现页面"""
    return render_template('discover.html')


@bp.route('/tutorials')
def tutorials():
    """教程页面"""
    return render_template('tutorials.html')


@bp.route('/AI_dialogue')
def ai_dialogue():
    """AI对话页面"""
    return render_template('lingxi_agent.html')


@bp.route('/settings')
@login_required
def settings():
    """设置页面"""
    # 获取用户的API密钥信息
    api_keys = {
        'openai': {
            'name': 'OpenAI GPT',
            'api_key': current_user.openai_api_key if hasattr(current_user, 'openai_api_key') else '',
            'endpoint': 'https://api.openai.com/v1',
            'models': ['gpt-4', 'gpt-3.5-turbo', 'dall-e-3']
        },
        'stability': {
            'name': 'Stability AI',
            'api_key': current_user.stability_api_key if hasattr(current_user, 'stability_api_key') else '',
            'endpoint': 'https://api.stability.ai/v1',
            'models': ['stable-diffusion-xl-1024-v1-0', 'stable-diffusion-v1-6']
        },
        'anthropic': {
            'name': 'Anthropic Claude',
            'api_key': current_user.anthropic_api_key if hasattr(current_user, 'anthropic_api_key') else '',
            'endpoint': 'https://api.anthropic.com/v1',
            'models': ['claude-3-opus-20240229', 'claude-3-sonnet-20240229', 'claude-3-haiku-20240307']
        },
        'deepseek': {
            'name': 'DeepSeek',
            'api_key': current_user.deepseek_api_key if hasattr(current_user, 'deepseek_api_key') else '',
            'endpoint': 'https://api.deepseek.com/v1',
            'models': ['deepseek-chat', 'deepseek-coder']
        },
        'midjourney': {
            'name': 'Midjourney',
            'api_key': current_user.midjourney_api_key if hasattr(current_user, 'midjourney_api_key') else '',
            'endpoint': 'https://api.midjourney.com/v1',
            'models': ['mj-5.2', 'mj-5.1', 'niji-6']
        },
        'unified_generator': {
            'name': '本地UnifiedGenerator',
            'url': current_user.unified_generator_url if hasattr(current_user, 'unified_generator_url') else 'http://192.168.2.15:58888',
            'api_key': current_user.unified_generator_api_key if hasattr(current_user, 'unified_generator_api_key') else '',
            'models': ['black-forest-labs/FLUX.2-klein-4B']
        }
    }

    return render_template('settings.html', api_keys=api_keys)


@bp.route('/api/discover/trending')
def get_trending_dramas():
    """获取热门短剧"""
    # 模拟数据
    trending_dramas = [
        {
            'id': 1,
            'title': '时空恋人',
            'description': '穿越时空的爱情故事，感动千万观众',
            'cover': 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '爱情',
            'views': '120万',
            'likes': '5.6万',
            'author': '时光影视',
            'episodes': 15
        },
        {
            'id': 2,
            'title': '逆袭人生',
            'description': '从平凡到非凡的逆袭之路',
            'cover': 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '励志',
            'views': '98万',
            'likes': '4.8万',
            'author': '梦想工作室',
            'episodes': 12
        },
        {
            'id': 3,
            'title': '迷雾追踪',
            'description': '悬疑推理短剧，层层递进的剧情',
            'cover': 'https://images.unsplash.com/photo-1536440136628-849c177e76a1?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '悬疑',
            'views': '85万',
            'likes': '4.2万',
            'author': '悬疑剧场',
            'episodes': 10
        }
    ]

    return jsonify(trending_dramas)


@bp.route('/api/discover/creators')
def get_recommended_creators():
    """获取推荐创作者"""
    # 模拟数据
    creators = [
        {
            'id': 1,
            'name': '张艺导',
            'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?ixlib=rb-4.0.3&auto=format&fit=crop&w=200&q=80',
            'bio': '资深短剧导演，专注都市情感题材',
            'works': 28,
            'followers': '12.5万'
        },
        {
            'id': 2,
            'name': '李编剧',
            'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?ixlib=rb-4.0.3&auto=format&fit=crop&w=200&q=80',
            'bio': '新生代编剧，擅长悬疑推理',
            'works': 15,
            'followers': '8.7万'
        },
        {
            'id': 3,
            'name': '王制片',
            'avatar': 'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?ixlib=rb-4.0.3&auto=format&fit=crop&w=200&q=80',
            'bio': '专业制片人，多部热门作品',
            'works': 42,
            'followers': '25.3万'
        }
    ]

    return jsonify(creators)


@bp.route('/api/tutorials/recommended')
def get_recommended_tutorials():
    """获取推荐教程"""
    # 先尝试从数据库获取已发布的教程
    tutorials = Tutorial.query.filter(Tutorial.status == 'published').order_by(Tutorial.views.desc()).limit(6).all()
    
    if tutorials:
        # 如果有数据库中的教程，使用它们
        tutorial_list = []
        for tutorial in tutorials:
            tutorial_dict = tutorial.to_dict()
            # 为了保持与前端兼容，添加一些字段
            tutorial_dict['description'] = tutorial.content[:100] + '...' if tutorial.content else ''
            tutorial_dict['cover'] = tutorial.cover_image or 'https://images.unsplash.com/photo-1595769812725-4c6564f70466?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80'
            # 模拟学生数量
            if tutorial.views < 1000:
                students = f'{tutorial.views}'
            elif tutorial.views < 10000:
                students = f'{tutorial.views // 1000}千'
            else:
                students = f'{tutorial.views // 10000}万'
            tutorial_dict['students'] = students
            tutorial_dict['free'] = tutorial.is_free
            tutorial_list.append(tutorial_dict)
        return jsonify(tutorial_list)
    
    # 如果没有教程，创建示例教程
    # 获取第一个用户作为作者
    author = User.query.first()
    if not author:
        # 如果没有用户，返回模拟数据
        tutorials = [
            {
                'id': 1,
                'title': '短剧制作入门指南',
                'description': '从零开始学习短剧制作的基础知识和流程',
                'cover': 'https://images.unsplash.com/photo-1595769812725-4c6564f70466?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
                'level': '初级',
                'duration': '2小时',
                'students': '5.2万',
                'free': True
            },
            {
                'id': 2,
                'title': '高级剪辑技巧',
                'description': '掌握专业级的视频剪辑技巧和特效制作',
                'cover': 'https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
                'level': '高级',
                'duration': '4小时',
                'students': '3.8万',
                'free': False
            },
            {
                'id': 3,
                'title': 'AI剧本生成实战',
                'description': '利用AI工具快速生成高质量剧本的技巧',
                'cover': 'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
                'level': '中级',
                'duration': '3小时',
                'students': '4.5万',
                'free': True
            }
        ]
        return jsonify(tutorials)
    
    # 创建示例教程
    sample_tutorials = [
        {
            'title': '短剧制作入门指南',
            'content': '欢迎来到短剧制作的世界！本教程将带你从零开始，逐步掌握短剧制作的基本流程和技巧。\n\n## 什么是短剧？\n短剧是一种时长较短、情节紧凑的视频形式，通常在几分钟到十几分钟之间。它要求创作者在有限的时间内讲好一个完整的故事。\n\n## 制作流程\n1. **剧本创作**：确定主题、编写剧情大纲\n2. **角色设计**：塑造鲜明的人物形象\n3. **拍摄准备**：场景布置、设备调试\n4. **实际拍摄**：镜头语言、表演指导\n5. **后期制作**：剪辑、配音、特效\n6. **发布推广**：平台选择、宣传策略\n\n## 实用技巧\n- 保持节奏紧凑，避免拖沓\n- 注重开头吸引力，前三秒决定留存率\n- 合理运用音乐和音效增强氛围\n- 结尾要有亮点，留下深刻印象\n\n希望本教程能帮助你开启短剧创作之旅！',
            'cover_image': 'https://images.unsplash.com/photo-1595769812725-4c6564f70466?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '新手入门',
            'level': '初级',
            'duration': '2小时',
            'tags': ['入门', '基础', '流程'],
            'is_free': True,
            'status': 'published'
        },
        {
            'title': '高级剪辑技巧',
            'content': '剪辑是视频制作的灵魂。掌握高级剪辑技巧，能让你的作品脱颖而出。\n\n## 核心概念\n### 1. 节奏控制\n- 快节奏剪辑适合动作、悬疑类内容\n- 慢节奏剪辑适合情感、文艺类内容\n- 节奏变化要服务于内容表达\n\n### 2. 转场艺术\n- 硬切：最常用的转场方式\n- 淡入淡出：表现时间流逝或场景转换\n- 匹配剪辑：通过相似元素连接不同场景\n- 跳跃剪辑：创造紧张感或表现心理活动\n\n### 3. 色彩校正\n- 统一画面色调，营造整体氛围\n- 使用LUTs快速调色\n- 根据内容情绪选择冷暖色调\n\n## 实战案例\n我们将通过一个具体的案例，演示如何运用这些技巧提升剪辑质量。\n\n## 工具推荐\n- Adobe Premiere Pro：专业级剪辑软件\n- DaVinci Resolve：强大的调色功能\n- Final Cut Pro：Mac平台优秀选择\n\n不断练习，你也能成为剪辑大师！',
            'cover_image': 'https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '进阶技巧',
            'level': '高级',
            'duration': '4小时',
            'tags': ['剪辑', '高级', '技巧'],
            'is_free': False,
            'status': 'published'
        },
        {
            'title': 'AI剧本生成实战',
            'content': '人工智能正在改变创作方式。本教程将教你如何利用AI工具高效生成高质量剧本。\n\n## AI剧本生成原理\n- 基于大语言模型的文本生成\n- 通过学习海量剧本数据掌握创作规律\n- 根据用户输入生成符合要求的剧本\n\n## 使用步骤\n1. **明确需求**：确定剧本类型、风格、长度\n2. **输入提示**：提供详细的人物设定、情节梗概\n3. **生成草稿**：AI根据提示生成剧本初稿\n4. **人工润色**：对AI生成的内容进行修改完善\n5. **最终定稿**：完成符合要求的剧本\n\n## 实用工具\n- ChatGPT：通用对话模型，适合多种题材\n- Claude：长文本处理能力强\n- 专门剧本生成工具：针对性更强\n\n## 注意事项\n- AI生成的内容需要人工审核和修改\n- 注意版权问题，避免侵权\n- 结合人类创意，发挥各自优势\n\n拥抱AI，让创作更高效！',
            'cover_image': 'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': 'AI创作',
            'level': '中级',
            'duration': '3小时',
            'tags': ['AI', '剧本', '生成'],
            'is_free': True,
            'status': 'published'
        }
    ]
    
    created_tutorials = []
    for sample in sample_tutorials:
        tutorial = Tutorial(
            title=sample['title'],
            content=sample['content'],
            cover_image=sample['cover_image'],
            category=sample['category'],
            level=sample['level'],
            duration=sample['duration'],
            tags=json.dumps(sample['tags']),
            is_free=sample['is_free'],
            status=sample['status'],
            author_id=author.id,
            views=1000 + len(created_tutorials) * 500,  # 模拟浏览量
            likes=50 + len(created_tutorials) * 20      # 模拟点赞数
        )
        db.session.add(tutorial)
        created_tutorials.append(tutorial)
    
    try:
        db.session.commit()
        # 重新查询已发布的教程
        tutorials = Tutorial.query.filter(Tutorial.status == 'published').order_by(Tutorial.views.desc()).limit(6).all()
        tutorial_list = []
        for tutorial in tutorials:
            tutorial_dict = tutorial.to_dict()
            tutorial_dict['description'] = tutorial.content[:100] + '...' if tutorial.content else ''
            tutorial_dict['cover'] = tutorial.cover_image or 'https://images.unsplash.com/photo-1595769812725-4c6564f70466?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80'
            if tutorial.views < 1000:
                students = f'{tutorial.views}'
            elif tutorial.views < 10000:
                students = f'{tutorial.views // 1000}千'
            else:
                students = f'{tutorial.views // 10000}万'
            tutorial_dict['students'] = students
            tutorial_dict['free'] = tutorial.is_free
            tutorial_list.append(tutorial_dict)
        return jsonify(tutorial_list)
    except Exception as e:
        db.session.rollback()
        print(f"创建示例教程失败: {e}")
        # 失败时返回模拟数据
        tutorials = [
            {
                'id': 1,
                'title': '短剧制作入门指南',
                'description': '从零开始学习短剧制作的基础知识和流程',
                'cover': 'https://images.unsplash.com/photo-1595769812725-4c6564f70466?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
                'level': '初级',
                'duration': '2小时',
                'students': '5.2万',
                'free': True
            },
            {
                'id': 2,
                'title': '高级剪辑技巧',
                'description': '掌握专业级的视频剪辑技巧和特效制作',
                'cover': 'https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
                'level': '高级',
                'duration': '4小时',
                'students': '3.8万',
                'free': False
            },
            {
                'id': 3,
                'title': 'AI剧本生成实战',
                'description': '利用AI工具快速生成高质量剧本的技巧',
                'cover': 'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
                'level': '中级',
                'duration': '3小时',
                'students': '4.5万',
                'free': True
            }
        ]
        return jsonify(tutorials)


@bp.route('/api/tutorials')
def get_tutorials():
    """获取教程列表"""
    category = request.args.get('category', '')
    level = request.args.get('level', '')
    status = request.args.get('status', 'published')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    query = Tutorial.query

    if category:
        query = query.filter(Tutorial.category == category)
    if level:
        query = query.filter(Tutorial.level == level)
    if status:
        query = query.filter(Tutorial.status == status)

    # 按创建时间倒序排列
    tutorials = query.order_by(Tutorial.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'tutorials': [tutorial.to_dict() for tutorial in tutorials.items],
        'pagination': {
            'page': tutorials.page,
            'per_page': tutorials.per_page,
            'total': tutorials.total,
            'pages': tutorials.pages
        }
    })


@bp.route('/api/tutorials/<int:tutorial_id>')
def get_tutorial(tutorial_id):
    """获取单个教程"""
    tutorial = Tutorial.query.get_or_404(tutorial_id)
    
    # 增加浏览量
    tutorial.views += 1
    db.session.commit()
    
    return jsonify(tutorial.to_dict())


@bp.route('/api/tutorials', methods=['POST'])
@login_required
def create_tutorial():
    """创建新教程"""
    data = request.get_json()
    
    if not data.get('title'):
        return jsonify({'error': '标题不能为空'}), 400
    
    tutorial = Tutorial(
        title=data.get('title'),
        content=data.get('content', ''),
        cover_image=data.get('cover_image'),
        category=data.get('category', '其他'),
        level=data.get('level', '初级'),
        duration=data.get('duration'),
        tags=json.dumps(data.get('tags', [])),
        status=data.get('status', 'draft'),
        is_free=data.get('is_free', True),
        author_id=current_user.id
    )
    
    try:
        db.session.add(tutorial)
        db.session.commit()
        return jsonify(tutorial.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/tutorials/<int:tutorial_id>', methods=['PUT'])
@login_required
def update_tutorial(tutorial_id):
    """更新教程"""
    tutorial = Tutorial.query.get_or_404(tutorial_id)
    
    # 检查权限：只有作者可以更新
    if tutorial.author_id != current_user.id:
        return jsonify({'error': '无权修改此教程'}), 403
    
    data = request.get_json()
    
    if 'title' in data:
        tutorial.title = data['title']
    if 'content' in data:
        tutorial.content = data['content']
    if 'cover_image' in data:
        tutorial.cover_image = data['cover_image']
    if 'category' in data:
        tutorial.category = data['category']
    if 'level' in data:
        tutorial.level = data['level']
    if 'duration' in data:
        tutorial.duration = data['duration']
    if 'tags' in data:
        tutorial.tags = json.dumps(data['tags'])
    if 'status' in data:
        tutorial.status = data['status']
    if 'is_free' in data:
        tutorial.is_free = data['is_free']
    
    tutorial.updated_at = datetime.utcnow()
    
    try:
        db.session.commit()
        return jsonify(tutorial.to_dict())
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/tutorials/<int:tutorial_id>', methods=['DELETE'])
@login_required
def delete_tutorial(tutorial_id):
    """删除教程"""
    tutorial = Tutorial.query.get_or_404(tutorial_id)
    
    # 检查权限：只有作者可以删除
    if tutorial.author_id != current_user.id:
        return jsonify({'error': '无权删除此教程'}), 403
    
    try:
        db.session.delete(tutorial)
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/settings/update-api-key', methods=['POST'])
@login_required
def update_api_key():
    """更新API密钥"""
    data = request.get_json()
    service = data.get('service')
    api_key = data.get('api_key')

    if not service or not api_key:
        return jsonify({'error': '缺少必要参数'}), 400

    try:
        if service == 'openai':
            current_user.openai_api_key = api_key
        elif service == 'stability':
            current_user.stability_api_key = api_key
        elif service == 'anthropic':
            current_user.anthropic_api_key = api_key
        elif service == 'deepseek':
            current_user.deepseek_api_key = api_key
        elif service == 'midjourney':
            current_user.midjourney_api_key = api_key
        elif service == 'unified_generator':
            # unified_generator需要保存URL和API Key
            unified_url = data.get('url', 'http://192.168.2.15:58888')
            current_user.unified_generator_url = unified_url
            current_user.unified_generator_api_key = api_key
        else:
            return jsonify({'error': '不支持的服务类型'}), 400

        db.session.commit()
        return jsonify({'success': True, 'message': 'API密钥更新成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/settings/test-api-key', methods=['POST'])
@login_required
def test_api_key():
    """测试API密钥"""
    data = request.get_json()
    service = data.get('service')
    api_key = data.get('api_key')

    if not service or not api_key:
        return jsonify({'error': '缺少必要参数'}), 400

    import time
    time.sleep(1)  # 模拟网络延迟

    # 返回模拟的测试结果
    return jsonify({
        'success': True,
        'valid': True,
        'message': 'API密钥验证成功',
        'credits': 1000,  # 模拟剩余额度
        'expires_at': '2024-12-31'  # 模拟过期时间
    })


@bp.route('/api/settings/image-generator-config', methods=['GET'])
@login_required
def get_image_generator_config():
    """获取图像生成器配置"""
    config = {
        'class_path': 'UnifiedGeneratorImageGenerator',
        'init_args': {
            'api_key': current_user.unified_generator_api_key if hasattr(current_user, 'unified_generator_api_key') else '',
            'base_url': current_user.unified_generator_url if hasattr(current_user, 'unified_generator_url') else 'http://192.168.2.15:58888',
            'model': 'black-forest-labs/FLUX.2-klein-4B'
        }
    }
    
    # 如果没有配置，返回空
    if not config['init_args']['api_key']:
        return jsonify({'config': None})
    
    return jsonify({'config': config})


@bp.route('/api/settings/export-data', methods=['GET'])
@login_required
def export_user_data():
    """导出用户数据"""
    try:
        # 收集用户数据
        user_data = {
            'user': current_user.to_dict(),
            'projects': [project.to_dict() for project in current_user.projects],
            'created_at': datetime.utcnow().isoformat()
        }

        # 创建数据文件
        import tempfile
        import zipfile
        import json

        # 创建临时文件
        temp_dir = tempfile.mkdtemp()
        data_file = os.path.join(temp_dir, 'user_data.json')

        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(user_data, f, ensure_ascii=False, indent=2)

        # 创建ZIP文件
        zip_file = os.path.join(temp_dir, 'user_data.zip')
        with zipfile.ZipFile(zip_file, 'w') as zipf:
            zipf.write(data_file, 'user_data.json')

        # 读取ZIP文件内容
        with open(zip_file, 'rb') as f:
            zip_data = f.read()

        # 清理临时文件
        import shutil
        shutil.rmtree(temp_dir)

        # 返回ZIP文件
        from flask import send_file
        import io

        return send_file(
            io.BytesIO(zip_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'lingxijuneng_data_export_{datetime.utcnow().date()}.zip'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/settings/account', methods=['PUT'])
@login_required
def update_account():
    """更新账户信息"""
    data = request.get_json()

    try:
        if 'username' in data and data['username'] != current_user.username:
            # 检查用户名是否已存在
            existing_user = User.query.filter_by(username=data['username']).first()
            if existing_user and existing_user.id != current_user.id:
                return jsonify({'error': '用户名已存在'}), 400
            current_user.username = data['username']

        if 'email' in data and data['email'] != current_user.email:
            # 检查邮箱是否已存在
            existing_user = User.query.filter_by(email=data['email']).first()
            if existing_user and existing_user.id != current_user.id:
                return jsonify({'error': '邮箱已存在'}), 400
            current_user.email = data['email']

        if 'bio' in data:
            current_user.bio = data['bio']

        db.session.commit()
        return jsonify({'success': True, 'message': '账户信息更新成功'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/settings/change-password', methods=['POST'])
@login_required
def change_password():
    """修改密码"""
    data = request.get_json()
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password:
        return jsonify({'error': '请提供当前密码和新密码'}), 400

    # 验证当前密码
    if not current_user.check_password(current_password):
        return jsonify({'error': '当前密码错误'}), 400

    # 设置新密码
    try:
        current_user.set_password(new_password)
        db.session.commit()
        return jsonify({'success': True, 'message': '密码修改成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/discover/tagged')
def get_tagged_dramas():
    """获取指定标签的短剧"""
    tag = request.args.get('tag', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    
    if not tag:
        return jsonify({'error': '请提供标签参数'}), 400
    
    # 模拟数据 - 在实际应用中，这里应该查询数据库
    # 根据标签返回相应的短剧数据
    all_dramas = [
        {
            'id': 1,
            'title': '时空恋人',
            'description': '穿越时空的爱情故事，感动千万观众',
            'cover': 'https://images.unsplash.com/photo-1536240478700-b869070f9279?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '爱情',
            'views': '120万',
            'likes': '5.6万',
            'author': '时光影视',
            'episodes': 15,
            'tags': ['穿越重生', '爱情', '古风']
        },
        {
            'id': 2,
            'title': '逆袭人生',
            'description': '从平凡到非凡的逆袭之路',
            'cover': 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '励志',
            'views': '98万',
            'likes': '4.8万',
            'author': '梦想工作室',
            'episodes': 12,
            'tags': ['逆袭', '励志', '现代都市']
        },
        {
            'id': 3,
            'title': '迷雾追踪',
            'description': '悬疑推理短剧，层层递进的剧情',
            'cover': 'https://images.unsplash.com/photo-1536440136628-849c177e76a1?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '悬疑',
            'views': '85万',
            'likes': '4.2万',
            'author': '悬疑剧场',
            'episodes': 10,
            'tags': ['悬疑推理', '侦探', '现代都市']
        },
        {
            'id': 4,
            'title': '甜宠时光',
            'description': '甜蜜宠爱的爱情故事',
            'cover': 'https://images.unsplash.com/photo-1511578314322-379afb476865?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '爱情',
            'views': '76万',
            'likes': '3.9万',
            'author': '甜蜜制作',
            'episodes': 8,
            'tags': ['甜宠', '爱情', '青春校园']
        },
        {
            'id': 5,
            'title': '星际穿越者',
            'description': '科幻冒险故事，探索未知宇宙',
            'cover': 'https://images.unsplash.com/photo-1446776653964-20c1d3a81b06?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '科幻',
            'views': '92万',
            'likes': '4.5万',
            'author': '科幻工厂',
            'episodes': 14,
            'tags': ['科幻未来', '冒险', '星际']
        },
        {
            'id': 6,
            'title': '职场精英',
            'description': '职场励志故事，奋斗与成长',
            'cover': 'https://images.unsplash.com/photo-1552664730-d307ca884978?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '职场',
            'views': '68万',
            'likes': '3.2万',
            'author': '职场频道',
            'episodes': 10,
            'tags': ['职场励志', '逆袭', '现代都市']
        }
    ]
    
    # 根据标签筛选短剧
    if tag == '穿越重生':
        filtered = [d for d in all_dramas if '穿越重生' in d.get('tags', [])]
    elif tag == '霸道总裁':
        filtered = [d for d in all_dramas if d['category'] == '爱情']
    elif tag == '甜宠':
        filtered = [d for d in all_dramas if '甜宠' in d.get('tags', [])]
    elif tag == '逆袭':
        filtered = [d for d in all_dramas if '逆袭' in d.get('tags', [])]
    elif tag == '悬疑推理':
        filtered = [d for d in all_dramas if '悬疑推理' in d.get('tags', [])]
    elif tag == '古风':
        filtered = [d for d in all_dramas if '古风' in d.get('tags', [])]
    elif tag == '现代都市':
        filtered = [d for d in all_dramas if '现代都市' in d.get('tags', [])]
    elif tag == '青春校园':
        filtered = [d for d in all_dramas if '青春校园' in d.get('tags', [])]
    elif tag == '科幻未来':
        filtered = [d for d in all_dramas if '科幻未来' in d.get('tags', [])]
    elif tag == '职场励志':
        filtered = [d for d in all_dramas if '职场励志' in d.get('tags', [])]
    elif tag == '家庭伦理':
        filtered = [d for d in all_dramas if d['category'] == '家庭']
    elif tag == '奇幻冒险':
        filtered = [d for d in all_dramas if '冒险' in d.get('tags', [])]
    else:
        filtered = all_dramas
    
    # 分页处理
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = filtered[start:end]
    
    return jsonify({
        'dramas': paginated,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page
        },
        'tag': tag
    })


@bp.route('/api/discover/category')
def get_category_dramas():
    """获取指定分类的短剧"""
    category = request.args.get('category', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    
    if not category:
        return jsonify({'error': '请提供分类参数'}), 400
    
    # 使用与上面相同的模拟数据
    all_dramas = [
        {
            'id': 1,
            'title': '时空恋人',
            'description': '穿越时空的爱情故事，感动千万观众',
            'cover': 'https://images.unsplash.com/photo-1536240478700-b869070f9279?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '爱情',
            'views': '120万',
            'likes': '5.6万',
            'author': '时光影视',
            'episodes': 15,
            'tags': ['穿越重生', '爱情', '古风']
        },
        {
            'id': 2,
            'title': '逆袭人生',
            'description': '从平凡到非凡的逆袭之路',
            'cover': 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '励志',
            'views': '98万',
            'likes': '4.8万',
            'author': '梦想工作室',
            'episodes': 12,
            'tags': ['逆袭', '励志', '现代都市']
        },
        {
            'id': 3,
            'title': '迷雾追踪',
            'description': '悬疑推理短剧，层层递进的剧情',
            'cover': 'https://images.unsplash.com/photo-1536440136628-849c177e76a1?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '悬疑',
            'views': '85万',
            'likes': '4.2万',
            'author': '悬疑剧场',
            'episodes': 10,
            'tags': ['悬疑推理', '侦探', '现代都市']
        },
        {
            'id': 4,
            'title': '甜宠时光',
            'description': '甜蜜宠爱的爱情故事',
            'cover': 'https://images.unsplash.com/photo-1511578314322-379afb476865?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '爱情',
            'views': '76万',
            'likes': '3.9万',
            'author': '甜蜜制作',
            'episodes': 8,
            'tags': ['甜宠', '爱情', '青春校园']
        },
        {
            'id': 5,
            'title': '星际穿越者',
            'description': '科幻冒险故事，探索未知宇宙',
            'cover': 'https://images.unsplash.com/photo-1446776653964-20c1d3a81b06?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '科幻',
            'views': '92万',
            'likes': '4.5万',
            'author': '科幻工厂',
            'episodes': 14,
            'tags': ['科幻未来', '冒险', '星际']
        },
        {
            'id': 6,
            'title': '职场精英',
            'description': '职场励志故事，奋斗与成长',
            'cover': 'https://images.unsplash.com/photo-1552664730-d307ca884978?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '职场',
            'views': '68万',
            'likes': '3.2万',
            'author': '职场频道',
            'episodes': 10,
            'tags': ['职场励志', '逆袭', '现代都市']
        }
    ]
    
    # 根据分类筛选短剧
    category_map = {
        '推荐': 'all',
        '热门': 'all',
        '最新': 'all',
        '精选': 'all',
        '爱情': '爱情',
        '悬疑': '悬疑',
        '喜剧': '喜剧',
        '古装': '古装',
        '科幻': '科幻',
        '都市': '现代都市',
        '校园': '青春校园'
    }
    
    category_key = category_map.get(category, 'all')
    
    if category_key == 'all':
        filtered = all_dramas
    else:
        filtered = [d for d in all_dramas if d['category'] == category_key]
    
    # 分页处理
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = filtered[start:end]
    
    return jsonify({
        'dramas': paginated,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page
        },
        'category': category
    })


@bp.route('/api/discover/search')
def search_dramas():
    """搜索短剧"""
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    
    if not query or len(query.strip()) < 2:
        return jsonify({'error': '请输入至少2个字符进行搜索'}), 400
    
    # 使用与上面相同的模拟数据
    all_dramas = [
        {
            'id': 1,
            'title': '时空恋人',
            'description': '穿越时空的爱情故事，感动千万观众',
            'cover': 'https://images.unsplash.com/photo-1536240478700-b869070f9279?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '爱情',
            'views': '120万',
            'likes': '5.6万',
            'author': '时光影视',
            'episodes': 15,
            'tags': ['穿越重生', '爱情', '古风']
        },
        {
            'id': 2,
            'title': '逆袭人生',
            'description': '从平凡到非凡的逆袭之路',
            'cover': 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '励志',
            'views': '98万',
            'likes': '4.8万',
            'author': '梦想工作室',
            'episodes': 12,
            'tags': ['逆袭', '励志', '现代都市']
        },
        {
            'id': 3,
            'title': '迷雾追踪',
            'description': '悬疑推理短剧，层层递进的剧情',
            'cover': 'https://images.unsplash.com/photo-1536440136628-849c177e76a1?ixlib=rb-4.0.3&auto=format&fit=crop&w=300&q=80',
            'category': '悬疑',
            'views': '85万',
            'likes': '4.2万',
            'author': '悬疑剧场',
            'episodes': 10,
            'tags': ['悬疑推理', '侦探', '现代都市']
        }
    ]
    
    # 简单搜索逻辑：在标题和描述中查找关键词
    query_lower = query.lower().strip()
    filtered = []
    
    for drama in all_dramas:
        title_match = query_lower in drama['title'].lower()
        desc_match = query_lower in drama['description'].lower()
        category_match = query_lower in drama['category'].lower()
        tag_match = any(query_lower in tag.lower() for tag in drama.get('tags', []))
        
        if title_match or desc_match or category_match or tag_match:
            filtered.append(drama)
    
    # 分页处理
    total = len(filtered)
    start = (page - 1) * per_page
    end = start + per_page
    paginated = filtered[start:end]
    
    return jsonify({
        'dramas': paginated,
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': total,
            'pages': (total + per_page - 1) // per_page
        },
        'query': query,
        'results_count': total
    })


@bp.route('/api/ai/generate', methods=['POST'])
def ai_generate():
    """AI生成内容"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
    
    gen_type = data.get('type', 'theme')
    prompt = data.get('prompt', '')
    category = data.get('category', '其他')
    title = data.get('title', '')
    
    # 模拟AI生成延迟
    import time
    time.sleep(1.5)
    
    # 根据类型和分类生成模拟内容
    options = []
    
    if gen_type == 'theme':
        if category == '爱情':
            options = [
                "跨越时空的命中注定的相遇，两个来自不同时代的灵魂在命运的安排下相知相爱",
                "青梅竹马时隔十年重逢，从误会到理解再到深深相爱的浪漫故事",
                "霸道总裁与倔强灰姑娘的职场爱情故事，在权力与真心的博弈中找到真爱"
            ]
        elif category == '悬疑':
            options = [
                "一桩看似普通的失踪案背后隐藏着惊天阴谋，侦探步步深入揭开真相",
                "完美犯罪的破绽往往藏在细节中，一场高智商的较量即将展开",
                "每个人都有秘密，当秘密被揭开时，谁才是真正的凶手"
            ]
        elif category == '科幻':
            options = [
                "未来世界中，人类与AI的边界逐渐模糊，一段关于自我认知的旅程",
                "穿越时空的冒险，改变过去还是接受现实，每一个选择都关乎命运",
                "末日废土上的生存之战，人性在极端环境下的考验与救赎"
            ]
        else:
            options = [
                "一个普通人意外获得超能力，在责任与欲望之间寻找平衡",
                "当梦想与现实碰撞，坚持还是妥协，这是每个人都要面对的选择",
                "一段跨越阶层的友谊，在世俗的偏见中开出最美的花"
            ]
    
    elif gen_type == 'description':
        if category == '爱情':
            options = [
                "本剧讲述了女主角在命运的安排下与男主角相遇，从相识到相知再到相爱的浪漫故事。剧中融入了现代都市的快节奏生活与细腻的情感描写，展现了当代年轻人对爱情的追求与困惑。",
                "一段跨越十年的爱情故事，从青涩的校园时代到成熟的职场生涯，两人在人生的不同阶段相遇、错过、重逢，最终在命运的安排下走到一起。",
                "霸道总裁与职场新人的爱情博弈，在职场与感情的双重压力下，两人如何从互相看不顺眼到深深相爱，展现了一段充满波折却又甜蜜的爱情故事。"
            ]
        elif category == '悬疑':
            options = [
                "一桩离奇的命案打破了小城的宁静，看似简单的案件背后却隐藏着错综复杂的利益纠葛。随着调查的深入，越来越多不为人知的秘密浮出水面...",
                "完美的不在场证明，精心设计的犯罪现场，凶手仿佛从未存在。但再完美的犯罪也终将留下痕迹，真相永远不会被完全掩盖。",
                "每个人都有自己的秘密，当这些秘密被一一揭开时，你会发现身边的人都不是你想象中的样子。在这场人性的博弈中，谁才是真正的赢家"
            ]
        else:
            options = [
                "这是一个关于成长与蜕变的故事。主人公在经历了种种挫折与磨难后，逐渐找到了自己的人生方向，实现了从平凡到非凡的转变。",
                "在快节奏的现代社会中，人们往往迷失了自我。本剧通过主人公的经历，探讨了如何在喧嚣的世界中保持初心，找到真正属于自己的生活方式。",
                "一段关于梦想与现实的碰撞。当理想遭遇现实的残酷打击，是坚持还是放弃？本剧给出了一个温暖而有力的答案。"
            ]
    
    elif gen_type == 'background':
        if category == '爱情':
            options = [
                "【时代背景】现代都市\n【地点】繁华的大都市，高档写字楼、咖啡厅、公园等\n【人物关系】男女主角因工作相识，从最初的误会到慢慢了解\n【核心冲突】身份地位的差距、前任的纠缠、家庭的反对\n【情感基调】浪漫温馨，偶尔有小虐但总体甜蜜",
                "【时代背景】架空古代\n【地点】繁华的京城，包含皇宫、市集、江湖等场所\n【人物关系】女主角是穿越而来的现代女孩，男主角是冷面王爷\n【核心冲突】两人来自不同时代的世界观碰撞、宫廷权力斗争\n【情感基调】先婚后爱，从互相看不顺眼到深深相爱",
                "【时代背景】大学校园\n【地点】美丽的大学校园，图书馆、操场、宿舍等\n【人物关系】男女主角是同班同学，从竞争对手到互相欣赏\n【核心冲突】学业压力、毕业抉择、异地恋的考验\n【情感基调】青春洋溢，充满朝气与希望"
            ]
        else:
            options = [
                "【时代背景】当代社会\n【地点】现代都市的各种场景\n【人物设定】多元化的角色群像，各自有着不同的人生轨迹\n【故事主线】通过一系列事件将不同人物的命运交织在一起\n【主题表达】探讨现代社会中的各种议题，引发观众思考",
                "【时代背景】近未来世界\n【地点】科技与自然环境并存的世界\n【人物设定】普通人在特殊环境下的生存与奋斗\n【故事主线】面对未知挑战时的选择与成长\n【主题表达】人性的光辉在困境中闪耀",
                "【时代背景】架空世界\n【地点】充满想象力的奇幻世界\n【人物设定】各具特色的角色，拥有不同的能力与背景\n【故事主线】冒险与探索，在旅途中发现自我与世界\n【主题表达】勇气、友情与成长的永恒主题"
            ]
    
    elif gen_type == 'all':
        options = [
            f"主题：从平凡到非凡的逆袭之路，讲述一个普通人不甘平庸，通过努力奋斗最终实现人生价值的励志故事。\n\n描述：主人公原本是一个平凡的上班族，生活平淡无奇。一次偶然的机会，他发现了自己隐藏的才能，并决定勇敢追求梦想。在经历了重重困难与挫折后，他终于在事业上取得了突破，同时也收获了真挚的爱情与友情。\n\n背景：故事发生在现代都市，展现了当代年轻人的生活状态与价值追求。通过主人公的成长历程，传达了坚持梦想、永不放弃的人生态度。",
            f"主题：跨越时空的命中注定，两个灵魂在不同时空相遇相知，用爱跨越一切障碍。\n\n描述：女主角意外穿越到古代，遇到了冷面王爷男主角。两人在相处中从互相看不顺眼到渐生情愫，共同经历了宫廷斗争、江湖险恶等种种考验。最终，他们不仅收获了爱情，还找到了回到现代的方法，但两人必须做出艰难的选择。\n\n背景：故事融合了古代宫廷与现代都市两个时空，展现了不同时代的文化碰撞与融合。通过两位主角的爱情故事，探讨了爱情的真谛与命运的选择。",
            f"主题：真相只有一个，在迷雾重重的案件中寻找真相，揭开层层伪装。\n\n描述：一桩看似普通的意外死亡案件，却牵扯出一系列不为人知的秘密。侦探通过细致的观察与缜密的推理，逐渐拼凑出事件的全貌。在追查真相的过程中，他发现每个人都可能是嫌疑人，而真相远比想象中更加复杂。\n\n背景：故事发生在一个表面平静的小城，暗流涌动的社会关系构成了复杂的案件背景。通过推理过程展现人性的多面性，探讨正义与真相的价值。"
        ]
    
    else:
        options = [
            "根据您的需求，AI为您生成了这个创意方案。这是一个充满想象力的设定，可以进一步发展出精彩的故事情节。",
            "这是一个独特而有趣的创意，融合了多种元素，具有很强的可看性和话题性。建议可以在人物塑造上再多下功夫。",
            "AI基于您的输入生成了这个方案，整体构思新颖，结构完整。可以根据实际需求进行调整和优化。"
        ]
    
    return jsonify({
        'success': True,
        'data': {
            'type': gen_type,
            'options': options,
            'generated_at': datetime.utcnow().isoformat()
        }
    })


@bp.route('/api/ai/generate-field', methods=['POST'])
def ai_generate_field():
    """AI生成单个字段内容（主题、描述、背景）
    
    依赖关系：
    - 主题(theme): 依赖项目标题(title)
    - 项目描述(description): 依赖主题(theme)和项目标题(title)
    - 内容背景(background): 依赖项目描述(description)、主题(theme)和项目标题(title)
    """
    from api_services.deepseek_api import get_deepseek_client
    
    data = request.get_json()
    
    logger.info(f"=== AI生成字段请求 ===")
    logger.info(f"请求数据: {data}")
    
    if not data:
        logger.warning("请求数据为空")
        return jsonify({'success': False, 'error': '请求数据不能为空'}), 400
    
    title = data.get('title', '').strip()
    field = data.get('field', 'theme')
    category = data.get('category', '其他')
    theme = data.get('theme', '').strip()
    description = data.get('description', '').strip()
    
    logger.info(f"field={field}, title={title}, category={category}, theme={theme[:50] if theme else ''}, description={description[:50] if description else ''}")
    
    if not title and field != 'background':
        logger.warning("项目标题为空")
        return jsonify({'success': False, 'error': '项目标题不能为空'}), 400
    
    # 验证依赖字段
    if field == 'description' and not theme:
        logger.warning("生成描述但没有主题")
        return jsonify({'success': False, 'error': '生成描述前请先填写主题'}), 400
    
    if field == 'background' and not description:
        logger.warning("生成背景但没有描述")
        return jsonify({'success': False, 'error': '生成背景前请先填写项目描述'}), 400
    
    # 获取DeepSeek客户端
    client = get_deepseek_client()
    if not client:
        logger.error("DeepSeek客户端获取失败")
        return jsonify({'success': False, 'error': 'AI服务暂不可用，请稍后再试'}), 500
    
    try:
        # 调用AI生成
        logger.info(f"开始调用AI生成 field={field}")
        result = client.generate_field_content(
            field=field,
            title=title,
            category=category,
            theme=theme,
            description=description
        )
        
        logger.info(f"AI返回结果: {result}")
        
        if result.get('success'):
            data_result = result.get('data', [])
            logger.info(f"返回数据长度: {len(data_result)}, 数据类型: {type(data_result)}, 数据内容: {data_result}")
            return jsonify({
                'success': True,
                'content': data_result,
                'generated_count': len(data_result)
            })
        else:
            logger.error(f"AI生成失败: {result.get('error')}")
            return jsonify({
                'success': False,
                'error': result.get('error', 'AI生成失败')
            }), 500
            
    except Exception as e:
        logger.exception(f"AI生成异常: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'生成失败: {str(e)}'
        }), 500