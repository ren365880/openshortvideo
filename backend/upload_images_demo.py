import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.upload_image import ImageUploader


def main():
    print("=" * 50)
    print("图片上传示例")
    print("=" * 50)

    # 方式1: 只传图片路径，其他从配置文件加载
    image_path = "my_final_image.png"

    uploader = ImageUploader(
        image_path=image_path,
        config_path="configs/idea2video_deepseek_veo3_fast.yaml"
    )

    print(f"\n配置加载完成:")
    print(f"  - Supabase URL: {uploader.base_url}")
    print(f"  - Bucket: {uploader.bucket_name}")
    print(f"  - 用户名: {uploader.username}")

    # 方式2: 也可以覆盖配置
    title = input("请输入标题 (直接回车使用默认值): ").strip() or None
    description = input("请输入描述 (直接回车使用默认值): ").strip() or None
    category = input("请输入分类 [music/dance/knowledge/comedy/food/travel/game] (直接回车使用默认值 knowledge): ").strip() or None
    tags_input = input("请输入标签，用逗号分隔 (直接回车使用默认值): ").strip()
    tags = [t.strip() for t in tags_input.split(",")] if tags_input else None
    is_public_input = input("是否公开? [y/n] (默认y): ").strip().lower() or "y"
    is_public = is_public_input == "y" if is_public_input else None

    # 覆盖默认值
    if title:
        uploader.title = title
    if description:
        uploader.description = description
    if category:
        uploader.category = category
    if tags:
        uploader.tags = tags
    uploader.is_public = is_public

    print("\n" + "=" * 50)
    print("开始上传图片...")
    print("=" * 50)

    try:
        success = uploader.run()
        if success:
            print("\n" + "=" * 50)
            print("图片上传成功!")
            print("=" * 50)
            print(f"标题: {uploader.title}")
            print(f"分类: {uploader.category}")
            print(f"标签: {uploader.tags}")
            print(f"可见性: {'公开' if uploader.is_public else '私密'}")
            print(f"图片URL: {uploader.file_url}")
        else:
            print("\n上传失败")
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
