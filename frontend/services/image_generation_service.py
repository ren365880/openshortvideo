"""
统一的图片生成服务模块
支持多种文生图、图像编辑等模型的集成
"""
import os
import asyncio
import logging
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger('image_service')


class BaseImageGenerator(ABC):
    """图片生成器基类"""
    
    @abstractmethod
    async def generate_image(
        self, 
        prompt: str, 
        reference_images: List[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        生成图片
        返回: {'success': bool, 'image_path': str, 'image_data': bytes, 'error': str}
        """
        pass
    
    @abstractmethod
    async def edit_image(
        self,
        image_path: str,
        prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        编辑图片
        返回: {'success': bool, 'image_path': str, 'image_data': bytes, 'error': str}
        """
        pass


class NanobananaYunwuImageGenerator(BaseImageGenerator):
    """Nanobanana Yunwu 图片生成器 (基于Google Gemini)"""
    
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash-image-preview"):
        from google import genai
        from google.genai import types
        
        self.client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                base_url="https://yunwu.ai",
                api_version="v1beta",
            ),
        )
        self.model = model
    
    async def generate_image(
        self, 
        prompt: str, 
        reference_images: List[str] = None,
        aspect_ratio: str = "16:9",
        **kwargs
    ) -> Dict[str, Any]:
        try:
            from PIL import Image
            from interfaces.image_output import ImageOutput
            
            logger.info(f"Calling {self.model} to generate image...")
            
            reference_image_list = []
            if reference_images:
                for path in reference_images:
                    if os.path.exists(path):
                        reference_image_list.append(Image.open(path))
            
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=reference_image_list + [prompt],
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(
                        aspect_ratio=aspect_ratio,
                    ),
                ),
            )
            
            image = None
            text = ""
            for part in response.candidates[0].content.parts:
                if part.text is not None:
                    text += part.text
                elif part.inline_data is not None:
                    image = part.as_image()
            
            if image is None:
                logger.warning(f"[Nanobanana] Line ~99 - No image in response, text: {text[:200]}")
                return {'success': False, 'error': f"No image generated. Response: {text}"}
            
            logger.info(f"[Nanobanana] Image generated successfully")
            return {'success': True, 'image_data': image, 'text': text}
            
        except Exception as e:
            import traceback
            logger.error(f"[Nanobanana] Image generation failed (line ~104): {str(e)}")
            logger.error(f"[Nanobanana] Traceback: {traceback.format_exc()}")
            return {'success': False, 'error': str(e)}
    
    async def edit_image(
        self,
        image_path: str,
        prompt: str,
        **kwargs
    ) -> Dict[str, Any]:
        return await self.generate_image(prompt, reference_images=[image_path], **kwargs)


class SiliconFlowImageGenerator(BaseImageGenerator):
    """SiliconFlow 图片生成器"""
    
    def __init__(self, api_key: str, model: str = "black-forest-labs/FLUX.1-dev"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.siliconflow.cn/v1"
    
    async def generate_image(
        self, 
        prompt: str, 
        reference_images: List[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        try:
            import requests
            
            url = f"{self.base_url}/images/generations"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": self.model,
                "prompt": prompt,
                "image_size": kwargs.get('image_size', '1024x1024'),
                "num_inference_steps": kwargs.get('steps', 20),
                "guidance_scale": kwargs.get('guidance_scale', 7.5)
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            logger.info(f"[SiliconFlow] Response status: {response.status_code}")
            logger.info(f"[SiliconFlow] Response text (first 500): {response.text[:500] if response.text else 'empty'}")
            
            if response.status_code != 200:
                logger.error(f"[SiliconFlow] API error: status={response.status_code}, body={response.text[:200]}")
                return {'success': False, 'error': f"API error: {response.status_code}"}
            
            result = response.json()
            
            if 'data' in result and len(result['data']) > 0:
                image_url = result['data'][0]['url']
                logger.info(f"[SiliconFlow] Image generated successfully: {image_url}")
                return {'success': True, 'image_url': image_url}
            else:
                logger.warning(f"[SiliconFlow] No image in response: {result}")
                return {'success': False, 'error': result.get('message', 'Unknown error')}
                
        except Exception as e:
            import traceback
            logger.error(f"[SiliconFlow] Image generation failed (line ~157): {str(e)}")
            logger.error(f"[SiliconFlow] Traceback: {traceback.format_exc()}")
            return {'success': False, 'error': str(e)}
    
    async def edit_image(self, image_path: str, prompt: str, **kwargs) -> Dict[str, Any]:
        # SiliconFlow暂不支持图像编辑，使用生成替代
        return await self.generate_image(prompt, **kwargs)


class OpenAIImageGenerator(BaseImageGenerator):
    """OpenAI DALL-E 图片生成器"""
    
    def __init__(self, api_key: str, model: str = "dall-e-3"):
        self.api_key = api_key
        self.model = model
    
    async def generate_image(
        self, 
        prompt: str, 
        reference_images: List[str] = None,
        size: str = "1024x1024",
        **kwargs
    ) -> Dict[str, Any]:
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=self.api_key)
            
            response = await client.images.generate(
                model=self.model,
                prompt=prompt,
                size=size,
                n=1
            )
            
            image_url = response.data[0].url
            logger.info(f"[OpenAI] Image generated: {image_url}")
            return {'success': True, 'image_url': image_url}
            
        except Exception as e:
            import traceback
            logger.error(f"[OpenAI] Image generation failed (line ~210): {str(e)}")
            logger.error(f"[OpenAI] Traceback: {traceback.format_exc()}")
            return {'success': False, 'error': str(e)}
    
    async def edit_image(self, image_path: str, prompt: str, **kwargs) -> Dict[str, Any]:
        # DALL-E 2支持编辑
        try:
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=self.api_key)
            
            response = await client.images.edit(
                image=open(image_path, "rb"),
                model=self.model,
                prompt=prompt,
                n=1
            )
            
            image_url = response.data[0].url
            return {'success': True, 'image_url': image_url}
            
        except Exception as e:
            logger.error(f"OpenAI image edit failed: {str(e)}")
            return {'success': False, 'error': str(e)}


class UnifiedGeneratorImageGenerator(BaseImageGenerator):
    """本地部署的统一生成器（UnifiedGenerator）"""
    
    def __init__(self, api_key: str, base_url: str = "http://192.168.2.15:58888", 
                 model: str = "black-forest-labs/FLUX.2-klein-4B"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.negative_prompt = "低分辨率，低画质，肢体畸形，手指畸形，画面过饱和，蜡像感，人脸无细节，过度光滑，画面具有AI感。构图混乱。文字模糊，扭曲。"
    
    async def generate_image(
        self, 
        prompt: str, 
        reference_images: List[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """文生图或图生图"""
        try:
            # 导入统一生成器客户端
            import sys
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from api_services.UnifiedGenerator_image import UnifiedGeneratorClient
            
            client = UnifiedGeneratorClient(
                base_url=self.base_url,
                api_key=self.api_key
            )
            
            # 判断是文生图还是图生图
            if reference_images and len(reference_images) > 0:
                # 图生图/图像编辑
                image_path = reference_images[0].replace("\\","/")
                logger.info(f"[UnifiedGenerator] Using image edit mode with reference: {image_path}")
                
                # 检查是否是本地路径
                if os.path.exists(image_path):
                    # 获取服务器地址，构造HTTP URL
                    # 假设Flask运行在某个端口，uploads目录可以通过HTTP访问
                    # 这里需要外部传入服务器地址，或者使用环境变量
                    flask_base_url = kwargs.get('flask_base_url', 'http://192.168.2.15:5000/')
                    
                    # 把本地路径转换为相对路径
                    rel_path = image_path
                    # 处理各种uploads路径
                    if 'uploads/' in image_path:
                        rel_path = '/' + image_path.replace('\\', '/')
                        # 移除开头的 /
                        if rel_path.startswith('/'):
                            rel_path = rel_path[1:]
                    
                    reference_url = f"{flask_base_url}{rel_path}"
                    logger.info(f"[UnifiedGenerator] Using reference image URL: {reference_url}")
                    
                    # 验证URL是否可访问
                    import requests
                    try:
                        verify_response = requests.head(reference_url, timeout=5)
                        logger.info(f"[UnifiedGenerator] Reference URL status: {verify_response.status_code}")
                    except Exception as e:
                        logger.warning(f"[UnifiedGenerator] Failed to verify reference URL: {e}")
                    
                    result = client.image_edit(
                        prompt=prompt,
                        image_url=reference_url,
                        negative_prompt=self.negative_prompt,
                        height=kwargs.get('height', 1024),
                        width=kwargs.get('width', 1024),
                        seed=kwargs.get('seed')
                    )
                else:
                    # 如果已经是HTTP URL，直接使用
                    result = client.image_edit(
                        prompt=prompt,
                        image_url=image_path,
                        negative_prompt=self.negative_prompt,
                        height=kwargs.get('height', 1024),
                        width=kwargs.get('width', 1024),
                        seed=kwargs.get('seed')
                    )
            else:
                # 文生图
                logger.info(f"[UnifiedGenerator] Using text-to-image mode")
                
                result = client.text_to_image(
                    prompt=prompt,
                    negative_prompt=self.negative_prompt,
                    height=kwargs.get('height', 1024),
                    width=kwargs.get('width', 1024),
                    seed=kwargs.get('seed')
                )
            
            # 解析结果
            if result and 'files' in result and len(result['files']) > 0:
                image_url = result['files'][0]['url']
                logger.info(f"[UnifiedGenerator] Image generated: {image_url}")
                return {'success': True, 'image_url': image_url}
            else:
                logger.warning(f"[UnifiedGenerator] No image in result: {result}")
                return {'success': False, 'error': 'No image generated'}
                
        except Exception as e:
            import traceback
            logger.error(f"[UnifiedGenerator] Image generation failed: {str(e)}")
            logger.error(f"[UnifiedGenerator] Traceback: {traceback.format_exc()}")
            return {'success': False, 'error': str(e)}
    
    async def edit_image(self, image_path: str, prompt: str, **kwargs) -> Dict[str, Any]:
        """图像编辑"""
        return await self.generate_image(prompt, reference_images=[image_path], **kwargs)


class ImageGeneratorFactory:
    """图片生成器工厂类"""
    
    _generators = {
        'nanobanana_yunwu': NanobananaYunwuImageGenerator,
        'siliconflow': SiliconFlowImageGenerator,
        'openai_dalle': OpenAIImageGenerator,
        'unified_generator': UnifiedGeneratorImageGenerator,
    }
    
    @classmethod
    def create(cls, generator_type: str, api_key: str, **kwargs) -> BaseImageGenerator:
        """创建图片生成器实例"""
        generator_class = cls._generators.get(generator_type.lower())
        
        if not generator_class:
            raise ValueError(f"Unknown generator type: {generator_type}. Available: {list(cls._generators.keys())}")
        
        return generator_class(api_key=api_key, **kwargs)
    
    @classmethod
    def register(cls, name: str, generator_class: type):
        """注册新的图片生成器"""
        cls._generators[name.lower()] = generator_class
    
    @classmethod
    def get_available_generators(cls) -> List[str]:
        """获取可用的生成器列表"""
        return list(cls._generators.keys())


# 便捷函数
def get_image_generator(config: Dict[str, Any]) -> Optional[BaseImageGenerator]:
    """
    根据配置获取图片生成器
    配置格式:
    {
        'type': 'nanobanana_yunwu',  # 生成器类型
        'api_key': 'xxx',            # API密钥
        'model': 'gemini-2.5-flash-image-preview'  # 可选，模型名称
    }
    """
    if not config:
        return None
    
    generator_type = config.get('type') or config.get('class_path', '').lower()
    
    # 从class_path提取类型
    if 'nanobanana' in generator_type:
        generator_type = 'nanobanana_yunwu'
    elif 'siliconflow' in generator_type:
        generator_type = 'siliconflow'
    elif 'openai' in generator_type:
        generator_type = 'openai_dalle'
    elif 'unified' in generator_type or 'local' in generator_type:
        generator_type = 'unified_generator'
    else:
        logger.warning(f"Unknown generator type: {generator_type}, using default")
        generator_type = 'nanobanana_yunwu'
    
    api_key = config.get('api_key') or config.get('init_args', {}).get('api_key', '')
    model = config.get('model') or config.get('init_args', {}).get('model', '')
    base_url = config.get('base_url') or config.get('init_args', {}).get('base_url', '')
    
    try:
        if generator_type == 'unified_generator':
            return ImageGeneratorFactory.create(generator_type, api_key, 
                model=model if model else None,
                base_url=base_url if base_url else "http://192.168.2.15:58888")
        else:
            return ImageGeneratorFactory.create(generator_type, api_key, model=model if model else None)
    except Exception as e:
        logger.error(f"Failed to create image generator: {e}")
        return None


async def generate_character_image(
    character_prompt: str,
    generator_config: Dict[str, Any] = None,
    output_dir: str = None,
    reference_image: str = None,
    image_type: str = 'character'
) -> Optional[str]:
    """
    生成角色图像
    
    Args:
        character_prompt: 角色描述提示词
        generator_config: 生成器配置
        output_dir: 输出目录
        reference_image: 参考图像路径（用于图生图/图像编辑）
        image_type: 图像类型，用于生成唯一文件名 (character/front/back/side)
    
    Returns:
        生成的图像路径，失败返回None
    """
    generator = get_image_generator(generator_config) if generator_config else None
    
    if not generator:
        logger.warning("[generate_character_image] No image generator configured")
        return None
    
    logger.info(f"[generate_character_image] Starting generation with prompt: {character_prompt}")
    logger.info(f"[generate_character_image] Generator config: {generator_config}")
    logger.info(f"[generate_character_image] Reference image: {reference_image}")
    logger.info(f"[generate_character_image] Image type: {image_type}")
    
    try:
        # 如果有参考图像，使用图生图模式
        reference_images = [reference_image] if reference_image else None
        
        result = await generator.generate_image(
            prompt=character_prompt,
            reference_images=reference_images,
            aspect_ratio="1:1"  # 角色头像用正方形
        )
        
        logger.info(f"[generate_character_image] Result: {result}")
        
        if result.get('success'):
            # 保存图像
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)
            
            image_data = result.get('image_data')
            image_url = result.get('image_url')
            
            # 生成唯一文件名
            filename = f"{image_type}.png"
            
            if image_data and output_dir:
                # 保存PIL图像
                image_path = os.path.join(output_dir, filename)
                image_data.save(image_path)
                logger.info(f"[generate_character_image] Image saved to: {image_path}")
                return image_path
            elif image_url:
                # 下载URL图像
                import requests
                if output_dir:
                    image_path = os.path.join(output_dir, filename)
                    response = requests.get(image_url)
                    with open(image_path, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"[generate_character_image] Image downloaded to: {image_path}")
                    return image_path
            
            logger.info(f"[generate_character_image] Character image generated: {image_url or 'PIL image'}")
            return image_url or 'generated'
        else:
            logger.error(f"[generate_character_image] Line ~352 - Generation failed: {result.get('error')}")
            return None
            
    except Exception as e:
        import traceback
        logger.error(f"[generate_character_image] Line ~356 - Error: {str(e)}")
        logger.error(f"[generate_character_image] Traceback: {traceback.format_exc()}")
        return None
