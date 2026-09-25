# Eidolon-SC

和《偶像大师 闪耀色彩》的偶像实时对话的 AI 分身系统，供自己和小圈子使用。术语见 `CONTEXT.md`，规划见 `.scratch/mvp/`。

## 启动

```sh
cp .env.example .env   # 填写对话模型的地址、密钥和模型名
# 准备人设文件，见下方「角色」
docker compose up --build
```

打开 http://localhost:3000 ，在设置页填入访问密钥后即可在角色选择页挑一位角色对话。

## 角色

角色由 `characters/characters.toml` 配置：标识、显示名、简介、Fish Audio 音色 ID、人设文件和头像的位置。新增角色或替换音色 ID 只需要改这个文件，然后重启后端。

人设文件和头像不进仓库（ADR-0003）。启动前参照 `characters/sheets/example.md` 写好 `characters/sheets/mano.md` 和 `characters/sheets/kogane.md`；头像（可选）放在 `characters/avatars/` 下。缺少人设文件时后端会拒绝启动并指出缺哪一份。docker compose 会把 `characters/` 只读挂载进后端容器。

## 用户与访问密钥

管理员用命令行管理用户和访问密钥。一位用户可以持有多把密钥，对话记录属于用户本身；吊销一把密钥不影响用户的数据。

```sh
docker compose exec backend eidolon user create alice    # 创建用户
docker compose exec backend eidolon key issue alice      # 签发密钥（只显示这一次）
docker compose exec backend eidolon key list alice       # 查看密钥编号和状态
docker compose exec backend eidolon key revoke <密钥编号>  # 吊销
```

本地开发时用 `uv run eidolon --db data/eidolon.db ...`。01 阶段遗留的默认用户名为 `default`，为它签发密钥即可继续访问原有对话。

## 开发

后端（Python，`backend/`）：

```sh
cd backend
uv sync
uv run pytest        # 测试
uv run pyright       # 类型检查
CHAT_LLM_BASE_URL=... CHAT_LLM_API_KEY=... CHAT_LLM_MODEL=... uv run eidolon   # 启动在 :8000，读取 ../characters/characters.toml（可用 EIDOLON_CHARACTERS_PATH 覆盖）
```

前端（Next.js，`frontend/`）：

```sh
cd frontend
npm install
BACKEND_URL=http://localhost:8000 npm run dev   # 启动在 :3000，/api/* 转发给后端
npm run typecheck
```
