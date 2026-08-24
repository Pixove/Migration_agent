from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent.chat import ChatSession
from agent.config import ConfigError, load_config
from agent.llm import create_llm_client
from agent.loop import MigrationRunner


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="企业级代码库现代化迁移 Agent"
    )
    parser.add_argument("--source", help="待迁移项目路径")
    parser.add_argument("--output", help="迁移输出路径")
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="配置文件路径，默认 config.yaml",
    )
    parser.add_argument(
        "--docs",
        action="append",
        default=[],
        help="最佳实践文档路径（文件或目录），可多次指定",
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="不使用大模型，使用回退计划",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="跳过人工审批，自动应用所有计划",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="使用对话引导模式确认迁移目标与路径",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return 2

    if args.chat:
        llm = None if args.no_llm else create_llm_client(config.llm)
        try:
            chat_result = ChatSession(config, llm=llm).run()
        except Exception as exc:
            print(f"对话引导失败: {exc}", file=sys.stderr)
            return 1
        config.migration.profile = chat_result.profile
        config.migration.scope = chat_result.scope
        source = chat_result.source
        output = chat_result.output
    else:
        source = args.source or input("请输入待迁移项目路径: ").strip()
        output = args.output or input("请输入迁移输出路径: ").strip()
        if not source or not output:
            print("输入路径与输出路径不能为空", file=sys.stderr)
            return 2
        if not Path(source).is_dir():
            print(f"输入项目不存在或不是目录: {source}", file=sys.stderr)
            return 2

    try:
        runner = MigrationRunner(
            config,
            source,
            output,
            docs=args.docs,
            no_llm=args.no_llm,
            auto_approve=args.auto_approve,
        )
        state = runner.run()
    except Exception as exc:
        print(f"迁移任务失败: {exc}", file=sys.stderr)
        return 1

    print("迁移任务完成")
    print(f"输出目录: {state.output_root}")
    print(f"审计目录: {state.audit_dir()}")
    print(f"计划条目: {len(state.plan_items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
