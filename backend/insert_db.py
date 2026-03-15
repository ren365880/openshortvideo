import json
import os
import sqlite3

url_data = {
    "黑袍妖将": {
        "front": {
            "path": "https://backend.appmiaoda.com/projects/supabase268304199530360832/storage/v1/object/public/app-8u3vvyt9el8h_images/cd0c9a9a-f88f-4037-ac4d-67787035d7c0/1769908752875_lq2t36.jpg",
            "description": "A front view portrait of 黑袍妖将."
        },
        "side": {
            "path": "https://backend.appmiaoda.com/projects/supabase268304199530360832/storage/v1/object/public/app-8u3vvyt9el8h_images/cd0c9a9a-f88f-4037-ac4d-67787035d7c0/1769909613176_yk7zsu.jpg",
            "description": "A side view portrait of 黑袍妖将."
        },
        "back": {
            "path": "https://backend.appmiaoda.com/projects/supabase268304199530360832/storage/v1/object/public/app-8u3vvyt9el8h_images/cd0c9a9a-f88f-4037-ac4d-67787035d7c0/1769909559414_w4ujih.jpg",
            "description": "A back view portrait of 黑袍妖将."
        }
    },
    "白衣剑仙": {
        "front": {
            "path": "https://backend.appmiaoda.com/projects/supabase268304199530360832/storage/v1/object/public/app-8u3vvyt9el8h_images/cd0c9a9a-f88f-4037-ac4d-67787035d7c0/1769907741782_rlg1e5.jpg",
            "description": "A front view portrait of 白衣剑仙."
        },
        "side": {
            "path": "https://backend.appmiaoda.com/projects/supabase268304199530360832/storage/v1/object/public/app-8u3vvyt9el8h_images/cd0c9a9a-f88f-4037-ac4d-67787035d7c0/1769908440655_zxys9e.jpg",
            "description": "A side view portrait of 白衣剑仙."
        },
        "back": {
            "path": "https://backend.appmiaoda.com/projects/supabase268304199530360832/storage/v1/object/public/app-8u3vvyt9el8h_images/cd0c9a9a-f88f-4037-ac4d-67787035d7c0/1769908265396_zeq38b.jpg",
            "description": "A back view portrait of 白衣剑仙."
        }
    }
}


def insert_character_images(json_path: str):
    """
    插入角色图片数据到数据库

    Args:
        json_path: JSON文件路径
    """
    try:
        from database import get_db

        # 解析JSON数据
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        # 获取数据库实例
        db = get_db()

        inserted_count = 0
        failed_count = 0

        print("=" * 60)
        print("开始插入图片数据")
        print("=" * 60)

        # 遍历所有角色
        for character_name in data.keys():
            print(f"\n处理角色: {character_name}")

            # 遍历所有视图
            for view_type in data[character_name].keys():
                try:
                    # 获取本地路径（来自第一个JSON）
                    local_path = data[character_name][view_type]["path"]

                    # 获取对应的网络URL（来自url_data）
                    if (character_name in url_data and
                            view_type in url_data[character_name]):
                        image_url = url_data[character_name][view_type]["path"]
                        description = url_data[character_name][view_type]["description"]
                    else:
                        print(f"  ⚠ 角色 {character_name} 的 {view_type} 视图在url_data中不存在")
                        failed_count += 1
                        continue

                    print(f"  [{view_type}]")
                    print(f"    本地路径: {local_path}")
                    print(f"    图片URL: {image_url[:80]}...")

                    # 检查本地文件是否存在（可选）
                    file_exists = os.path.exists(local_path)
                    print(f"    文件存在: {'✓' if file_exists else '✗'}")

                    # 插入数据库（无论文件是否存在都插入）
                    record_id = db.add_image_record(
                        local_path=local_path,
                        image_url=image_url,
                        task_id=f"char_{character_name}_{view_type}",
                        prompt=description,
                        aspect_ratio=""
                    )

                    # 更好的ID检查方式
                    if record_id and record_id > 0:
                        print(f"    ✓ 插入成功，ID: {record_id}")
                        inserted_count += 1

                        # 验证插入是否真的成功
                        try:
                            # 通过ID查询验证
                            record = db.get_image_by_id(record_id)
                            if record:
                                print(f"    ✓ 验证成功，路径: {record.get('local_path', 'N/A')}")
                            else:
                                print(f"    ⚠ 插入成功但查询失败")
                        except Exception as e:
                            print(f"    ⚠ 验证时出错: {e}")
                    else:
                        print(f"    ✗ 插入失败，record_id: {record_id}")

                        # 尝试查询是否已存在
                        try:
                            existing_url = db.get_image_url(local_path)
                            if existing_url:
                                print(f"    ⚠ 记录可能已存在，URL: {existing_url[:80]}...")

                                # 尝试更新
                                success = db.update_image_url(local_path, image_url)
                                if success:
                                    print(f"    ✓ 更新成功")
                                    inserted_count += 1
                                else:
                                    failed_count += 1
                            else:
                                failed_count += 1
                        except Exception as e:
                            print(f"    ⚠ 检查已存在记录时出错: {e}")
                            failed_count += 1

                except Exception as e:
                    print(f"  处理 {character_name}.{view_type} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
                    failed_count += 1

        print("\n" + "=" * 60)
        print(f"插入完成!")
        print(f"成功插入: {inserted_count} 条")
        print(f"失败: {failed_count} 条")
        print("=" * 60)

        return inserted_count

    except Exception as e:
        print(f"插入数据失败: {e}")
        import traceback
        traceback.print_exc()
        return 0


def insertion_with_debug():
    """带调试信息的插入测试"""
    print("开始插入图片数据到数据库")
    print("=" * 60)

    # 你的JSON文件路径
    json_path = "working_dir_idea2video/text_videov2/character_portraits_registry.json"

    # 插入数据
    inserted_count = insert_character_images(json_path)

    print(f"\n插入完成！成功插入了 {inserted_count} 条记录")
    print("=" * 60)

    # 验证数据库内容
    print("\n验证数据库内容:")
    print("-" * 40)
    try:
        from database import get_db
        db = get_db()
        all_images = db.get_all_images()
        print(f"数据库中的总记录数: {len(all_images)}")

        for i, img in enumerate(all_images[:10]):  # 只显示前10条
            print(f"[{i + 1}] ID: {img['id']}")
            print(f"    路径: {img.get('local_path', 'N/A')}")
            print(f"    URL: {img.get('image_url', 'N/A')[:80]}...")
            print()
    except Exception as e:
        print(f"验证数据库时出错: {e}")

if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("开始插入数据")
    print("=" * 60)

    # 然后测试插入
    insertion_with_debug()

    print("\n" + "=" * 60)
    print("修复方法测试")
    print("=" * 60)
