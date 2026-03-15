# routes/character_library.py - 角色库管理路由
from flask import Blueprint, request, jsonify, render_template, current_app
from flask_login import login_required, current_user
from __init__ import db
from models import Character
from services.log_service import log_user_action
from datetime import datetime
import json
import os

bp = Blueprint('character_library', __name__)


@bp.route('/character-library')
@login_required
def character_library_page():
    """角色库管理页面"""
    return render_template('character_library.html')


@bp.route('/api/character-library/list', methods=['GET'])
@login_required
def list_characters():
    """获取角色库列表 - 获取用户所有项目中的角色"""
    try:
        # 获取用户所有项目的角色
        from models import Project
        user_projects = Project.query.filter_by(user_id=current_user.id).all()
        project_ids = [p.id for p in user_projects]
        
        characters = Character.query.filter(
            Character.project_id.in_(project_ids)
        ).order_by(Character.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'characters': [char.to_dict() for char in characters]
        })
    except Exception as e:
        print(f"获取角色库失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/character-library/add', methods=['POST'])
@login_required
def add_character():
    """添加角色到角色库"""
    try:
        data = request.get_json()
        project_id = data.get('project_id')
        characters = data.get('characters', [])
        
        if not project_id:
            return jsonify({'error': 'project_id 不能为空'}), 400
        
        saved_count = 0
        for char_data in characters:
            char_name = char_data.get('identifier_in_scene') or char_data.get('name', '')
            if not char_name:
                continue
                
            # 检查是否已存在
            existing = Character.query.filter_by(
                project_id=project_id,
                name=char_name
            ).first()
            
            if existing:
                # 更新
                existing.description = char_data.get('static_features', '')
                existing.appearance = char_data.get('dynamic_features', '')
                existing.avatar = char_data.get('front_image')
                existing.avatar_back = char_data.get('back_image')
                existing.avatar_side = char_data.get('side_image')
            else:
                # 创建新角色
                new_char = Character(
                    project_id=project_id,
                    name=char_name,
                    role='角色库',
                    description=char_data.get('static_features', ''),
                    appearance=char_data.get('dynamic_features', ''),
                    avatar=char_data.get('front_image'),
                    avatar_back=char_data.get('back_image'),
                    avatar_side=char_data.get('side_image'),
                    created_at=datetime.utcnow()
                )
                db.session.add(new_char)
            
            saved_count += 1
        
        db.session.commit()
        
        log_user_action(
            '添加角色到角色库',
            f'添加了 {saved_count} 个角色',
            level='INFO'
        )
        
        return jsonify({
            'success': True,
            'message': f'成功保存 {saved_count} 个角色'
        })
    except Exception as e:
        db.session.rollback()
        print(f"添加角色失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@bp.route('/api/character-library/<int:character_id>', methods=['DELETE'])
@login_required
def delete_character(character_id):
    """删除角色"""
    try:
        from models import Project
        # 获取用户的项目IDs
        user_projects = Project.query.filter_by(user_id=current_user.id).all()
        project_ids = [p.id for p in user_projects]
        
        character = Character.query.filter_by(id=character_id).first()
        
        if not character:
            return jsonify({'error': '角色不存在'}), 404
        
        # 验证权限
        if character.project_id not in project_ids:
            return jsonify({'error': '无权删除此角色'}), 403
        
        db.session.delete(character)
        db.session.commit()
        
        return jsonify({'success': True, 'message': '角色已删除'})
    except Exception as e:
        db.session.rollback()
        print(f"删除角色失败: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/character-library/<int:character_id>', methods=['PUT'])
@login_required
def update_character(character_id):
    """更新角色信息"""
    try:
        data = request.get_json()
        from models import Project
        user_projects = Project.query.filter_by(user_id=current_user.id).all()
        project_ids = [p.id for p in user_projects]
        
        character = Character.query.filter_by(id=character_id).first()
        
        if not character:
            return jsonify({'error': '角色不存在'}), 404
        
        if character.project_id not in project_ids:
            return jsonify({'error': '无权修改此角色'}), 403
        
        if 'name' in data:
            character.name = data['name']
        if 'description' in data:
            character.description = data['description']
        if 'appearance' in data:
            character.appearance = data['appearance']
        
        db.session.commit()
        
        return jsonify({'success': True, 'character': character.to_dict()})
    except Exception as e:
        db.session.rollback()
        print(f"更新角色失败: {e}")
        return jsonify({'error': str(e)}), 500