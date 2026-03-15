import os
import json
import time
import logging
from typing import List, Dict, Any, Optional
from openai import OpenAI
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from services.log_service import log_ai_call

logger = logging.getLogger('deepseek_api')


class DeepSeekAPI:
    def __init__(self):
        self.api_key = ""
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY environment variable is not set")

        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com"
        )
        self.model = "deepseek-chat"

    def generate_field_content(
        self, 
        field: str, 
        title: str, 
        category: str = "其他",
        theme: str = "",
        description: str = "",
        project_id: int = None,
        user_input: str = "",
        count: int = 3
    ) -> Dict[str, Any]:
        """生成项目字段内容（主题、描述、背景、分集、角色）
        
        Args:
            field: 字段类型 (theme/description/background/episodes/characters)
            title: 项目标题
            category: 项目分类
            theme: 主题 (description和background字段需要)
            description: 项目描述 (background字段需要)
            user_input: 用户输入 (用于episodes和characters)
            count: 生成数量
            project_id: 项目ID
        """
        start_time = time.time()
        
        system_prompts = {
            "theme": "你是一个专业的短剧编剧。请基于用户提供的项目标题和分类，生成3个有吸引力的短剧主题。主题应该简洁明了，8-15个字，能够概括整个故事的核心。主题应该与标题相关联，体现故事的核心冲突或亮点。",
            
            "description": "你是一个专业的短剧编剧。请基于以下信息生成3个的项目描述选项：\n- 项目标题\n- 已选择的主题\n- 项目分类\n\n每个描述应该是80-150字，包含：故事梗概，主要冲突、核心看点。描述应该紧扣主题，形成完整的故事线。",
            
            "background": "你是一个专业的短剧编剧。请基于以下信息生成3个详细的故事背景设定：\n- 项目标题\n- 主题\n- 项目描述\n- 项目分类\n\n每个背景应该包含150-250字：\n1. 时代背景和地点\n2. 主要人物关系\n3. 世界观设定\n4. 核心冲突来源\n5. 情感基调\n\n背景应该与主题和描述保持一致性。",
            
            "episodes": "你是一个专业的短剧编剧。请根据项目信息生成分集大纲。你必须返回JSON数组格式，不要返回markdown或其他格式。每个分集需要包含：title(集标题)、summary(剧情梗概)、scenes(场景设定)、key_points(关键情节点)。",
            
            "characters": "你是一个专业的角色设计师。请根据项目信息生成详细必须返回JSON数组的人物角色设定。你格式，不要返回markdown或其他格式。每个角色需要包含：name(姓名)、gender(性别)、age(年龄)、role(角色定位)、personality(性格特点)、appearance(外貌描述)、background(背景故事)、function(在故事中的作用)。",
        }
        
        user_prompts = {
            "theme": f"""项目标题：{title}
项目分类：{category}

请生成3个与标题相关联的主题选项。每个主题8-15个字，要能体现故事的核心冲突或亮点。
要求：
1. 主题要与标题有关联性
2. 要能引发观众兴趣
3. 简洁有力，易于记忆

请直接返回JSON数组格式，不要有其他内容。例如：["主题1", "主题2", "主题3"]""",
            
            "description": f"""项目标题：{title}
项目分类：{category}
已选择的主题：{theme}

请基于以上信息，生成3个项目描述选项。每个选项必须包含以下3个独立字段：
1. 故事梗概（50-80字）
2. 主要冲突（30-50字）
3. 核心看点（30-50字）

格式要求：每个选项必须是JSON对象，包含"故事梗概"、"主要冲突"、"核心看点"三个字段。
例如：[{{"故事梗概":"...","主要冲突":"...","核心看点":"..."}},{{"故事梗概":"...","主要冲突":"...","核心看点":"..."}},{{"故事梗概":"...","主要冲突":"...","核心看点":"..."}}]""",
            
            "background": f"""项目标题：{title}
项目分类：{category}
主题：{theme}
项目描述：{description}

请基于以上信息，生成3个详细的故事背景设定。
要求：
1. 每个背景150-250字
2. 包含：时代背景和地点、主要人物关系、世界观设定、核心冲突来源、情感基调
3. 与主题和描述保持一致性
4. 有画面感，便于后续创作

请直接返回JSON数组格式，不要有其他内容。""",
            
            "episodes": f"""{user_input}

请生成{count}集的分集大纲，每集需要包含：
1. title: 集标题
2. summary: 剧情梗概（100-150字）
3. scenes: 场景设定
4. key_points: 关键情节点

要求：
1. 每集剧情要有连贯性和递进关系
2. 紧扣项目主题和风格
3. 剧情要有人物成长和冲突
4. 每集结尾要留有悬念或过渡

请直接返回JSON数组格式，例如：
[{{"title": "第1集标题", "summary": "剧情梗概", "scenes": "场景设定", "key_points": "关键情节点"}}, ...]""",
            
            "characters": f"""{user_input}

请生成{count}个主要角色。每个角色需要包含：
1. name: 姓名
2. gender: 性别（男/女/不限）
3. age: 年龄
4. role: 角色定位（主角/配角/反派等）
5. personality: 性格特点
6. appearance: 外貌描述（用于AI绘画，简洁具体）
7. background: 背景故事
8. function: 在故事中的作用

请直接返回JSON数组格式，例如：
[{{"name": "角色名", "gender": "男", "age": "25岁", "role": "主角", "personality": "性格特点", "appearance": "外貌描述", "background": "背景故事", "function": "在故事中的作用"}}, ...]"""
        }
        
        user_prompts = {
            "theme": f"""项目标题：{title}
项目分类：{category}

请生成3个与标题相关联的主题选项。每个主题8-15个字，要能体现故事的核心冲突或亮点。
要求：
1. 主题要与标题有关联性
2. 要能引发观众兴趣
3. 简洁有力，易于记忆

请直接返回JSON数组格式，不要有其他内容。例如：["主题1", "主题2", "主题3"]""",
            
            "description": f"""项目标题：{title}
项目分类：{category}
已选择的主题：{theme}

请基于以上信息，生成3个项目描述选项。每个选项必须包含以下3个独立字段：
1. 故事梗概（50-80字）
2. 主要冲突（30-50字）
3. 核心看点（30-50字）

格式要求：每个选项必须是JSON对象，包含"故事梗概"、"主要冲突"、"核心看点"三个字段。
例如：[{{"故事梗概":"...","主要冲突":"...","核心看点":"..."}},{{"故事梗概":"...","主要冲突":"...","核心看点":"..."}},{{"故事梗概":"...","主要冲突":"...","核心看点":"..."}}]""",
            
            "background": f"""项目标题：{title}
项目分类：{category}
主题：{theme}
项目描述：{description}

请基于以上信息，生成3个详细的故事背景设定。
要求：
1. 每个背景150-250字
2. 包含：时代背景和地点、主要人物关系、世界观设定、核心冲突来源、情感基调
3. 与主题和描述保持一致性
4. 有画面感，便于后续创作

请直接返回JSON数组格式，不要有其他内容。"""
        }

        try:
            logger.info(f"=== DeepSeek API 调用 ===")
            logger.info(f"field={field}, title={title}, category={category}, theme={theme[:50] if theme else ''}")
            logger.info(f"user_input长度: {len(user_input) if user_input else 0}")
            logger.info(f"user_input长度: {user_input}")
            # 使用user_input作为用户提示，如果没有提供则使用预定义的模板
            user_content = user_input if user_input else user_prompts.get(field, "")
            logger.info(f"user_content长度: {len(user_content)}")
            logger.info(f"user_content长度: {user_content}")
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompts.get(field, system_prompts["theme"])},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.8,
                max_tokens=2000,
                response_format={"type": "text"}
            )

            result_text = response.choices[0].message.content.strip()
            logger.info(f"API原始返回长度: {len(result_text)}")
            logger.info(f"API原始返回前500字符: {result_text[:500]}")
            
            # 尝试解析JSON数组
            try:
                # 尝试直接解析
                if result_text.startswith('['):
                    result = json.loads(result_text)
                    logger.info(f"直接解析JSON数组成功: {type(result)}")
                else:
                    # 尝试提取JSON部分
                    import re
                    json_match = re.search(r'\[[\s\S]*\]', result_text)
                    if json_match:
                        result = json.loads(json_match.group())
                        logger.info(f"提取JSON数组成功: {type(result)}, 长度={len(result)}")
                    else:
                        # 尝试提取多个JSON对象（可能被markdown代码块包裹）
                        json_objects = re.findall(r'\{[\s\S]*?\}', result_text)
                        if json_objects:
                            parsed_objects = []
                            for obj_str in json_objects:
                                try:
                                    parsed_objects.append(json.loads(obj_str))
                                except:
                                    continue
                            if parsed_objects:
                                result = parsed_objects
                                logger.info(f"从markdown提取{len(parsed_objects)}个JSON对象")
                            else:
                                # 如果无法解析，返回原始文本作为数组
                                result = [result_text]
                                logger.warning(f"无法解析JSON，将文本作为数组")
                        else:
                            # 如果无法解析，返回原始文本作为数组
                            result = [result_text]
                            logger.warning(f"无法解析JSON，将文本作为数组: {result_text[:100]}...")
            except Exception as e:
                logger.exception(f"JSON解析失败: {e}, 原始文本: {result_text[:200]}")
                result = [result_text]
            
            # 确保返回的是字符串数组，不是对象数组
            final_result = []
            for item in result:
                if isinstance(item, dict):
                    # 如果是对象，转为格式化字符串
                    final_result.append(json.dumps(item, ensure_ascii=False, indent=2))
                elif isinstance(item, str):
                    final_result.append(item)
                else:
                    final_result.append(str(item))
            
            logger.info(f"最终返回结果类型: {type(final_result)}, 长度: {len(final_result)}, 内容预览: {final_result[:2] if final_result else []}")
            
            # 记录AI调用日志
            duration_ms = int((time.time() - start_time) * 1000)
            log_ai_call(
                action=f'生成项目{field}',
                model=self.model,
                prompt=user_prompts.get(field, ''),
                response=json.dumps(final_result)[:500],
                duration_ms=duration_ms,
                status='success',
                project_id=project_id
            )
            
            logger.info(f"generate_field_content返回: result类型={type(final_result)}, 数据={str(final_result)[:100]}")
            return {"success": True, "data": final_result}

        except Exception as e:
            logger.exception(f"DeepSeek generate_field_content 异常: {str(e)}")
            duration_ms = int((time.time() - start_time) * 1000)
            log_ai_call(
                action=f'生成项目{field}',
                model=self.model,
                prompt=user_prompts.get(field, ''),
                response=None,
                duration_ms=duration_ms,
                status='failed',
                error=str(e),
                project_id=project_id
            )
            return {"success": False, "error": str(e)}

        user_prompts = {
            "theme": f"请为{category}类短剧生成3个有吸引力的主题选项。{f'用户的想法是：{user_input}' if user_input else ''}每个主题10-15个字，格式为JSON数组。",
            "description": f"请为这个{category}类短剧主题生成项目描述：{user_input}。生成3个不同风格的描述选项，每个80-120字，格式为JSON数组。",
            "background": f"请为这个{category}类短剧生成详细的故事背景：{user_input}。生成3个不同设定的背景选项，每个150-200字，格式为JSON数组。"
        }

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompts[prompt_type]},
                    {"role": "user", "content": user_prompts[prompt_type]}
                ],
                temperature=0.8,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            
            # 记录AI调用日志
            duration_ms = int((time.time() - start_time) * 1000)
            log_ai_call(
                action=f'生成项目{prompt_type}',
                model=self.model,
                prompt=user_prompts[prompt_type],
                response=json.dumps(result)[:500],
                duration_ms=duration_ms,
                status='success',
                project_id=project_id
            )
            
            return {"success": True, "data": result}

        except Exception as e:
            # 记录错误日志
            duration_ms = int((time.time() - start_time) * 1000)
            log_ai_call(
                action=f'生成项目{prompt_type}',
                model=self.model,
                prompt=user_prompts.get(prompt_type, ''),
                response=None,
                duration_ms=duration_ms,
                status='failed',
                error=str(e),
                project_id=project_id
            )
            return {"success": False, "error": str(e)}

    def generate_episode_outline(self, project_info: Dict[str, Any], episode_count: int, project_id: int = None) -> Dict[str, Any]:
        """生成分集大纲"""
        start_time = time.time()
        prompt = f"""
            项目信息：
            - 标题：{project_info.get('title')}
            - 分类：{project_info.get('category')}
            - 主题：{project_info.get('theme')}
            - 描述：{project_info.get('description')}
            - 背景：{project_info.get('background')}

            请生成{episode_count}集的分集大纲，每集包含：
            1. 集标题
            2. 剧情梗概（100字左右）
            3. 主要场景
            4. 关键情节

            格式为JSON，包含一个episodes数组。
            """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的短剧编剧助手。请根据项目信息，生成详细的分集大纲。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            
            # 记录AI调用日志
            duration_ms = int((time.time() - start_time) * 1000)
            log_ai_call(
                action='生成分集大纲',
                model=self.model,
                prompt=prompt,
                response=json.dumps(result)[:500],
                duration_ms=duration_ms,
                status='success',
                project_id=project_id
            )
            
            return {"success": True, "data": result}

        except Exception as e:
            # 记录错误日志
            duration_ms = int((time.time() - start_time) * 1000)
            log_ai_call(
                action='生成分集大纲',
                model=self.model,
                prompt=prompt,
                response=None,
                duration_ms=duration_ms,
                status='failed',
                error=str(e),
                project_id=project_id
            )
            return {"success": False, "error": str(e)}

    def generate_character_profile(self, project_info: Dict[str, Any], count: int = 3, project_id: int = None) -> Dict[str, Any]:
        """生成角色设定"""
        start_time = time.time()
        prompt = f"""
            项目信息：
            - 标题：{project_info.get('title')}
            - 分类：{project_info.get('category')}
            - 主题：{project_info.get('theme')}
            - 描述：{project_info.get('description')}

            请生成{count}个主要角色的详细设定，每个角色包含：
            1. 姓名
            2. 年龄
            3. 性别
            4. 职业/身份
            5. 性格特点
            6. 背景故事
            7. 在故事中的作用

            格式为JSON，包含一个characters数组。
            """
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的角色设计师。请根据项目信息，生成详细的人物角色设定。"
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            
            # 记录AI调用日志
            duration_ms = int((time.time() - start_time) * 1000)
            log_ai_call(
                action='生成角色设定',
                model=self.model,
                prompt=prompt,
                response=json.dumps(result)[:500],
                duration_ms=duration_ms,
                status='success',
                project_id=project_id
            )
            
            return {"success": True, "data": result}

        except Exception as e:
            # 记录错误日志
            duration_ms = int((time.time() - start_time) * 1000)
            log_ai_call(
                action='生成角色设定',
                model=self.model,
                prompt=prompt,
                response=None,
                duration_ms=duration_ms,
                status='failed',
                error=str(e),
                project_id=project_id
            )
            return {"success": False, "error": str(e)}


# 全局实例
deepseek_client = None


def get_deepseek_client():
    """获取DeepSeek客户端实例"""
    global deepseek_client
    if deepseek_client is None:
        try:
            deepseek_client = DeepSeekAPI()
        except Exception as e:
            print(f"初始化DeepSeek客户端失败: {e}")
            return None
    return deepseek_client