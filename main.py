"""兼容旧入口；推荐使用 sa-cli 或 python -m sa_cli。"""
from sa_cli.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
