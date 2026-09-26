"""The `eidolon` command: runs the server, and lets the admin manage users and access keys.

    eidolon                          run the server (same as `eidolon serve`)
    eidolon user create <name>       create a user
    eidolon user list
    eidolon key issue <user>         issue an access key; the key is shown only once
    eidolon key list <user>
    eidolon key revoke <key-id>
    eidolon story import-csv <dir>   import SCTranslationData story CSVs into the story corpus
                                     and report each character's story catalog
    eidolon story import-json <dir>  the same for the game's own script JSON, filling in what
                                     SCTranslationData lacks
    eidolon story sync               import SCTranslationData, then the card and event episodes
                                     it lacks from the ShinyColorsDB mirror; exits 2 if the
                                     mirror failed
    eidolon character draft-sheet <id>
                                     have the background model draft a character's sheet
                                     from the episodes she is cast in, for review
"""

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from eidolon.config import (
    Settings,
    characters_path_from_env,
    database_path_from_env,
    event_names_path_from_env,
    mirror_cache_path_from_env,
    story_path_from_env,
)
from eidolon.store import DuplicateName, NotFound, Store


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command in (None, "serve"):
        return _serve()
    if args.command == "story" and args.action == "sync":
        return asyncio.run(_sync_story(args))
    if args.command == "story":
        return asyncio.run(_import_story(args))
    if args.command == "character":
        return asyncio.run(_draft_sheet(args))

    store = Store(args.db or database_path_from_env())
    try:
        args.run(store, args)
    except (NotFound, DuplicateName) as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        store.close()
    return 0


def _serve() -> int:
    import uvicorn

    from eidolon.app import create_app
    from eidolon.assembly import build

    try:  # missing settings and a broken character configuration
        settings = Settings.from_env()
        backend = build(settings)
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    try:  # an unfit chat model
        asyncio.run(_check_chat_llm(settings))
    except RuntimeError as e:
        asyncio.run(backend.aclose())
        print(e, file=sys.stderr)
        return 1
    app = create_app(backend)
    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )
    return 0


async def _check_chat_llm(settings: Settings) -> None:
    """Checks the chat model on a client of its own: the server's run in uvicorn's event
    loop, and an HTTP client cannot move between loops."""
    from eidolon.llm.providers import check_chat_llm, open_llm

    llm = open_llm(settings.chat_llm)
    try:
        await check_chat_llm(llm)
    finally:
        await llm.aclose()


async def _import_story(args: argparse.Namespace) -> int:
    from eidolon.characters import load_characters
    from eidolon.config import SiliconFlowSettings
    from eidolon.corpus import StoryCorpus
    from eidolon.embedding import EmbeddingError, SiliconFlowEmbedder
    from eidolon.story_import import import_csv_directory, import_json_directory

    if not args.directory.is_dir():
        print(f"找不到剧情目录 {args.directory}", file=sys.stderr)
        return 1
    try:
        characters = load_characters(args.characters or characters_path_from_env())
        settings = SiliconFlowSettings.from_env()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    embedder = SiliconFlowEmbedder(settings.api_key, settings.embedding_model, settings.base_url)
    try:
        corpus = StoryCorpus(args.db or database_path_from_env(), embedder)
        try:
            import_stories = (
                import_json_directory if args.action == "import-json" else import_csv_directory
            )
            report = await import_stories(args.directory, corpus, characters.values())
            catalogs = {c.name: corpus.catalog(c.id) for c in characters.values()}
        finally:
            corpus.close()
    except EmbeddingError as e:
        print(f"导入中断（已导入的剧情会保留，重新运行即可继续）：{e}", file=sys.stderr)
        return 1
    finally:
        await embedder.aclose()
    for warning in report.warnings:
        print(f"注意：{warning}", file=sys.stderr)
    print(
        f"已导入 {report.imported} 段剧情，跳过 {report.skipped_failures} 段失败结局"
        f"（其中 {report.removed} 段从剧情库移除），新向量化 {report.embedded_passages} 段文本"
    )
    if report.csv_versions_kept:
        print(f"另有 {report.csv_versions_kept} 段剧情已从 CSV 导入（带中文翻译），保留 CSV 版本")
    for name, catalog in catalogs.items():
        episodes = sum(len(source.episodes) for source in catalog)
        print(f"剧情目录 {name}：{len(catalog)} 张卡或活动，{episodes} 段剧情")
    return 0


async def _sync_story(args: argparse.Namespace) -> int:
    from eidolon.characters import load_characters
    from eidolon.config import SiliconFlowSettings
    from eidolon.corpus import StoryCorpus
    from eidolon.embedding import EmbeddingError, SiliconFlowEmbedder
    from eidolon.mirror import Mirror
    from eidolon.story_sync import load_event_names, sync_stories

    story = args.story or story_path_from_env()
    if not story.is_dir():
        print(f"找不到 SCTranslationData 的剧情目录 {story}", file=sys.stderr)
        return 1
    try:
        characters = load_characters(args.characters or characters_path_from_env())
        event_names = load_event_names(
            args.events or event_names_path_from_env(), required=args.events is not None
        )
        settings = SiliconFlowSettings.from_env()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1

    progress = logging.StreamHandler()  # the first sync takes an hour or two
    progress.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    for name in ("eidolon.story_sync", "eidolon.story_import"):
        logging.getLogger(name).addHandler(progress)
        logging.getLogger(name).setLevel(logging.INFO)
    embedder = SiliconFlowEmbedder(settings.api_key, settings.embedding_model, settings.base_url)
    mirror = Mirror()
    try:
        corpus = StoryCorpus(args.db or database_path_from_env(), embedder)
        try:
            report = await sync_stories(
                story,
                args.cache or mirror_cache_path_from_env(),
                corpus,
                characters.values(),
                mirror,
                event_names=event_names,
                idols=args.idol,
            )
        finally:
            corpus.close()
    except EmbeddingError as e:
        print(f"同步中断（已导入的剧情和已下载的剧本会保留，重新运行即可继续）：{e}", file=sys.stderr)
        return 1
    finally:
        await mirror.aclose()
        await embedder.aclose()
    for warning in [*report.translated.warnings, *report.untranslated.warnings]:
        print(f"注意：{warning}", file=sys.stderr)
    translated, untranslated = report.translated, report.untranslated
    print(
        f"汉化版：新增 {translated.added} 段，更新 {translated.imported - translated.added} 段"
        f"（其中 {translated.untranslated_replaced} 段取代了原文剧情），"
        f"跳过 {translated.skipped_failures} 段失败结局（其中 {translated.removed} 段从剧情库移除）"
    )
    print(
        f"原文剧情：下载 {report.downloaded} 个剧本，新增 {untranslated.added} 段，"
        f"更新 {untranslated.imported - untranslated.added} 段；"
        f"本次检查的卡牌中有 {report.translations_kept} 段已有汉化版，保留汉化版"
    )
    if report.missing:
        print(f"卡牌列出的剧本中有 {report.missing} 个镜像上还没有，下次同步再试")
    if report.unnamed_events:
        events = "、".join(f"{event:03d}" for event in report.unnamed_events)
        print(f"活动名对照表里还没有这些活动，暂用「活动剧情 NNN」：{events}")
    print(
        f"共跳过 {report.skipped_failures} 段失败结局，新向量化 {report.embedded_passages} 段文本"
    )
    if report.mirror_error is not None:
        print(
            f"无法从镜像拉取原文剧情（汉化版已照常导入，下次同步会接着拉取）：{report.mirror_error}",
            file=sys.stderr,
        )
        return 2
    return 0


async def _draft_sheet(args: argparse.Namespace) -> int:
    from eidolon.characters import load_characters
    from eidolon.config import LLMSettings
    from eidolon.corpus import StoryCorpus
    from eidolon.embedding import NoEmbedder
    from eidolon.llm import LLMError
    from eidolon.llm.providers import open_llm
    from eidolon.sheet_draft import (
        DEFAULT_BUDGET,
        CannotWrite,
        NoEpisodes,
        SheetReviewed,
        check_output,
        draft_sheet,
    )

    try:
        characters = load_characters(
            args.characters or characters_path_from_env(), require_sheets=False
        )
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1
    character = characters.get(args.character_id)
    if character is None:
        print(f"角色配置里没有 {args.character_id}（有 {'、'.join(characters)}）", file=sys.stderr)
        return 1
    target = args.output or character.sheet_path
    assert target is not None, "characters come from a configuration file"
    budget = args.budget or DEFAULT_BUDGET
    if budget < 1000:
        print("--budget 至少为 1000", file=sys.stderr)
        return 1
    try:  # before anything is spent on it
        path = check_output(target, args.force)
    except SheetReviewed as e:
        print(f"{e}，不会覆盖；确实要重新生成请加 --force", file=sys.stderr)
        return 1
    except CannotWrite as e:
        print(e, file=sys.stderr)
        return 1
    try:
        llm_settings = LLMSettings.background_from_env()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1

    progress = logging.StreamHandler()  # drafting takes minutes; say how far it has got
    progress.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    logging.getLogger("eidolon.sheet_draft").addHandler(progress)
    logging.getLogger("eidolon.sheet_draft").setLevel(logging.INFO)
    llm = open_llm(llm_settings)
    corpus = StoryCorpus(args.db or database_path_from_env(), NoEmbedder())
    try:
        report = await draft_sheet(
            character, corpus, llm, output=path, overwrite=args.force, budget=budget
        )
    except (NoEpisodes, LLMError) as e:
        print(e, file=sys.stderr)
        return 1
    finally:
        corpus.close()
        await llm.aclose()
    sampled = (
        f"（素材太多，均匀抽取了其中 {report.episodes_read} 段）"
        if report.episodes_read < report.episodes_cast
        else ""
    )
    print(
        f"已根据 {character.name} 出场的 {report.episodes_cast} 段剧情{sampled}生成人设初稿，"
        f"共请求后台模型 {report.requests} 次：{path}"
    )
    print("请人工校对，校对完成后删除文件第一行的草稿标记。")
    return 0


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

    story = commands.add_parser("story", help="管理剧情库").add_subparsers(
        dest="action", required=True, metavar="操作"
    )
    import_csv = story.add_parser(
        "import-csv", help="导入 SCTranslationData 格式的剧情 CSV 目录（可重复执行）"
    )
    import_csv.add_argument("directory", type=Path, help="剧情 CSV 所在目录，例如 data/story")
    import_json = story.add_parser(
        "import-json",
        help="导入游戏原始剧本 JSON 目录，补全 SCTranslationData 缺少的剧情（可重复执行）",
    )
    import_json.add_argument(
        "directory",
        type=Path,
        help="剧本 JSON 所在目录；文件路径需含剧本编号，如 produce_events/100100101.json",
    )
    sync = story.add_parser(
        "sync",
        help="导入 SCTranslationData 的汉化版，再从 ShinyColorsDB 镜像补齐缺少的卡牌剧情和活动剧情"
        "（可重复执行；镜像连不上时退出码为 2）",
    )
    sync.add_argument(
        "--story",
        type=Path,
        help="SCTranslationData 的剧情目录（默认取环境变量 EIDOLON_STORY_PATH）",
    )
    sync.add_argument(
        "--cache",
        type=Path,
        help="镜像剧本的本地缓存目录（默认取环境变量 EIDOLON_MIRROR_CACHE_PATH），不要放进仓库",
    )
    sync.add_argument(
        "--idol",
        type=int,
        action="append",
        help="只从镜像同步这位偶像的卡牌，不同步活动剧情（镜像 API 的偶像编号，例如 1 是櫻木真乃），可重复",
    )
    sync.add_argument(
        "--events",
        type=Path,
        help="活动名对照表（默认取环境变量 EIDOLON_EVENT_NAMES_PATH；默认的文件不存在时活动用占位名）",
    )
    for command in (import_csv, import_json, sync):
        command.add_argument(
            "--characters",
            type=Path,
            help="角色配置文件（默认取环境变量 EIDOLON_CHARACTERS_PATH）",
        )

    character = commands.add_parser("character", help="管理角色").add_subparsers(
        dest="action", required=True, metavar="操作"
    )
    draft = character.add_parser(
        "draft-sheet", help="用后台模型根据角色出场的剧情生成人设初稿，写入人设文件"
    )
    draft.add_argument("character_id", help="角色标识，例如 mano")
    draft.add_argument(
        "--characters",
        type=Path,
        help="角色配置文件（默认取环境变量 EIDOLON_CHARACTERS_PATH）",
    )
    draft.add_argument(
        "--output",
        type=Path,
        help="写到这个文件，而不是角色配置里的人设文件（例如在人设目录只读的容器里）",
    )
    draft.add_argument("--force", action="store_true", help="覆盖已经校对过的人设")
    draft.add_argument(
        "--budget",
        type=int,
        help="每次请求后台模型最多带多少字的剧情素材（默认 40000，至少 1000），超出时分批总结",
    )
    return parser


if __name__ == "__main__":
    sys.exit(main())
