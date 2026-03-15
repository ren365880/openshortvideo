import asyncio
import logging
import yaml
from tools.wuyinkeji_veo3_veo3_fast_api import VideoGeneratorVeoFastAPI

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


def load_api_key_from_config(config_path="configs/idea2video_deepseek_veo3_fast.yaml"):
    """从配置文件加载API密钥"""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    return config["video_generator"]["init_args"]["api_key"]


async def veo3_with_first_last_frame():
    """
    使用首尾帧生成视频的Demo
    """
    print("=" * 50)
    print("Veo3 API - 使用首尾帧生成视频")
    print("=" * 50)

    # 使用你的API密钥
    API_KEY = load_api_key_from_config()
    print(f"已从配置文件加载API密钥: {API_KEY[:10]}...")

    # 创建视频生成器实例
    video_generator = VideoGeneratorVeoFastAPI(
        api_key=API_KEY,
        poll_interval=10,  # 视频生成需要更长的轮询间隔
        max_poll_attempts=60,  # 最多尝试60次（10分钟）
    )

    try:
        # 方法1：使用图片URL字符串（推荐）
        print("\n方法1：使用图片URL字符串")
        print("-" * 30)

        # 准备首帧和尾帧的图片URL（需要是公开可访问的URL）
        first_frame_url = "https://backend.appmiaoda.com/projects/supabase268304199530360832/storage/v1/object/public/app-8u3vvyt9el8h_images/cd0c9a9a-f88f-4037-ac4d-67787035d7c0/1769909613176_yk7zsu.jpg"  # 替换为真实URL
        last_frame_url = "https://backend.appmiaoda.com/projects/supabase268304199530360832/storage/v1/object/public/app-8u3vvyt9el8h_images/cd0c9a9a-f88f-4037-ac4d-67787035d7c0/1769908440655_zxys9e.jpg"  # 替换为真实URL
        result = await video_generator.generate_single_video(
            prompt="主观/俯瞰镜头，模拟白衣剑仙的视角。镜头从云层上方开始，视线穿透翻腾的白色云层，向下移动，最终锁定下方一处被浓稠、翻涌的黑色雾气完全笼罩的山谷。\n[环境音] 风声减弱，下方山谷传来低沉、不祥的嗡鸣声。",
            model="veo3.1-fast",
            video_type="img2video",  # 必须设置为img2video
            first_frame_image=first_frame_url,  # 首帧图片URL
            last_frame_image=last_frame_url,  # 尾帧图片URL
            ratio="16:9"
        )

        print(f"✓ 视频生成成功!")
        print(f"视频URL: {result}")

    except Exception as e:
        print(f"✗ 方法1失败: {e}")

async def main():
    """
    主函数
    """
    # 先进行快速测试
    #await quick_test()

    # 如果需要测试首尾帧功能，取消下面的注释
    await veo3_with_first_last_frame()


if __name__ == "__main__":
    asyncio.run(main())