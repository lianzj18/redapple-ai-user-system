# 红苹果AI用户系统：GitHub + Railway 部署说明

## 1. 本版本包含的 Railway 文件

- `Procfile`
- `railway.json`
- `runtime.txt`
- `.gitignore`
- `.env.example`
- `/healthz` 健康检查接口
- `SECRET_KEY` 环境变量支持
- `DISABLE_FLASH=1` 云端禁用本地串口烧录
- `DATABASE_URL` PostgreSQL 预留配置

## 2. 本地上传到 GitHub

```bash
git init
git add .
git commit -m "init redapple ai user system railway"
git branch -M main
git remote add origin https://github.com/你的用户名/redapple-ai-user-system.git
git push -u origin main
```

## 3. Railway 部署

1. 打开 Railway 控制台。
2. New Project。
3. Deploy from GitHub repo。
4. 选择 `redapple-ai-user-system` 仓库。
5. Railway 会读取 `railway.json` 或 `Procfile` 自动启动。
6. 部署成功后，在 Settings / Networking 中生成 Public Domain。

## 4. Railway 环境变量

在 Railway 项目的 Variables 中添加：

```text
SECRET_KEY=一个足够长的随机字符串
DISABLE_FLASH=1
DEEPSEEK_API_KEY=你的DeepSeek密钥
```

`DATABASE_URL` 是 PostgreSQL 迁移预留项。当前版本默认 SQLite 演示部署；正式多用户长期运行建议迁移 PostgreSQL。

## 5. 自定义域名

在 Railway 的 Networking / Custom Domain 中添加：

```text
app.yourdomain.com
```

然后到域名 DNS 后台按 Railway 提示添加 CNAME 或 A 记录。

## 6. 重要说明：云端烧录限制

Railway 云端容器无法访问用户电脑上的 USB 串口，因此本版本在云端建议设置：

```text
DISABLE_FLASH=1
```

云端保留“生成固件配置”功能；真正烧录建议后续做“红苹果AI本地烧录助手”。

## 7. 本地测试 Railway 启动命令

```bash
python app.py --init-db
uvicorn app:app --host 0.0.0.0 --port 8000
```


## 登录页安全说明

v1.8 起，登录页不再展示默认管理员账号密码。首次部署仍可使用初始化管理员账号登录，
但正式上线前建议修改默认密码。
