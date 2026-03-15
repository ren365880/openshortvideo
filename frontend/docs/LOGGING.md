# 日志管理系统使用说明

## 功能特性

- **双日志存储**: 同时支持文件日志和数据库日志
- **自动轮转**: 日志文件超过50MB自动轮转，保留30天
- **分类管理**: 支持AI调用、用户操作、系统事件等多种分类
- **实时监控**: 记录操作耗时、IP地址、用户信息等详细数据
- **管理界面**: 提供Web界面查看、筛选、导出日志

## 快速开始

### 1. 初始化日志系统

```bash
python init_logs.py
```

这将：
- 创建日志数据库表
- 创建logs目录
- 测试日志记录功能

### 2. 访问日志管理页面

打开浏览器访问：
```
http://localhost:5000/logs
```

## 日志分类

### AI调用日志
自动记录所有AI模型调用：
- 调用时间
- 使用的模型
- 请求和响应内容
- 调用耗时
- 成功/失败状态

**自动记录位置**:
- `api_services/deepseek_api.py` - 所有AI生成方法

### 用户操作日志
记录用户的关键操作：
- 创建项目
- 更新项目
- 删除项目
- 创建/更新/删除分集

**已添加记录位置**:
- `routes/projects.py` - 项目CRUD操作
- `routes/episodes.py` - 分集CRUD操作

### 系统事件日志
记录系统级别的事件和错误

### 错误日志
记录所有异常和错误信息

## 在代码中使用日志

### 1. 导入日志服务

```python
from services.log_service import (
    log_ai_call,      # AI调用日志
    log_user_action,  # 用户操作日志
    log_system_event, # 系统事件日志
    log_error,        # 错误日志
    log_operation,    # 装饰器
    log_ai_operation  # AI专用装饰器
)
```

### 2. 记录AI调用

```python
# 手动记录
log_ai_call(
    action='生成内容',
    model='gpt-4',
    prompt='用户输入',
    response='AI响应',
    duration_ms=1500,
    status='success',
    project_id=1
)

# 或使用装饰器自动记录
@log_ai_operation('gpt-4')
def generate_content(prompt):
    # AI调用逻辑
    return result
```

### 3. 记录用户操作

```python
log_user_action(
    action='创建项目',
    description='创建了新项目: 测试项目',
    level='INFO',
    project_id=1,
    request_data={'title': '测试项目'}
)
```

### 4. 记录错误

```python
try:
    # 可能出错的代码
    risky_operation()
except Exception as e:
    log_error(
        action='数据导入',
        error=e,
        project_id=project_id
    )
```

### 5. 使用装饰器自动记录

```python
from services.log_service import log_operation

@log_operation('用户操作', '更新设置')
def update_settings(data):
    # 业务逻辑
    pass
```

## 日志文件结构

```
logs/
├── app.log              # 主应用日志
├── app.log.1            # 轮转后的日志
├── app.log.2.gz         # 压缩的历史日志
├── ai_calls.log         # AI调用专用日志
├── ai_calls.log.1       # AI日志轮转
└── error.log            # 错误日志
```

## 数据库日志表结构

```sql
CREATE TABLE log_entry (
    id INTEGER PRIMARY KEY,
    level VARCHAR(20),          -- DEBUG/INFO/WARNING/ERROR/CRITICAL
    category VARCHAR(50),       -- 分类
    action VARCHAR(100),        -- 操作名称
    user_id INTEGER,            -- 用户ID
    project_id INTEGER,         -- 项目ID
    episode_id INTEGER,         -- 分集ID
    ip_address VARCHAR(45),     -- IP地址
    user_agent VARCHAR(500),    -- 用户代理
    request_data TEXT,          -- 请求数据(JSON)
    response_data TEXT,         -- 响应数据(JSON)
    error_message TEXT,         -- 错误信息
    duration_ms INTEGER,        -- 耗时(毫秒)
    status VARCHAR(20),         -- success/failed/pending
    metadata TEXT,              -- 元数据(JSON)
    created_at DATETIME         -- 创建时间
);
```

## API接口

### 查看日志列表
```
GET /logs/api/list?page=1&per_page=50&level=INFO&category=AI调用
```

### 查看日志统计
```
GET /logs/api/stats
```

### 清理旧日志
```
POST /logs/api/cleanup
{
    "days": 30
}
```

### 导出日志
```
GET /logs/api/export?start_date=2024-01-01&end_date=2024-01-31
```

## 定时任务

系统会自动执行以下任务：

1. **每天凌晨2点**:
   - 压缩7天前的日志文件
   - 清理30天前的日志（文件和数据库）

## 配置参数

在 `services/log_service.py` 中修改：

```python
MAX_LOG_SIZE = 50 * 1024 * 1024  # 50MB 单个文件大小限制
MAX_LOG_DAYS = 30                  # 30天 保留期限
LOG_BACKUP_COUNT = 10              # 保留10个备份文件
```

## 注意事项

1. 日志文件存储在项目根目录的 `logs/` 文件夹中
2. 数据库日志会永久保留（除非手动清理）
3. 建议定期检查和清理日志以节省磁盘空间
4. AI调用日志会截断过长的提示词和响应（保留前1000字符）

## 故障排查

### 日志没有记录到数据库
- 检查数据库连接是否正常
- 查看控制台是否有错误输出
- 检查 LogEntry 表是否存在

### 日志文件没有生成
- 检查 `logs/` 目录是否有写入权限
- 检查磁盘空间是否充足

### 日志页面无法访问
- 确认已访问 `/logs` 路径
- 检查是否已登录（需要登录权限）
- 查看浏览器控制台是否有JS错误
