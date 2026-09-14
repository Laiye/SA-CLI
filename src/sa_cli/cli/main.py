"""CLI 入口、日志与退出码。"""
import logging

from . import commands
from .parser import build_parser

logger = logging.getLogger(__name__)

def setup_logging(verbose):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
    )


def main(argv=None, *, sleep=None):
    try:
        parser = build_parser()
    except ValueError as exc:
        setup_logging(False)
        logger.error("配置错误: %s", exc)
        return 1
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        return 0

    if args.dry_run:
        logger.info("===== DRY-RUN：不连接仪器，以下为将发送的 SCPI 命令序列 =====")

    try:
        return commands._dispatch(args, sleep=sleep)
    except Exception as e:
        logger.error("程序异常: %s", e)
        logger.debug("详细堆栈:", exc_info=True)
        return 1


