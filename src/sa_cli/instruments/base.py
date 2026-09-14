#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仪器封装：从 JSON 指令集动态生成 SCPI 控制方法，并提供 VISA 会话管理。"""

import json
import logging
import time

import pyvisa

from sa_cli import config
from sa_cli.validation import finite_float

logger = logging.getLogger(__name__)


class Instrument:
    """从 JSON 文件加载 actions，并动态生成控制方法。"""

    def __init__(self, resource_address, json_file, rm=None, dry_run=False, sleep=None):
        self.address = resource_address
        self.dry_run = dry_run
        self._sleep_fn = (lambda _: None) if dry_run else (sleep if sleep is not None else time.sleep)
        self.rm = rm if dry_run else (rm or pyvisa.ResourceManager())
        self.instr = None
        self.actions = self._load_json(json_file)
        self._create_methods()
        if not dry_run:
            self._connect()

    def sleep(self, seconds):
        """使用当前仪器的等待策略；dry-run 永远不等待。"""
        self._sleep_fn(seconds)

    def _load_json(self, json_file):
        json_path = str(json_file)
        try:
            with config.open_data(json_file) as f:
                data = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"JSON 文件不存在: {json_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 解析错误: {e}")

        actions = data.get('actions', {})
        if not isinstance(actions, dict) or not actions:
            raise ValueError(f"JSON 文件缺少有效的 actions 定义: {json_path}")
        logger.info("已加载指令集: %s (%s)", data.get('name', 'Unknown'), json_path)
        return actions

    def _connect(self):
        try:
            self.instr = self.rm.open_resource(self.address)
            self.instr.timeout = 5000
            if 'idn' in self.actions:
                idn_str = self.idn() if hasattr(self, 'idn') else "Unknown"
                logger.info("已连接: %s", idn_str)
            else:
                logger.info("已连接到 %s", self.address)
        except Exception as e:
            raise ConnectionError(f"连接失败 ({self.address}): {e}") from e

    def _create_methods(self):
        for action_name, action_def in self.actions.items():
            commands = action_def.get('commands')
            if not isinstance(commands, list) or not commands:
                raise ValueError(f"action '{action_name}' 缺少有效的 commands 列表")
            args_num = action_def.get('args_num', 0)
            if not isinstance(args_num, int) or args_num < 0:
                raise ValueError(f"action '{action_name}' 的 args_num 必须为非负整数")
            is_query = action_def.get('is_query', False)
            returns = action_def.get('returns', 'float')
            if returns not in ('float', 'str'):
                raise ValueError(f"action '{action_name}' 的 returns 必须为 'float' 或 'str'")

            def make_method(name, cmd_list, num_args, query_flag, returns_type):
                def method(self, *args):
                    if len(args) != num_args:
                        raise TypeError(
                            f"方法 '{name}' 需要 {num_args} 个参数，但传入了 {len(args)} 个"
                        )
                    full_cmds = []
                    for cmd_template in cmd_list:
                        if num_args > 0:
                            if '{' in cmd_template:
                                cmd = cmd_template.format(*args)
                            else:
                                cmd = cmd_template + ' '.join(str(a) for a in args)
                        else:
                            cmd = cmd_template
                        full_cmds.append(cmd)
                    if query_flag:
                        if len(full_cmds) != 1:
                            raise ValueError(f"查询动作 '{name}' 只能包含一条命令")
                        if self.dry_run:
                            logger.info("[DRY-RUN] %s? %s", name, full_cmds[0])
                            if name == 'opc':
                                return 1.0   # OPC 视为立即完成，避免等待循环
                            return '' if returns_type == 'str' else 0.0
                        result = self.instr.query(full_cmds[0]).strip()
                        if returns_type == 'str':
                            return result
                        try:
                            return finite_float(result)
                        except ValueError:
                            raise ValueError(
                                f"查询 '{name}' 返回非数值结果: {result!r}"
                            ) from None
                    else:
                        for cmd in full_cmds:
                            if self.dry_run:
                                logger.info("[DRY-RUN] %s: %s", name, cmd)
                            else:
                                self.instr.write(cmd)
                        return None

                return method

            setattr(
                self, action_name,
                make_method(action_name, commands, args_num, is_query, returns).__get__(self)
            )

    def close(self):
        if self.instr:
            try:
                self.instr.close()
            except Exception:
                pass

    def clear_status(self):
        """清除仪器错误状态和 VISA I/O 缓冲区（用于超时恢复）。"""
        # 1) VISA 总线级 device clear：中止挂起 I/O、丢弃收发缓冲，
        #    不会像逐字节读取那样在空缓冲时阻塞数秒。
        try:
            self.instr.clear()
        except Exception:
            pass
        # 2) *CLS 清仪器侧状态/错误队列
        try:
            self.instr.write("*CLS")
        except Exception:
            pass


