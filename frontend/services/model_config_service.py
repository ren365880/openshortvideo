"""
模型配置服务 - 管理视频生成所需的各类模型配置
包括LLM、MLLM、文生图、视频生成、图像编辑等模型的配置
"""
import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import yaml


# 默认配置目录
DEFAULT_CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend', 'configs')


@dataclass
class ModelConfig:
    """单个模型配置"""
    class_path: str = ""
    init_args: Dict[str, Any] = None
    max_requests_per_minute: Optional[int] = None
    max_requests_per_day: Optional[int] = None
    
    def __post_init__(self):
        if self.init_args is None:
            self.init_args = {}
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ModelConfig':
        if data is None:
            return cls()
        return cls(**data)


@dataclass
class GenerationModelConfig:
    """生成流程的完整模型配置"""
    chat_model: Optional[ModelConfig] = None
    mllm_model: Optional[ModelConfig] = None
    image_generator: Optional[ModelConfig] = None
    video_generator: Optional[ModelConfig] = None
    image_editor: Optional[ModelConfig] = None
    
    def to_dict(self) -> Dict:
        result = {}
        for key, value in asdict(self).items():
            if value is not None:
                result[key] = value.to_dict() if hasattr(value, 'to_dict') else value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'GenerationModelConfig':
        if data is None:
            return cls()
        parsed = {}
        for key, value in data.items():
            if isinstance(value, dict):
                parsed[key] = ModelConfig.from_dict(value)
            else:
                parsed[key] = value
        return cls(**parsed)


# 可用的模型选项
AVAILABLE_CHAT_MODELS = [
    {"id": "deepseek-chat", "name": "DeepSeek Chat", "provider": "DeepSeek"},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "OpenAI"},
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
    {"id": "claude-3-haiku", "name": "Claude 3 Haiku", "provider": "Anthropic"},
    {"id": "claude-3-sonnet", "name": "Claude 3 Sonnet", "provider": "Anthropic"},
    {"id": "qwen-plus", "name": "Qwen Plus", "provider": "Alibaba"},
    {"id": "qwen-turbo", "name": "Qwen Turbo", "provider": "Alibaba"},
]

AVAILABLE_MLLM_MODELS = [
    {"id": "Qwen/Qwen3-VL-32B-Instruct", "name": "Qwen3-VL-32B", "provider": "SiliconFlow"},
    {"id": "Qwen/Qwen2-VL-72B-Instruct", "name": "Qwen2-VL-72B", "provider": "SiliconFlow"},
    {"id": "OpenGVLab/InternVL2-Llama3-76B", "name": "InternVL2-Llama3-76B", "provider": "SiliconFlow"},
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "OpenAI"},
]

AVAILABLE_IMAGE_GENERATORS = [
    {"id": "tools.ImageGeneratorSiliconFlowAPI", "name": "SiliconFlow Image", "provider": "SiliconFlow", "class_path": "tools.ImageGeneratorSiliconFlowAPI"},
    {"id": "tools.ImageGeneratorOpenAIAPI", "name": "DALL-E", "provider": "OpenAI", "class_path": "tools.ImageGeneratorOpenAIAPI"},
    {"id": "tools.StableDiffusionAPI", "name": "Stable Diffusion", "provider": "Stability AI", "class_path": "tools.StableDiffusionAPI"},
    {"id": "UnifiedGeneratorImageGenerator", "name": "本地UnifiedGenerator", "provider": "Local", "class_path": "UnifiedGeneratorImageGenerator"},
]

AVAILABLE_VIDEO_GENERATORS = [
    {"id": "tools.LocalVideoGeneratorClientAPI", "name": "Kling Video", "provider": "Kling", "class_path": "tools.LocalVideoGeneratorClientAPI"},
    {"id": "tools.PikaVideoGenerator", "name": "Pika", "provider": "Pika", "class_path": "tools.PikaVideoGenerator"},
    {"id": "tools.RunwayVideoGenerator", "name": "Runway", "provider": "Runway", "class_path": "tools.RunwayVideoGenerator"},
    {"id": "tools.LumaVideoGenerator", "name": "Luma Dream", "provider": "Luma", "class_path": "tools.LumaVideoGenerator"},
]

AVAILABLE_IMAGE_EDITORS = [
    {"id": "tools.ImageEditorSiliconFlowAPI", "name": "SiliconFlow Image Editor", "provider": "SiliconFlow", "class_path": "tools.ImageEditorSiliconFlowAPI"},
    {"id": "tools.ImageEditorOpenAIAPI", "name": "GPT-4o Image Edit", "provider": "OpenAI", "class_path": "tools.ImageEditorOpenAIAPI"},
]


class ModelConfigService:
    """模型配置服务"""
    _instance = None
    _default_config: Optional[GenerationModelConfig] = None
    _episode_configs: Dict[int, GenerationModelConfig] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ModelConfigService, cls).__new__(cls)
            cls._instance._load_default_config()
        return cls._instance
    
    def _load_default_config(self):
        """加载默认配置"""
        config_files = [
            os.path.join(DEFAULT_CONFIG_DIR, 'idea2video_deepseek_veo3_SiliconFlow_image_vace.yaml'),
            os.path.join(DEFAULT_CONFIG_DIR, 'idea2video_deepseek_veo3_SiliconFlow_image.yaml'),
            os.path.join(DEFAULT_CONFIG_DIR, 'idea2video_deepseek_veo3.yaml'),
            os.path.join(DEFAULT_CONFIG_DIR, 'idea2video.yaml'),
        ]
        
        for config_file in config_files:
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config_data = yaml.safe_load(f)
                    
                    self._default_config = GenerationModelConfig.from_dict(config_data)
                    print(f"[ModelConfigService] Loaded default config from: {config_file}")
                    return
                except Exception as e:
                    print(f"[ModelConfigService] Failed to load {config_file}: {e}")
                    continue
        
        print(f"[ModelConfigService] No default config found, using empty config")
        self._default_config = GenerationModelConfig()
    
    @property
    def default_config(self) -> GenerationModelConfig:
        return self._default_config
    
    def get_default_config_dict(self) -> Dict:
        """获取默认配置（字典格式）"""
        return self._default_config.to_dict() if self._default_config else {}
    
    def get_episode_config(self, episode_id: int) -> GenerationModelConfig:
        """获取分集的模型配置，如果没有则返回默认配置"""
        if episode_id in self._episode_configs:
            return self._episode_configs[episode_id]
        
        # 尝试从数据库加载
        from models import Episode
        episode = Episode.query.get(episode_id)
        if episode and episode.generation_config:
            try:
                config_data = json.loads(episode.generation_config)
                if 'model_config' in config_data:
                    return GenerationModelConfig.from_dict(config_data['model_config'])
            except Exception as e:
                print(f"[ModelConfigService] Failed to load episode config: {e}")
        
        return self._default_config or GenerationModelConfig()
    
    def save_episode_config(self, episode_id: int, config: GenerationModelConfig):
        """保存分集的模型配置"""
        self._episode_configs[episode_id] = config
        
        # 同时保存到数据库
        from models import Episode
        episode = Episode.query.get(episode_id)
        if episode:
            try:
                existing_config = {}
                if episode.generation_config:
                    existing_config = json.loads(episode.generation_config)
                
                existing_config['model_config'] = config.to_dict()
                episode.generation_config = json.dumps(existing_config, ensure_ascii=False)
                from __init__ import db
                db.session.commit()
                print(f"[ModelConfigService] Saved model config for episode {episode_id}")
            except Exception as e:
                print(f"[ModelConfigService] Failed to save episode config: {e}")
    
    def get_model_options(self) -> Dict[str, List[Dict]]:
        """获取所有可用的模型选项"""
        return {
            'chat_models': AVAILABLE_CHAT_MODELS,
            'mllm_models': AVAILABLE_MLLM_MODELS,
            'image_generators': AVAILABLE_IMAGE_GENERATORS,
            'video_generators': AVAILABLE_VIDEO_GENERATORS,
            'image_editors': AVAILABLE_IMAGE_EDITORS,
        }
    
    def generate_config_file(self, episode_id: int, output_dir: str) -> str:
        """为分集生成配置文件到指定目录"""
        config = self.get_episode_config(episode_id)
        config_dict = config.to_dict()
        
        # 生成YAML格式的配置文件
        config_path = os.path.join(output_dir, 'generation_config.yaml')
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        print(f"[ModelConfigService] Generated config file: {config_path}")
        return config_path


# 全局实例
model_config_service = ModelConfigService()


# 便捷函数
def get_model_options() -> Dict[str, List[Dict]]:
    """获取可用的模型选项"""
    return model_config_service.get_model_options()

def get_default_model_config() -> Dict:
    """获取默认模型配置"""
    return model_config_service.get_default_config_dict()

def get_episode_model_config(episode_id: int) -> Dict:
    """获取分集的模型配置"""
    return model_config_service.get_episode_config(episode_id).to_dict()

def save_episode_model_config(episode_id: int, config: Dict):
    """保存分集的模型配置"""
    model_config = GenerationModelConfig.from_dict(config)
    model_config_service.save_episode_config(episode_id, model_config)

def generate_config_for_episode(episode_id: int, output_dir: str) -> str:
    """为分集生成配置文件"""
    return model_config_service.generate_config_file(episode_id, output_dir)
