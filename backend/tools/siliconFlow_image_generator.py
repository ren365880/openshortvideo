import logging
import asyncio
import requests
import json
import os
from datetime import datetime
from typing import List, Optional, Dict, Any
from PIL import Image
from io import BytesIO
from tenacity import retry, stop_after_attempt
from interfaces.image_output import ImageOutput
from utils.retry import after_func
from utils.rate_limiter import RateLimiter
from database import get_db  # 保留数据库导入以便未来扩展

# 配置logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(),
    ]
)


class ImageGeneratorSiliconFlowAPI:
    """
    使用 SiliconFlow API 生成图像的异步类。
    支持多种模型，直接生成图像URL。
    """

    def __init__(
            self,
            api_key: str,
            rate_limiter: Optional[RateLimiter] = None,
            base_url: str = "https://api.siliconflow.cn/v1/images/generations",
            default_model: str = "Kwai-Kolors/Kolors",
            default_image_size: str = "1024x1024",
    ):
        """
        初始化 SiliconFlow 图像生成器。

        Args:
            api_key: SiliconFlow API密钥。
            rate_limiter: 可选的速率限制器。
            base_url: SiliconFlow API的基础URL。
            default_model: 默认使用的模型。
            default_image_size: 默认图像尺寸。
        """
        self.api_key = api_key
        self.rate_limiter = rate_limiter
        self.base_url = base_url
        self.default_model = default_model
        self.default_image_size = default_image_size
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # 初始化数据库连接（保留原有逻辑）
        try:
            self.db = get_db()
            logging.info("数据库连接成功初始化")
        except Exception as e:
            logging.warning(f"数据库连接初始化失败: {e}")
            self.db = None

    async def _get_image_url_from_local_path(self, local_path: str) -> Optional[str]:
        """
        从本地路径获取图片URL（保留原有逻辑，用于未来扩展）。
        当前SiliconFlow API可能不支持参考图片，但保留方法以备后用。
        """
        # 由于当前SiliconFlow API可能不支持图片上传作为参考，
        # 这里保留原有逻辑但返回None，未来扩展时可用
        logging.debug(f"SiliconFlow API暂不支持本地图片参考，忽略路径: {local_path}")
        return None

    @retry(stop=stop_after_attempt(3), after=after_func)
    async def generate_single_image(
            self,
            prompt: str,
            reference_image_paths: List[str] = [],
            aspect_ratio: Optional[str] = None,
            model: Optional[str] = None,
            seed: Optional[int] = None,
            image_size: Optional[str] = None,
            **kwargs,
    ) -> ImageOutput:
        """
        异步生成单张图像的核心方法。

        Args:
            prompt: 图像描述提示词。
            reference_image_paths: 参考图像本地路径列表（当前API可能不支持）。
            aspect_ratio: 宽高比（如"16:9"，当前API使用具体尺寸）。
            model: 使用的模型名称。
            seed: 随机种子。
            image_size: 图像尺寸（如"1024x1024"）。
            **kwargs: 其他参数（如negative_prompt等）。

        Returns:
            ImageOutput: 包含PIL图像对象的输出。

        Raises:
            ValueError: 当生成失败时抛出。
            requests.RequestException: 当网络请求失败时抛出。
        """
        logging.info(f"调用 SiliconFlow API 生成图像，提示词: {prompt[:50]}...")
        logging.info(f"====================入参===========================")
        logging.info(f"====model=={model}")
        logging.info(f"====seed=={seed}")
        logging.info(f"====image_size=={image_size}")
        logging.info(f"====kwargs=={kwargs}")
        logging.info(f"====================入参===========================")

        # 处理参考图片路径（如果支持的话）
        reference_urls = []
        if reference_image_paths:
            for path in reference_image_paths:
                url = await self._get_image_url_from_local_path(path)
                if url:
                    reference_urls.append(url)
                else:
                    logging.warning(f"无法获取参考图片URL: {path}")

        # 生成图像
        try:
            image_url = await self._generate_image_direct(
                prompt=prompt,
                model=model,
                seed=seed,
                image_size=image_size,
                **kwargs
            )

            # 下载图像并转换为PIL Image
            pil_image = await self._download_image(image_url, prompt)

            # 保存图像到本地（可选）
            await self._save_image_to_disk(pil_image, prompt, image_url)

            return ImageOutput(fmt="pil", ext="png", data=pil_image, image_url=image_url)

        except Exception as e:
            logging.error(f"图像生成失败: {e}", exc_info=True)
            raise

    async def _generate_image_direct(
            self,
            prompt: str,
            model: Optional[str] = None,
            seed: Optional[int] = None,
            image_size: Optional[str] = None,
            **kwargs,
    ) -> str:
        """
        直接调用SiliconFlow API生成图像并返回URL。

        Args:
            prompt: 提示词
            model: 模型名称
            seed: 随机种子
            image_size: 图像尺寸
            **kwargs: 其他参数（如negative_prompt, num_inference_steps等）

        Returns:
            str: 生成的图片URL
        """
        # 准备请求数据
        data = {
            "model": model or self.default_model,
            "prompt": prompt,
            "image_size": image_size or self.default_image_size,
        }

        # 可选参数
        if seed is not None:
            data["seed"] = seed

        # 其他可选参数
        optional_params = ["negative_prompt", "num_inference_steps", "guidance_scale"]
        for param in optional_params:
            if param in kwargs:
                data[param] = kwargs[param]

        # 如果提供了aspect_ratio，尝试转换为image_size
        if "aspect_ratio" in kwargs and kwargs["aspect_ratio"]:
            aspect_ratio = kwargs["aspect_ratio"]
            # 将宽高比转换为具体尺寸
            size_mapping = {
                "1:1": "1024x1024",
                "16:9": "1024x576",
                "9:16": "576x1024",
                "4:3": "1024x768",
                "3:4": "768x1024",
            }
            if aspect_ratio in size_mapping:
                data["image_size"] = size_mapping[aspect_ratio]
                logging.info(f"将宽高比 {aspect_ratio} 转换为尺寸 {data['image_size']}")

        logging.info(f"发送请求到 SiliconFlow API，数据: {json.dumps(data, ensure_ascii=False, indent=2)}")

        # 应用速率限制
        if self.rate_limiter:
            await self.rate_limiter.acquire()

        # 发送请求
        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    self.base_url,
                    headers=self.headers,
                    json=data,
                    timeout=60  # 60秒超时
                )
            )
        except requests.exceptions.RequestException as e:
            logging.error(f"API请求失败: {e}")
            raise

        # 处理响应
        if response.status_code != 200:
            logging.error(f"API请求失败，状态码: {response.status_code}, 响应: {response.text}")
            raise ValueError(f"API请求失败: {response.status_code} - {response.text}")

        try:
            result = response.json()
            logging.debug(f"API响应: {json.dumps(result, ensure_ascii=False, indent=2)}")

            if "images" in result and len(result["images"]) > 0:
                image_info = result["images"][0]
                if "url" in image_info:
                    image_url = image_info["url"]
                    logging.info(f"图像生成成功，URL: {image_url}")
                    print(f"[OK] 图像生成成功! URL: {image_url}")
                    return image_url
                else:
                    # 有些API可能直接返回base64编码的图像
                    if "b64_json" in image_info:
                        logging.info("API返回base64编码的图像")
                        # 这里可以添加base64解码逻辑
                        raise NotImplementedError("Base64格式的图像暂未实现")
            else:
                error_msg = result.get("error", {}).get("message", "未知错误")
                logging.error(f"API返回错误: {error_msg}")
                raise ValueError(f"图像生成失败: {error_msg}")

        except json.JSONDecodeError as e:
            logging.error(f"JSON解析失败: {e}, 响应内容: {response.text[:200]}")
            raise ValueError(f"API响应格式错误: {e}")

    async def _download_image(self, image_url: str, prompt: str) -> Image.Image:
        """
        异步：从给定的URL下载图像并转换为PIL Image对象。
        """
        logging.info(f"开始下载图像: {image_url}")
        print(f"开始下载图像: {image_url}")

        loop = asyncio.get_event_loop()
        try:
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(image_url, stream=True, timeout=30)
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"下载图像失败: {e}")
            print(f"[ERROR] 下载图像失败: {e}")
            raise

        # 将响应内容读取到内存并转换为PIL Image
        image_data = BytesIO()
        for chunk in response.iter_content(chunk_size=8192):
            image_data.write(chunk)
        image_data.seek(0)

        try:
            pil_image = Image.open(image_data)
            # 确保图像是RGB模式
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            print(f"[OK] 图像下载成功! 尺寸: {pil_image.size}")
            return pil_image
        except Exception as e:
            logging.error(f"图像解码失败: {e}")
            print(f"[ERROR] 图像解码失败: {e}")
            raise

    async def _save_image_to_disk(self, image: Image.Image, prompt: str, image_url: str):
        """
        异步：将PIL图像保存到本地目录。
        """
        try:
            # 创建保存目录
            os.makedirs("generated_images", exist_ok=True)

            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # 简化提示词用于文件名
            safe_prompt = "".join(
                c for c in prompt[:30] if c.isalnum() or c in (' ', '-', '_')
            ).rstrip()
            safe_prompt = safe_prompt.replace(' ', '_') if safe_prompt else "image"

            # 从URL中提取文件名或使用哈希
            import hashlib
            url_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]

            filename = f"generated_images/siliconflow_{timestamp}_{url_hash}_{safe_prompt}.png"

            # 保存图像
            image.save(filename, "PNG")
            logging.info(f"图像已保存至: {filename}")
            print(f"[OK] 图像已保存至: {filename}")

            # 保存到数据库（如果可用）
            if self.db and hasattr(self.db, 'add_image'):
                try:
                    self.db.add_image(
                        local_path=os.path.abspath(filename),
                        upload_url=image_url,
                        metadata={
                            "source": "siliconflow",
                            "prompt": prompt,
                            "timestamp": timestamp
                        }
                    )
                    logging.info(f"图像信息已保存到数据库")
                except Exception as db_error:
                    logging.warning(f"保存到数据库失败: {db_error}")

        except Exception as e:
            logging.warning(f"保存图像到磁盘时发生错误（不影响返回）: {e}")
            print(f"[WARNING] 保存图像到磁盘时发生错误（不影响返回）: {e}")

    async def generate_batch_images(
            self,
            prompts: List[str],
            model: Optional[str] = None,
            seed: Optional[int] = None,
            image_size: Optional[str] = None,
            **kwargs,
    ) -> List[ImageOutput]:
        """
        批量生成多张图像。

        Args:
            prompts: 多个提示词列表
            model: 模型名称
            seed: 随机种子
            image_size: 图像尺寸
            **kwargs: 其他参数

        Returns:
            List[ImageOutput]: 多张图像输出列表
        """
        tasks = []
        for i, prompt in enumerate(prompts):
            # 为每张图片设置不同的种子（如果未指定）
            current_seed = seed + i if seed is not None else None
            task = self.generate_single_image(
                prompt=prompt,
                model=model,
                seed=current_seed,
                image_size=image_size,
                **kwargs
            )
            tasks.append(task)

        # 并行执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理结果
        outputs = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logging.error(f"第 {i + 1} 张图像生成失败: {result}")
                print(f"[ERROR] 第 {i + 1} 张图像生成失败: {result}")
            else:
                outputs.append(result)
                print(f"[OK] 第 {i + 1} 张图像生成成功")

        return outputs


# 示例使用代码
async def main():
    # 1. 实例化生成器
    api_key = "xxxxxxxxxxxxxxx"  # 替换为您的API密钥
    image_generator = ImageGeneratorSiliconFlowAPI(
        api_key=api_key,
        default_model="Kwai-Kolors/Kolors",
        default_image_size="1024x1024",
    )

    # 2. 准备参数
    prompt_text = "一只在星空下看书的小猫，卡通风格"

    try:
        # 3. 调用异步方法生成图像
        print("开始生成图像...")
        result = await image_generator.generate_single_image(
            prompt=prompt_text,
            model="Kwai-Kolors/Kolors",  # 可以覆盖默认模型
            seed=42,  # 固定种子以获得可重现的结果
            image_size="1024x1024",
            negative_prompt="模糊, 低质量",  # 可选：负面提示词
        )

        # 4. 获取结果
        pil_image = result.data  # PIL.Image对象
        image_url = result.image_url  # 图片URL
        print(f"图像生成成功！尺寸: {pil_image.size}")
        print(f"图片URL: {image_url}")

        # 显示图片
        # pil_image.show()

        # 批量生成示例
        # prompts = ["风景画", "肖像画", "抽象艺术"]
        # batch_results = await image_generator.generate_batch_images(prompts)

    except ValueError as e:
        print(f"生成失败: {e}")
    except Exception as e:
        print(f"发生未知错误: {e}")


# 运行异步主函数
if __name__ == "__main__":
    asyncio.run(main())