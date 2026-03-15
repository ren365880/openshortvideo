# routes/projects.py - 项目管理路由
from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required, current_user
from __init__ import db, bcrypt  # 修改这里
from models import Project, Episode, Character
from api_services.deepseek_api import get_deepseek_client
from services.log_service import log_user_action, log_error, log_operation
from werkzeug.utils import secure_filename
import json
from datetime import datetime
import os
import logging
import sys

bp = Blueprint('projects', __name__)
# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('ai_generate_field')


def parse_episodes_from_markdown(text, count=3):
    """从markdown格式的文本中解析分集信息"""
    import re
    
    episodes = []
    
    # 匹配 ## 第X集 或 ## 第X章 格式
    episode_pattern = re.compile(r'##\s*(?:第[一二三四五六七八九十\d]+集|第[一二三四五六七八九十\d]+章)\s*[:：]?\s*(.+?)(?=\n##|\Z)', re.DOTALL)
    matches = episode_pattern.findall(text)
    
    logger.info(f"找到{len(matches)}个分集标题")
    
    for i, match in enumerate(matches[:count]):
        # 取第一行作为标题（去掉markdown格式符号）
        title_lines = match.strip().split('\n')
        title = title_lines[0].strip() if title_lines else f'第{i+1}集'
        title = re.sub(r'^\*+|#+\s*', '', title)  # 去掉*和#开头
        
        # 提取剧情梗概
        summary_match = re.search(r'剧情梗概[：:]\s*(.+?)(?=主要场景设定|场景设定|关键情节点|$)', match, re.DOTALL)
        summary = summary_match.group(1).strip() if summary_match else ''
        summary = re.sub(r'\*+', '', summary)  # 去掉**等
        
        # 提取场景设定
        scenes_match = re.search(r'(?:主要场景设定|场景设定)[：:]\s*(.+?)(?=关键情节点|$)', match, re.DOTALL)
        scenes = scenes_match.group(1).strip() if scenes_match else ''
        
        # 提取关键情节点
        key_points_match = re.search(r'关键情节点[：:]\s*(.+?)$', match, re.DOTALL)
        key_points = key_points_match.group(1).strip() if key_points_match else ''
        
        episodes.append({
            'title': title[:100] if title else f'第{i+1}集',
            'summary': summary[:500] if summary else '',
            'scenes': scenes[:500] if scenes else '',
            'key_points': key_points[:500] if key_points else ''
        })
        logger.info(f"分集{i+1}: {episodes[-1]['title']}")
    
    return episodes


def parse_characters_from_markdown(text, count=4):
    """从markdown格式的文本中解析角色信息"""
    import re
    
    characters = []
    
    # 匹配 ## 序号. 角色名 或 ## 角色名 格式
    char_pattern = re.compile(r'(?:^|\n)##\s*\.?\s*(.+?)(?=\n##|\Z)', re.DOTALL)
    matches = char_pattern.findall(text)
    
    logger.info(f"找到{len(matches)}个角色")
    
    for i, match in enumerate(matches[:count]):
        name_match = re.search(r'([^\n\-]+)', match)
        name = name_match.group(1).strip() if name_match else f'角色{i+1}'
        
        # 提取各种字段
        gender_match = re.search(r'[*-]\s*gender[*:]\s*([^\n]+)', match)
        gender = gender_match.group(1).strip() if gender_match else '不限'
        
        age_match = re.search(r'[*-]\s*age[*:]\s*([^\n]+)', match)
        age = age_match.group(1).strip() if age_match else ''
        
        role_match = re.search(r'[*-]\s*role[*:]\s*([^\n]+)', match)
        role = role_match.group(1).strip() if role_match else '配角'
        
        personality_match = re.search(r'[*-]\s*personality[*:]\s*([^\n]+)', match, re.DOTALL)
        personality = personality_match.group(1).strip() if personality_match else ''
        
        appearance_match = re.search(r'[*-]\s*appearance[*:]\s*([^\n]+)', match, re.DOTALL)
        appearance = appearance_match.group(1).strip() if appearance_match else ''
        
        background_match = re.search(r'[*-]\s*background[*:]\s*([^\n]+)', match, re.DOTALL)
        background = background_match.group(1).strip() if background_match else ''
        
        function_match = re.search(r'[*-]\s*function[*:]\s*([^\n]+)', match, re.DOTALL)
        function = function_match.group(1).strip() if function_match else ''
        
        characters.append({
            'name': name[:50] if name else f'角色{i+1}',
            'gender': gender[:20] if gender else '不限',
            'age': age[:20] if age else '',
            'role': role[:30] if role else '配角',
            'personality': personality[:200] if personality else '',
            'appearance': appearance[:200] if appearance else '',
            'background': background[:300] if background else '',
            'function': function[:200] if function else ''
        })
        logger.info(f"角色{i+1}: {characters[-1]['name']}")
    
    return characters

def generate_initial_episodes(project, count, episode_type='empty'):
    """根据项目信息自动生成初始分集"""
    # 获取项目标签
    tags = []
    if project.tags:
        try:
            tags = json.loads(project.tags)
        except:
            tags = []
    
    # 根据分类和主题生成不同的分集内容模板
    episode_templates = {
        '爱情': [
            {'title': '初次相遇', 'content': '男女主角在一次偶然的机会下相遇，命运的齿轮开始转动...'},
            {'title': '渐生好感', 'content': '随着接触的增多，两人之间产生了微妙的情愫...'},
            {'title': '误会重重', 'content': '第三者的介入让两人之间产生了误会，关系陷入僵局...'},
            {'title': '真相大白', 'content': '误会终于解开，两人坦诚相对，感情更加深厚...'},
            {'title': '甜蜜告白', 'content': '在浪漫的氛围中，一方终于鼓起勇气表白...'},
            {'title': '共度难关', 'content': '面对外界的压力和挑战，两人携手共渡难关...'},
            {'title': '家庭阻力', 'content': '双方家庭的反对成为新的考验...'},
            {'title': '坚持真爱', 'content': '面对重重阻力，两人依然坚守对彼此的爱...'},
            {'title': '终成眷属', 'content': '历经磨难，两人终于获得了所有人的祝福...'},
            {'title': '幸福结局', 'content': '故事在温馨幸福的氛围中画上完美句号...'}
        ],
        '悬疑': [
            {'title': '离奇案件', 'content': '一桩离奇的案件发生，所有线索都指向一个谜团...'},
            {'title': '展开调查', 'content': '主角开始调查，发现案件背后隐藏着更大的秘密...'},
            {'title': '嫌疑人出现', 'content': '多位嫌疑人浮出水面，每个人都有作案动机...'},
            {'title': '证据缺失', 'content': '关键证据的缺失让调查陷入困境...'},
            {'title': '意外发现', 'content': '一个意外的发现让案情出现转机...'},
            {'title': '真凶现身', 'content': '经过缜密的推理，真凶的身份逐渐明朗...'},
            {'title': '生死对决', 'content': '主角与真凶展开惊心动魄的对决...'},
            {'title': '真相大白', 'content': '案件的真相终于水落石出...'},
            {'title': '幕后黑手', 'content': '然而真正的幕后黑手才刚刚浮出水面...'},
            {'title': '正义必胜', 'content': '最终正义战胜邪恶，罪恶得到惩罚...'}
        ],
        '喜剧': [
            {'title': '乌龙事件', 'content': '一系列令人啼笑皆非的乌龙事件接连发生...'},
            {'title': '误会连连', 'content': '主角们因为各种误会陷入尴尬境地...'},
            {'title': '搞笑桥段', 'content': '荒诞搞笑的情节让人捧腹大笑...'},
            {'title': '糗事百出', 'content': '主角们的糗事接连不断，笑料百出...'},
            {'title': '阴差阳错', 'content': '阴差阳错间，事情朝着意想不到的方向发展...'},
            {'title': '意外之喜', 'content': '一系列的意外最终带来了意想不到的好结果...'},
            {'title': '欢乐时刻', 'content': '众人欢聚一堂，共享欢乐时光...'},
            {'title': '搞笑对决', 'content': '主角们展开一场搞笑的对决...'},
            {'title': '圆满解决', 'content': '所有问题在笑声中得到圆满解决...'},
            {'title': '欢乐结局', 'content': '故事在欢声笑语中画上圆满句号...'}
        ],
        '默认': [
            {'title': '故事开端', 'content': '故事从这里开始，主人公踏上了未知的旅程...'},
            {'title': '遭遇挑战', 'content': '面对突如其来的挑战，主人公必须做出选择...'},
            {'title': '结识伙伴', 'content': '在旅途中结识了志同道合的伙伴...'},
            {'title': '困难重重', 'content': '前进的道路上困难重重，考验着每个人的意志...'},
            {'title': '成长蜕变', 'content': '历经磨难，主人公逐渐成长蜕变...'},
            {'title': '突破困境', 'content': '终于找到了突破困境的方法...'},
            {'title': '新的危机', 'content': '新的挑战再次出现，情况变得更加复杂...'},
            {'title': '团结一致', 'content': '众人团结一致，共同面对新的挑战...'},
            {'title': '最终对决', 'content': '与最终boss展开惊心动魄的对决...'},
            {'title': '完美结局', 'content': '故事迎来了完美的结局，所有人都获得了幸福...'}
        ]
    }
    
    # 根据项目分类选择合适的模板
    templates = episode_templates.get(project.category, episode_templates['默认'])
    
    # 创建分集
    episodes_to_add = []
    for i in range(1, min(count + 1, len(templates) + 1)):
        template = templates[i - 1] if i <= len(templates) else episode_templates['默认'][i - 1]
        
        if episode_type == 'empty':
            # 空白分集
            episode = Episode(
                title=f'第{i}集',
                episode_number=i,
                content='',
                status='draft',
                project_id=project.id
            )
        elif episode_type == 'outline':
            # 大纲分集
            episode = Episode(
                title=template['title'],
                episode_number=i,
                content=f"【大纲】\n{template['content']}\n\n主要情节：\n- 场景设定\n- 人物出场\n- 关键事件",
                status='draft',
                project_id=project.id
            )
        else:  # detailed
            # 详细分集
            episode = Episode(
                title=template['title'],
                episode_number=i,
                content=f"【场景一】\n地点：\n人物：\n对白：\n\n【场景二】\n地点：\n人物：\n对白：\n\n{template['content']}",
                status='draft',
                project_id=project.id
            )
        
        episodes_to_add.append(episode)
    
    # 批量添加分集
    for episode in episodes_to_add:
        db.session.add(episode)
    
    # 更新项目的总集数
    project.total_episodes = Episode.query.filter_by(project_id=project.id).count()


def generate_initial_characters(project, count=4):
    """根据项目信息自动生成初始角色（模板版本）"""
    import random
    
    colors = ['#4F46E5', '#EC4899', '#10B981', '#F59E0B', '#8B5CF6', '#EF4444', '#06B6D4', '#84CC16']
    
    role_templates = [
        {'name': '主角', 'role': '主角', 'gender': '不限', 'age': '25岁', 'personality': '勇敢、正义', 'description': '故事的核心人物'},
        {'name': '女主角', 'role': '女主', 'gender': '女', 'age': '24岁', 'personality': '聪明、善良', 'description': '故事的核心人物'},
        {'name': '男主角', 'role': '男主', 'gender': '男', 'age': '26岁', 'personality': '成熟、稳重', 'description': '故事的核心人物'},
        {'name': '反派', 'role': '反派', 'gender': '男', 'age': '35岁', 'personality': '阴险、狡诈', 'description': '故事的对立角色'},
        {'name': '配角A', 'role': '配角', 'gender': '女', 'age': '28岁', 'personality': '热情、开朗', 'description': '故事的辅助角色'},
        {'name': '配角B', 'role': '配角', 'gender': '男', 'age': '30岁', 'personality': '稳重、可靠', 'description': '故事的辅助角色'},
    ]
    
    for i, template in enumerate(role_templates[:count]):
        color = random.choice(colors)
        colors.remove(color)
        
        character = Character(
            name=template['name'],
            role=template['role'],
            gender=template['gender'],
            age=template['age'],
            personality=template['personality'],
            description=template['description'],
            color=color,
            project_id=project.id
        )
        db.session.add(character)
    
    db.session.commit()


def generate_initial_episodes_ai(project, count, episode_type='outline'):
    """使用AI根据项目信息自动生成初始分集"""
    from api_services.deepseek_api import get_deepseek_client
    
    logger.info(f"=== AI生成初始分集 for project {project.id} ===")
    
    # 获取DeepSeek客户端
    client = get_deepseek_client()
    if not client:
        logger.warning("DeepSeek客户端不可用，使用默认模板生成")
        return generate_initial_episodes(project, count, episode_type)
    
    try:
        # 构建提示词
        prompt = f"""
项目信息：
- 标题：{project.title}
- 分类：{project.category}
- 主题：{project.theme}
- 描述：{project.description}
- 背景：{project.background}

请为这个项目生成分集大纲。需要{count}集，每集需要包含：
1. 集标题（简洁有力）
2. 剧情梗概（100-150字，包含起承转合）
3. 主要场景设定
4. 关键情节点

要求：
1. 每集剧情要有连贯性和递进关系
2. 紧扣项目主题和风格
3. 剧情要有人物成长和冲突
4. 每集结尾要留有悬念或过渡
"""
        
        result = client.generate_field_content(
            field='episodes',
            title=project.title,
            category=project.category,
            theme=project.theme,
            description=project.description,
            user_input=prompt,
            count=count,
            project_id=project.id
        )
        
        if not result.get('success'):
            logger.error(f"AI生成失败: {result.get('error')}")
            return generate_initial_episodes(project, count, episode_type)
        
        episodes_data = result.get('data', {})
        logger.info(f"AI返回数据类型: {type(episodes_data)}")
        logger.info(f"AI返回数据长度: {len(episodes_data) if isinstance(episodes_data, (list, dict)) else 'N/A'}")
        
        # 解析返回的分集数据
        if isinstance(episodes_data, dict) and 'episodes' in episodes_data:
            episode_list = episodes_data['episodes']
            logger.info("从dict中提取episodes字段")
        elif isinstance(episodes_data, list):
            episode_list = episodes_data
            logger.info("直接使用list")
        else:
            logger.warning(f"AI返回数据格式不正确: {type(episodes_data)}, 数据: {str(episodes_data)[:200]}")
            # 尝试从markdown格式中提取分集信息
            if isinstance(episodes_data, list) and len(episodes_data) > 0:
                raw_text = episodes_data[0] if isinstance(episodes_data[0], str) else str(episodes_data[0])
                logger.info(f"尝试从markdown解析，原始文本前200字符: {raw_text[:200]}")
                episode_list = parse_episodes_from_markdown(raw_text, count)
                if episode_list:
                    logger.info(f"从markdown成功解析出{len(episode_list)}个分集")
                else:
                    return generate_initial_episodes(project, count, episode_type)
            else:
                return generate_initial_episodes(project, count, episode_type)
        
        # 检查分集列表是否有效
        if not episode_list or len(episode_list) == 0:
            logger.warning("AI返回分集列表为空，使用默认模板")
            return generate_initial_episodes(project, count, episode_type)
        
        # 尝试解析每个分集数据，跳过无效项
        valid_episodes = []
        for ep_data in episode_list:
            # 如果是字符串，尝试解析为JSON
            if isinstance(ep_data, str):
                try:
                    ep_data = json.loads(ep_data)
                except:
                    logger.warning(f"无法解析分集数据: {ep_data[:50]}...")
                    continue
            
            # 确保是字典类型
            if not isinstance(ep_data, dict):
                logger.warning(f"分集数据不是字典: {ep_data}")
                continue
            
            valid_episodes.append(ep_data)
        
        if not valid_episodes:
            logger.warning("没有有效的分集数据，使用默认模板")
            return generate_initial_episodes(project, count, episode_type)
        
        episode_list = valid_episodes
        
        logger.info(f"有效分集数量: {len(episode_list)}")
        
        # 创建分集
        for i, ep_data in enumerate(episode_list[:count], 1):
            if episode_type == 'empty':
                content = ''
            elif episode_type == 'outline':
                content = f"""【大纲】
{ep_data.get('summary', '')}

【场景设定】
{ep_data.get('scenes', '')}

【关键情节点】
{ep_data.get('key_points', '')}"""
            else:  # detailed
                content = f"""【剧情梗概】
{ep_data.get('summary', '')}

【场景设定】
{ep_data.get('scenes', '')}

【关键情节点】
{ep_data.get('key_points', '')}

【详细对白】
（待填写）"""

            episode = Episode(
                title=ep_data.get('title', f'第{i}集'),
                episode_number=i,
                content=content,
                status='draft',
                project_id=project.id
            )
            db.session.add(episode)
        
        logger.info(f"AI生成了 {len(episode_list[:count])} 集")
        return True
        
    except Exception as e:
        logger.error(f"AI生成分集异常: {str(e)}")
        return generate_initial_episodes(project, count, episode_type)


def generate_initial_characters_ai(project, count=4):
    """使用AI根据项目信息自动生成角色，包含角色图像生成"""
    from api_services.deepseek_api import get_deepseek_client
    from services.image_generation_service import get_image_generator, generate_character_image
    import asyncio
    
    logger.info(f"=== AI生成初始角色 for project {project.id} ===")
    
    # 获取DeepSeek客户端
    client = get_deepseek_client()
    if not client:
        logger.warning("DeepSeek客户端不可用，使用默认模板生成")
        return generate_initial_characters(project)
    
    try:
        user_input = f"""
项目信息：
- 标题：{project.title}
- 分类：{project.category}
- 主题：{project.theme}
- 描述：{project.description}
- 背景：{project.background}

请为这个项目生成{count}个主要角色。每个角色需要包含：
1. name: 姓名
2. gender: 性别（男/女）
3. age: 年龄
4. role: 角色定位（主角/配角/反派等）
5. personality: 性格特点
6. appearance: 外貌描述（用于AI绘画，简洁具体）
7. background: 背景故事
8. function: 在故事中的作用

注意：appearance字段要简洁具体，适合AI图像生成。
"""
        
        result = client.generate_field_content(
            field='characters',
            title=project.title,
            category=project.category,
            theme=project.theme,
            description=project.description,
            user_input=user_input,
            count=count,
            project_id=project.id
        )
        
        if not result.get('success'):
            logger.error(f"AI生成角色失败: {result.get('error')}")
            return generate_initial_characters(project)
        
        characters_data = result.get('data', {})
        logger.info(f"AI返回角色数据类型: {type(characters_data)}")
        logger.info(f"AI返回角色数据长度: {len(characters_data) if isinstance(characters_data, (list, dict)) else 'N/A'}")
        
        # 解析返回的角色数据
        if isinstance(characters_data, dict) and 'characters' in characters_data:
            character_list = characters_data['characters']
            logger.info("从dict中提取characters字段")
        elif isinstance(characters_data, list):
            character_list = characters_data
            logger.info("直接使用list")
        else:
            logger.warning(f"AI返回角色数据格式不正确: {type(characters_data)}, 数据: {str(characters_data)[:200]}")
            # 尝试从markdown格式中解析角色信息
            if isinstance(characters_data, list) and len(characters_data) > 0:
                raw_text = characters_data[0] if isinstance(characters_data[0], str) else str(characters_data[0])
                logger.info(f"尝试从markdown解析角色，原始文本前200字符: {raw_text[:200]}")
                character_list = parse_characters_from_markdown(raw_text, count)
                if character_list:
                    logger.info(f"从markdown成功解析出{len(character_list)}个角色")
                else:
                    return generate_initial_characters(project)
            else:
                return generate_initial_characters(project)
        
        # 尝试解析每个角色数据，跳过无效项
        valid_characters = []
        for char_data in character_list:
            # 如果是字符串，尝试解析为JSON
            if isinstance(char_data, str):
                try:
                    char_data = json.loads(char_data)
                except:
                    # 如果解析失败，跳过这个条目
                    logger.warning(f"无法解析角色数据: {char_data[:50]}...")
                    continue
            
            # 确保是字典类型
            if not isinstance(char_data, dict):
                logger.warning(f"角色数据不是字典: {char_data}")
                continue
            
            # 检查必要字段
            if not char_data.get('name'):
                logger.warning("角色数据缺少name字段")
                continue
                
            valid_characters.append(char_data)
        
        if not valid_characters:
            logger.warning("没有有效的角色数据，使用默认模板")
            return generate_initial_characters(project)
        
        character_list = valid_characters
        
        # 获取图像生成器配置
        from services.model_config_service import get_episode_model_config
        model_config = get_episode_model_config(project.id)
        image_gen_config = None
        if model_config and model_config.get('image_generator'):
            image_gen_config = model_config.get('image_generator')
        
        # 检查用户是否配置了本地UnifiedGenerator，优先使用用户设置
        from flask_login import current_user
        if hasattr(current_user, 'unified_generator_api_key') and current_user.unified_generator_api_key:
            image_gen_config = {
                'class_path': 'UnifiedGeneratorImageGenerator',
                'init_args': {
                    'api_key': current_user.unified_generator_api_key,
                    'base_url': current_user.unified_generator_url if hasattr(current_user, 'unified_generator_url') else 'http://192.168.2.15:58888',
                    'model': 'black-forest-labs/FLUX.2-klein-4B'
                }
            }
        
        # 创建角色目录
        import os
        character_dir = os.path.join('uploads', 'characters', str(project.id))
        os.makedirs(character_dir, exist_ok=True)
        
        # 创建角色
        created_count = 0
        for char_data in character_list[:count]:
            # 随机颜色
            import random
            colors = ['#4F46E5', '#EC4899', '#10B981', '#F59E0B', '#8B5CF6', '#EF4444', '#06B6D4', '#84CC16']
            color = char_data.get('color') or random.choice(colors)
            
            character = Character(
                name=char_data.get('name', '未命名角色'),
                role=char_data.get('role', '配角'),
                gender=char_data.get('gender', '不限'),
                age=char_data.get('age', ''),
                description=char_data.get('background', ''),
                personality=char_data.get('personality', ''),
                color=color,
                project_id=project.id
            )
            # 尝试设置appearance和function字段
            if hasattr(character, 'appearance'):
                character.appearance = char_data.get('appearance', '')
            if hasattr(character, 'function'):
                character.function = char_data.get('function', '')
            db.session.add(character)
            db.session.flush()
            
            # 生成角色三张图像（正面、背面、侧面）
            appearance = char_data.get('appearance', '')
            if appearance and image_gen_config:
                try:
                    # 创建角色专属目录
                    character_dir = os.path.join('uploads', 'characters', str(project.id), str(character.id))
                    os.makedirs(character_dir, exist_ok=True)
                    
                    logger.info(f"=== 开始为角色 {character.name} 生成图像 ===")
                    logger.info(f"图像生成配置: {image_gen_config}")
                    
                    # 1. 生成正面图像
                    logger.info(f"[{character.name}] 正在生成正面图像...")
                    front_prompt = f"{project.title}角色，{appearance}，高质量，写实风格，正面半身照"
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    front_image_path = loop.run_until_complete(
                        generate_character_image(
                            character_prompt=front_prompt,
                            generator_config=image_gen_config,
                            output_dir=character_dir,
                            image_type='front'
                        )
                    )
                    
                    if front_image_path and os.path.exists(front_image_path):
                        character.avatar_front = os.path.basename(front_image_path)
                        character.avatar = os.path.basename(front_image_path)  # 兼容旧字段
                        logger.info(f"[{character.name}] 正面图像生成成功: {front_image_path}")
                    else:
                        logger.warning(f"[{character.name}] 正面图像生成失败")
                    
                    # 获取正面图像路径作为背面和侧面的参考
                    front_reference = os.path.join(character_dir, character.avatar_front) if character.avatar_front else None
                    
                    # 2. 生成背面图像（使用正面作为参考）
                    logger.info(f"[{character.name}] 正在生成背面图像...")
                    back_prompt = f"背面半身照，看不到脸部特征"
                    
                    back_image_path = loop.run_until_complete(
                        generate_character_image(
                            character_prompt=back_prompt,
                            generator_config=image_gen_config,
                            output_dir=character_dir,
                            reference_image=front_reference,
                            image_type='back'
                        )
                    )
                    
                    if back_image_path and os.path.exists(back_image_path):
                        character.avatar_back = os.path.basename(back_image_path)
                        logger.info(f"[{character.name}] 背面图像生成成功: {back_image_path}")
                    else:
                        logger.warning(f"[{character.name}] 背面图像生成失败")
                    
                    # 3. 生成侧面图像（使用正面作为参考）
                    logger.info(f"[{character.name}] 正在生成侧面图像...")
                    side_prompt = f"3/4侧面半身照"
                    
                    side_image_path = loop.run_until_complete(
                        generate_character_image(
                            character_prompt=side_prompt,
                            generator_config=image_gen_config,
                            output_dir=character_dir,
                            reference_image=front_reference,
                            image_type='side'
                        )
                    )
                    
                    if side_image_path and os.path.exists(side_image_path):
                        character.avatar_side = os.path.basename(side_image_path)
                        logger.info(f"[{character.name}] 侧面图像生成成功: {side_image_path}")
                    else:
                        logger.warning(f"[{character.name}] 侧面图像生成失败")
                    
                    loop.close()
                    
                    logger.info(f"=== 角色 {character.name} 图像全部生成完成 ===")
                    logger.info(f"正面: {character.avatar_front}, 背面: {character.avatar_back}, 侧面: {character.avatar_side}")
                        
                except Exception as img_err:
                    logger.error(f"角色图像生成异常: {str(img_err)}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            created_count += 1
        
        logger.info(f"AI生成了 {created_count} 个角色")
        return True
        
    except Exception as e:
        logger.error(f"AI生成角色异常: {str(e)}")
        return generate_initial_characters(project)
    # 根据分类生成不同的角色
    character_templates = {
        '爱情': [
            {'name': '男主角', 'role': '主角', 'gender': '男', 'description': '温柔体贴的男主角', 'color': '#4F46E5'},
            {'name': '女主角', 'role': '主角', 'gender': '女', 'description': '善良坚强的女主角', 'color': '#EC4899'},
            {'name': '闺蜜', 'role': '配角', 'gender': '女', 'description': '女主角的好朋友', 'color': '#8B5CF6'},
            {'name': '情敌', 'role': '反派', 'gender': '不限', 'description': '与主角竞争爱情的人', 'color': '#EF4444'}
        ],
        '悬疑': [
            {'name': '侦探', 'role': '主角', 'gender': '不限', 'description': '聪明机智的侦探', 'color': '#4F46E5'},
            {'name': '助手', 'role': '配角', 'gender': '不限', 'description': '侦探的得力助手', 'color': '#10B981'},
            {'name': '嫌疑人', 'role': '配角', 'gender': '不限', 'description': '案件的嫌疑人', 'color': '#F59E0B'},
            {'name': '真凶', 'role': '反派', 'gender': '不限', 'description': '案件的真凶', 'color': '#EF4444'}
        ],
        '喜剧': [
            {'name': '搞笑担当', 'role': '主角', 'gender': '不限', 'description': '负责制造笑料的主角', 'color': '#F59E0B'},
            {'name': '捧哏', 'role': '配角', 'gender': '不限', 'description': '配合搞笑的角色', 'color': '#10B981'},
            {'name': '倒霉蛋', 'role': '配角', 'gender': '不限', 'description': '总是遇到倒霉事的角色', 'color': '#8B5CF6'},
            {'name': '吐槽役', 'role': '配角', 'gender': '不限', 'description': '负责吐槽的角色', 'color': '#EC4899'}
        ],
        '默认': [
            {'name': '主角A', 'role': '主角', 'gender': '不限', 'description': '故事的核心人物', 'color': '#4F46E5'},
            {'name': '主角B', 'role': '主角', 'gender': '不限', 'description': '另一位核心人物', 'color': '#EC4899'},
            {'name': '配角A', 'role': '配角', 'gender': '不限', 'description': '推动剧情发展的重要角色', 'color': '#10B981'},
            {'name': '反派', 'role': '反派', 'gender': '不限', 'description': '与主角对立的角色', 'color': '#EF4444'}
        ]
    }
    
    # 根据项目分类选择角色模板
    templates = character_templates.get(project.category, character_templates['默认'])
    
    # 创建角色
    characters_to_add = []
    for template in templates:
        character = Character(
            name=template['name'],
            role=template['role'],
            gender=template['gender'],
            description=template['description'],
            color=template['color'],
            project_id=project.id
        )
        characters_to_add.append(character)
    
    # 批量添加角色
    for character in characters_to_add:
        db.session.add(character)


@bp.route('/projects', methods=['GET'])
@login_required
def get_projects_page():
    return render_template('projects.html')


@bp.route('/projects/create', methods=['GET'])
@login_required
def create_project_page():
    return render_template('create_project.html')  # 需要创建这个模板


@bp.route('/api/projects', methods=['GET'])
@login_required
def get_projects():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)
    status = request.args.get('status', '')
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'newest')

    query = Project.query.filter_by(user_id=current_user.id)

    if status:
        query = query.filter_by(status=status)

    if search:
        query = query.filter(Project.title.contains(search) | Project.description.contains(search))

    # 排序
    if sort == 'newest':
        query = query.order_by(Project.created_at.desc())
    elif sort == 'oldest':
        query = query.order_by(Project.created_at.asc())
    elif sort == 'updated':
        query = query.order_by(Project.updated_at.desc())
    elif sort == 'name_asc':
        query = query.order_by(Project.title.asc())
    elif sort == 'name_desc':
        query = query.order_by(Project.title.desc())

    # 分页
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    projects = pagination.items

    return jsonify({
        'projects': [project.to_dict() for project in projects],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        }
    })


@bp.route('/api/projects/<int:project_id>', methods=['GET'])
@login_required
def get_project(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    return jsonify({'project': project.to_dict()})


@bp.route('/api/projects', methods=['POST'])
@login_required
def create_project():
    # 处理表单数据（支持JSON和FormData）
    if request.is_json:
        data = request.get_json()
        cover_file = None
    else:
        data = request.form.to_dict()
        cover_file = request.files.get('cover_image')
        
        # 处理JSON字符串字段
        if 'tags' in data and data['tags']:
            try:
                data['tags'] = json.loads(data['tags'])
            except:
                data['tags'] = [tag.strip() for tag in data['tags'].split(',') if tag.strip()]
        else:
            data['tags'] = []

        # 处理布尔值
        if 'is_public' in data:
            data['is_public'] = data['is_public'].lower() == 'true'

    # 调试信息
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logging.debug(f"Received data: {data}")
    logging.debug(f"Episode count: {data.get('episode_count')}")
    logging.debug(f"Episode type: {data.get('episode_type')}")

    if not data or not data.get('title'):
        return jsonify({'error': '项目标题是必填项'}), 400

    project = Project(
        title=data['title'],
        description=data.get('description', ''),
        theme=data.get('theme', ''),
        background=data.get('background', ''),
        category=data.get('category', '其他'),
        status=data.get('status', 'draft'),
        is_public=data.get('is_public', False),
        tags=json.dumps(data.get('tags', [])),
        user_id=current_user.id
    )

    # 处理封面图片上传
    if cover_file and cover_file.filename:
        import os
        from werkzeug.utils import secure_filename

        # 检查文件类型
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
        if '.' in cover_file.filename:
            ext = cover_file.filename.rsplit('.', 1)[1].lower()
            if ext not in allowed_extensions:
                return jsonify({'error': '只支持图片文件格式：png, jpg, jpeg, gif'}), 400

        # 创建安全的文件名
        timestamp = int(datetime.now().timestamp())
        filename = secure_filename(f"{current_user.id}_{timestamp}_{cover_file.filename}")
        filepath = os.path.join('uploads/covers', filename)

        # 确保目录存在
        os.makedirs('uploads/covers', exist_ok=True)

        # 保存文件
        cover_file.save(filepath)
        project.cover_image = filename

    db.session.add(project)
    
    try:
        db.session.commit()
        logging.debug("Project committed successfully")
    except Exception as e:
        logging.error(f"Error committing project: {str(e)}")
        db.session.rollback()
        return jsonify({'error': f'创建项目失败: {str(e)}'}), 500
    
    # 刷新project以确保获取最新的ID
    db.session.refresh(project)
    logging.debug(f"Project ID: {project.id}")

    # 获取初始集数设置
    episode_count = int(data.get('episode_count', 1))
    episode_type = data.get('episode_type', 'empty')
    
    logging.debug(f"Creating {episode_count} episodes of type {episode_type}")
    
    # 获取角色生成设置
    generate_characters = data.get('generate_characters', 'false')
    if isinstance(generate_characters, str):
        generate_characters = generate_characters.lower() == 'true'
    
    logging.debug(f"Generate characters: {generate_characters}")
    
    # 根据项目信息自动生成初始分集
    if episode_count > 0:
        try:
            generate_initial_episodes_ai(project, episode_count, episode_type)
            db.session.commit()
            # 更新项目的总集数
            project.total_episodes = Episode.query.filter_by(project_id=project.id).count()
            project.updated_at = datetime.utcnow()
            db.session.commit()
            logging.debug(f"Generated {len(project.episodes)} episodes")
        except Exception as e:
            logging.error(f"Error generating episodes: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())
            # 即使生成失败，项目仍然创建成功
    
    # 根据设置决定是否生成角色
    if generate_characters:
        try:
            generate_initial_characters_ai(project)
            db.session.commit()
            logging.debug(f"Generated {len(project.characters)} characters")
        except Exception as e:
            logging.error(f"Error generating characters: {str(e)}")
            import traceback
            logging.error(traceback.format_exc())

    # 记录项目创建日志
    log_user_action(
        '创建项目',
        f"创建项目: {project.title}",
        level='INFO',
        project_id=project.id,
        request_data={'title': project.title, 'category': project.category, 'episode_count': episode_count}
    )

    return jsonify({
        'message': '项目创建成功',
        'project': project.to_dict()
    }), 201


@bp.route('/api/projects/<int:project_id>', methods=['PUT'])
@login_required
def update_project(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    # 处理表单数据（支持JSON和FormData）
    if request.is_json:
        data = request.get_json()
        cover_file = None
    else:
        data = request.form.to_dict()
        cover_file = request.files.get('cover_image')

    # 更新基本信息
    if 'title' in data and data['title']:
        project.title = data['title']
    if 'theme' in data:
        project.theme = data['theme']
    if 'description' in data:
        project.description = data['description']
    if 'background' in data:
        project.background = data['background']
    if 'category' in data:
        project.category = data['category']
    if 'status' in data:
        project.status = data['status']
    if 'is_public' in data:
        project.is_public = data['is_public'].lower() == 'true' if isinstance(data['is_public'], str) else bool(data['is_public'])
    if 'tags' in data and data['tags']:
        try:
            # 尝试解析JSON
            if isinstance(data['tags'], str):
                tags = json.loads(data['tags'])
            else:
                tags = data['tags']
            project.tags = json.dumps(tags)
        except:
            # 如果不是JSON，按逗号分隔处理
            tags = [tag.strip() for tag in data['tags'].split(',') if tag.strip()]
            project.tags = json.dumps(tags)

    # 处理封面图片上传
    if cover_file and cover_file.filename:
        # 检查文件类型
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        if '.' in cover_file.filename:
            ext = cover_file.filename.rsplit('.', 1)[1].lower()
            if ext not in allowed_extensions:
                return jsonify({'error': '只支持图片文件格式：png, jpg, jpeg, gif, webp'}), 400
        
        # 创建安全的文件名
        timestamp = int(datetime.now().timestamp())
        filename = secure_filename(f"{current_user.id}_{timestamp}_{cover_file.filename}")
        filepath = os.path.join('uploads/covers', filename)
        
        # 确保目录存在
        os.makedirs('uploads/covers', exist_ok=True)
        
        # 保存文件
        cover_file.save(filepath)
        project.cover_image = filename

    project.updated_at = datetime.utcnow()
    db.session.commit()

    # 记录项目更新日志
    log_user_action(
        '更新项目',
        f"更新项目: {project.title}",
        level='INFO',
        project_id=project.id,
        request_data={'title': project.title, 'category': project.category}
    )

    return jsonify({
        'message': '项目更新成功',
        'project': project.to_dict()
    })


@bp.route('/api/projects/<int:project_id>', methods=['DELETE'])
@login_required
def delete_project(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        log_error('删除项目', f'项目不存在或无权访问: {project_id}', project_id=project_id)
        return jsonify({'error': '项目不存在或无权访问'}), 404

    project_title = project.title
    db.session.delete(project)
    db.session.commit()

    # 记录项目删除日志
    log_user_action(
        '删除项目',
        f"删除项目: {project_title}",
        level='WARNING',
        request_data={'project_id': project_id, 'title': project_title}
    )

    return jsonify({'message': '项目删除成功'})


@bp.route('/api/projects/<int:project_id>/cover', methods=['POST'])
@login_required
def upload_project_cover(project_id):
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    if 'cover' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400

    file = request.files['cover']

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

    filename = secure_filename(f"cover_{project_id}_{datetime.now().timestamp()}_{file.filename}")
    filepath = os.path.join('uploads/covers', filename)

    # 确保目录存在
    os.makedirs('uploads/covers', exist_ok=True)

    file.save(filepath)

    # 更新项目封面
    project.cover_image = filename
    db.session.commit()

    return jsonify({
        'message': '封面图片上传成功',
        'cover_url': f'/uploads/covers/{filename}'
    })


@bp.route('/projects/<int:project_id>')
@login_required
def project_detail_page(project_id):
    api_host = current_app.config.get('API_HOST', 'http://localhost:5001')
    return render_template('project_detail.html', api_host=api_host, current_user=current_user)


@bp.route('/projects/<int:project_id>/edit')
@login_required
def edit_project_page(project_id):
    return render_template('edit_project.html')  # 需要创建这个模板


@bp.route('/api/projects/stats', methods=['GET'])
@login_required
def get_project_stats():
    """获取用户项目的统计数据"""
    from sqlalchemy import func

    # 按状态统计
    status_stats = db.session.query(
        Project.status,
        func.count(Project.id).label('count')
    ).filter_by(user_id=current_user.id).group_by(Project.status).all()

    # 按分类统计
    category_stats = db.session.query(
        Project.category,
        func.count(Project.id).label('count')
    ).filter_by(user_id=current_user.id).group_by(Project.category).all()

    # 总数统计
    total_projects = Project.query.filter_by(user_id=current_user.id).count()
    total_episodes = db.session.query(func.sum(Project.total_episodes)).filter_by(user_id=current_user.id).scalar() or 0
    total_duration = db.session.query(func.sum(Project.total_duration)).filter_by(user_id=current_user.id).scalar() or 0

    # 最近创建的项目
    recent_projects = Project.query.filter_by(
        user_id=current_user.id
    ).order_by(Project.created_at.desc()).limit(5).all()

    return jsonify({
        'stats': {
            'total_projects': total_projects,
            'total_episodes': total_episodes,
            'total_duration': total_duration,
            'total_duration_formatted': f"{total_duration // 3600}:{(total_duration % 3600) // 60:02d}:{total_duration % 60:02d}",
            'by_status': {status: count for status, count in status_stats},
            'by_category': {category: count for category, count in category_stats}
        },
        'recent_projects': [project.to_dict() for project in recent_projects]
    })


@bp.route('/api/projects/<int:project_id>/analytics', methods=['GET'])
@login_required
def get_project_analytics(project_id):
    """获取特定项目的分析数据"""
    project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()

    if not project:
        return jsonify({'error': '项目不存在或无权访问'}), 404

    from sqlalchemy import func

    # 分集状态统计
    episode_status_stats = db.session.query(
        Episode.status,
        func.count(Episode.id).label('count'),
        func.sum(Episode.duration).label('total_duration')
    ).filter_by(project_id=project_id).group_by(Episode.status).all()

    # 分集时长分布
    episodes = Episode.query.filter_by(project_id=project_id).order_by(Episode.episode_number).all()

    # 角色统计
    character_stats = db.session.query(
        Character.role,
        func.count(Character.id).label('count')
    ).filter_by(project_id=project_id).group_by(Character.role).all()

    # 观看和点赞统计
    total_views = db.session.query(func.sum(Episode.views)).filter_by(project_id=project_id).scalar() or 0
    total_likes = db.session.query(func.sum(Episode.likes)).filter_by(project_id=project_id).scalar() or 0

    # 分集数据
    episode_data = []
    for episode in episodes:
        episode_data.append({
            'id': episode.id,
            'title': episode.title,
            'episode_number': episode.episode_number,
            'status': episode.status,
            'duration': episode.duration,
            'duration_formatted': episode.duration_formatted,
            'views': episode.views,
            'likes': episode.likes,
            'created_at': episode.created_at.isoformat()
        })

    return jsonify({
        'project': project.to_dict(),
        'analytics': {
            'episodes': {
                'total': len(episodes),
                'by_status': {status: {'count': count, 'total_duration': total_duration or 0} for status, count, total_duration in episode_status_stats},
                'data': episode_data
            },
            'characters': {
                'total': len(project.characters),
                'by_role': {role: count for role, count in character_stats}
            },
            'engagement': {
                'total_views': total_views,
                'total_likes': total_likes,
                'average_views_per_episode': total_views / len(episodes) if episodes else 0,
                'average_likes_per_episode': total_likes / len(episodes) if episodes else 0
            },
            'duration': {
                'total_seconds': project.total_duration,
                'total_formatted': f"{project.total_duration // 3600}:{(project.total_duration % 3600) // 60:02d}:{project.total_duration % 60:02d}",
                'average_per_episode': project.total_duration / len(episodes) if episodes else 0
            }
        }
    })


@bp.route('/api/projects/batch/update-status', methods=['POST'])
@login_required
def batch_update_project_status():
    """批量更新项目状态"""
    data = request.get_json()

    if not data or 'project_ids' not in data or 'status' not in data:
        return jsonify({'error': '需要提供项目ID列表和状态值'}), 400

    project_ids = data['project_ids']
    new_status = data['status']

    # 验证状态值
    valid_statuses = ['draft', 'active', 'completed', 'archived']
    if new_status not in valid_statuses:
        return jsonify({'error': f'无效的状态值，可选值：{", ".join(valid_statuses)}'}), 400

    # 批量更新
    updated_count = 0
    for project_id in project_ids:
        project = Project.query.filter_by(id=project_id, user_id=current_user.id).first()
        if project:
            project.status = new_status
            project.updated_at = datetime.utcnow()
            updated_count += 1

    db.session.commit()

    return jsonify({
        'message': f'成功更新 {updated_count} 个项目状态',
        'updated_count': updated_count,
        'status': new_status
    })


@bp.route('/api/projects/search', methods=['GET'])
@login_required
def search_projects():
    """高级搜索项目"""
    query = request.args.get('q', '')
    category = request.args.get('category', '')
    status = request.args.get('status', '')
    tags = request.args.get('tags', '')
    sort_by = request.args.get('sort_by', 'created_at')
    sort_order = request.args.get('sort_order', 'desc')

    # 基础查询
    db_query = Project.query.filter_by(user_id=current_user.id)

    # 关键词搜索
    if query:
        db_query = db_query.filter(
            (Project.title.contains(query)) |
            (Project.description.contains(query))
        )

    # 分类过滤
    if category:
        db_query = db_query.filter_by(category=category)

    # 状态过滤
    if status:
        db_query = db_query.filter_by(status=status)

    # 标签过滤
    if tags:
        tag_list = [tag.strip() for tag in tags.split(',') if tag.strip()]
        for tag in tag_list:
            db_query = db_query.filter(Project.tags.contains(f'"{tag}"'))

    # 排序
    if sort_by == 'title':
        order_column = Project.title
    elif sort_by == 'created_at':
        order_column = Project.created_at
    elif sort_by == 'updated_at':
        order_column = Project.updated_at
    elif sort_by == 'total_episodes':
        order_column = Project.total_episodes
    elif sort_by == 'total_duration':
        order_column = Project.total_duration
    else:
        order_column = Project.created_at

    if sort_order == 'asc':
        db_query = db_query.order_by(order_column.asc())
    else:
        db_query = db_query.order_by(order_column.desc())

    # 分页
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    pagination = db_query.paginate(page=page, per_page=per_page, error_out=False)
    projects = pagination.items

    return jsonify({
        'projects': [project.to_dict() for project in projects],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
            'has_prev': pagination.has_prev
        },
        'search': {
            'query': query,
            'category': category,
            'status': status,
            'tags': tags,
            'sort_by': sort_by,
            'sort_order': sort_order
        }
    })


