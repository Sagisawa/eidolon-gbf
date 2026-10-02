# 04: 数据库 module：一种连接、一处真删

**What to build:** 新增 `backend/src/eidolon/database.py`。它负责三件事：

- `connect(path)`：同一套 pragma，五个打开数据库的 module 都改用它；
- `USER_DATA`、`NOT_USER_DATA` 两张清单；
- `delete_user_data(db, user_id)`：删号，`Store.delete_user` 委托给它。

`Memories` 因此也打开了 `secure_delete`，顺带修掉 `.scratch/memory-secure-delete/issues/01-memories-secure-delete.md`。背景和取舍见 `../spec-04-database.md`。

**Blocked by:** None (can start immediately)。只改 `backend/`。

**Status:** ready-for-agent

## 已定的设计（2026-10-02 grilling）

- **范围**：统一打开连接、用户数据清单归位、契约测试。schema 和迁移仍由各 module 自己在构造时跑。
- **`connect(path)`**：
  - 建父目录，`check_same_thread=False, timeout=30`，再设 `journal_mode = WAL`、`secure_delete = ON`、`foreign_keys = ON`。
  - 不设 `row_factory`，不改 `isolation_level`。
  - 所有连接都开 `secure_delete`，包括剧情库和向量化文本集。
  - `Store` 的 timeout 从 5 秒变成 30 秒。
- **各 module 仍各持一条连接、各有一把锁**，构造函数签名不变（照旧收 `path`）。不共享连接。
- **两张静态清单在 `database.py`**：
  - `USER_DATA`（表 → where 子句，按删除顺序）：原样搬 `Store._USER_DATA` 的 10 张表；
  - `NOT_USER_DATA`：`episodes`、`episode_cast`、`episode_lines`、`episode_passages`、`embedded_texts`。
  - 不让各 module 构造时登记。
- **`delete_user_data(db, user_id)`**：一个事务里按清单删，表不存在就跳过，再 `wal_checkpoint(TRUNCATE)`。锁由调用方持有；`Store.delete_user` 在自己的锁里用自己的连接调它。`Accounts` 不动。
- **「真删」的边界**写进 `database.py` 的 docstring：
  - 删号是真删，内容覆写、WAL 截掉；
  - 单独删一条记忆、清空记忆会覆写页，但更早的 WAL 帧可能还留着，要等之后的 checkpoint 或删号时才清掉。
- **注释跟着改**：`Store` 的 WAL、`secure_delete` 注释，`UsageLimiter` 的 `secure_delete` 注释，`Memories.forget`、`Accounts.delete` 的 docstring，`_USER_DATA` 旁那句「must be added here」。
- **线上旧页不处理**：不 `VACUUM`，不加命令。
- **不改 `CONTEXT.md`，不写 ADR**。

## 验收

- [ ] **按 TDD**：先写下面的测试，看到它们失败，再改实现。
- [ ] **`test_database.py`（新）**：
  - `connect` 的连接 `journal_mode` 是 `wal`，`secure_delete`、`foreign_keys` 是 1，`busy_timeout` 是 30000；
  - 父目录不存在时会建好。
- [ ] **归类契约测试**：在临时库上打开整套后端，开着记忆和检索，然后断言：
  - 每张不以 `sqlite_` 开头的表，恰好在 `USER_DATA`、`NOT_USER_DATA` 之一；
  - 清单里没有库里不存在的表。
- [ ] **`test_delete_account.py` 新增两条**（memory-secure-delete ticket 01 的复现），照 `test_deleted_data_is_gone_from_the_database_files_too` 的写法：
  - 先清空记忆再删号；
  - 先删一条记忆再删号。

  `CAT` 不在 db 和 `-wal` 的字节里。改实现之前应该是红的；没看到红就如实记下。
- [ ] **防回退**：扫描 `src/eidolon/` 的源码，除了 `database.py` 没有 `sqlite3.connect(`。
- [ ] `Store` 里不再有 `_USER_DATA`、`memories`、`memory_vectors`、`usage` 这些表名；五个 module 里不再自己设 pragma、不再自己 `mkdir`。
- [ ] `backend/` 下 `pytest` 全部通过，`pyright` 0 errors。
- [ ] 完成后 memory-secure-delete ticket 01 追加 Comment 指向这张，标为 resolved。
- [ ] **人工验收（留给用户）**：本地起后端和构建版前端，各项照常；用户验过之后再标 `resolved`。
  - 删一条记忆、清空记忆：记忆页照常更新；
  - 删号：退出登录，用同一身份再登录是一个新用户，记忆、对话、用量都没有了；
  - 通话、文字回合、剧情检索照常（各连接的 pragma 变了，timeout 也变了）。

## Comments
