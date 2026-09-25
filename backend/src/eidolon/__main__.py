"""The `eidolon` command: runs the server, and lets the admin manage users and access keys.

    eidolon                          run the server (same as `eidolon serve`)
    eidolon user create <name>       create a user
    eidolon user list
    eidolon key issue <user>         issue an access key; the key is shown only once
    eidolon key list <user>
    eidolon key revoke <key-id>
"""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from eidolon.config import database_path_from_env
from eidolon.store import DuplicateName, NotFound, Store


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command in (None, "serve"):
        _serve()
        return 0

    store = Store(args.db or database_path_from_env())
    try:
        args.run(store, args)
    except (NotFound, DuplicateName) as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        store.close()
    return 0


def _serve() -> None:
    import uvicorn

    from eidolon.app import create_app
    from eidolon.config import Settings

    uvicorn.run(
        create_app(Settings.from_env()),
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )


def _create_user(store: Store, args: argparse.Namespace) -> None:
    store.create_user(args.name)
    print(f"已创建用户 {args.name}")


def _list_users(store: Store, _: argparse.Namespace) -> None:
    for user in store.list_users():
        print(f"{user.name}\t创建于 {user.created_at}")


def _issue_key(store: Store, args: argparse.Namespace) -> None:
    user = store.get_user_by_name(args.user)
    key, secret = store.issue_key(user.id)
    print(f"已为用户 {user.name} 签发访问密钥 {key.id}：")
    print(secret)
    print("密钥只显示这一次，请直接交给用户保存。")


def _list_keys(store: Store, args: argparse.Namespace) -> None:
    user = store.get_user_by_name(args.user)
    for key in store.list_keys(user.id):
        state = f"已吊销于 {key.revoked_at}" if key.revoked_at else "有效"
        print(f"{key.id}\t签发于 {key.created_at}\t{state}")


def _revoke_key(store: Store, args: argparse.Namespace) -> None:
    store.revoke_key(args.key_id)
    print(f"已吊销访问密钥 {args.key_id}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eidolon", description="Eidolon-SC 后端")
    parser.add_argument(
        "--db", type=Path, help="数据库文件（默认取环境变量 EIDOLON_DATABASE_PATH）"
    )
    commands = parser.add_subparsers(dest="command", metavar="命令")
    commands.add_parser("serve", help="启动服务（默认）")

    user = commands.add_parser("user", help="管理用户").add_subparsers(
        dest="action", required=True, metavar="操作"
    )
    create = user.add_parser("create", help="创建用户")
    create.add_argument("name")
    create.set_defaults(run=_create_user)
    user.add_parser("list", help="列出用户").set_defaults(run=_list_users)

    key = commands.add_parser("key", help="管理访问密钥").add_subparsers(
        dest="action", required=True, metavar="操作"
    )
    issue = key.add_parser("issue", help="为用户签发访问密钥")
    issue.add_argument("user")
    issue.set_defaults(run=_issue_key)
    listing = key.add_parser("list", help="列出用户的访问密钥")
    listing.add_argument("user")
    listing.set_defaults(run=_list_keys)
    revoke = key.add_parser("revoke", help="吊销访问密钥")
    revoke.add_argument("key_id")
    revoke.set_defaults(run=_revoke_key)
    return parser


if __name__ == "__main__":
    sys.exit(main())
