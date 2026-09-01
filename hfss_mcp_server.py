"""HFSS Agent —— MCP server 入口(native COM 版)。

跟 gRPC 版同壳:stdio + 数据驱动 registry + dispatch 透传 + stdout 隔离。
区别:ctx 持有 win32com 的 COM 句柄(oDesktop/oProject/oDesign/oEditor),连接走原生 API,跨版本。
"""

import sys
import os
import io
import json
import atexit

# ── stdout 即协议:在 import tools 之前隔离(同 gRPC 版) ──
_real_stdout_fd = os.dup(1)
os.dup2(2, 1)
sys.stdout = sys.stderr

# 确认机制改道:stdio 下 input() 抢 stdin,关掉进程内硬确认,交给 Claude Code 权限系统
os.environ["HFSS_AGENT_AUTOCONFIRM"] = "1"

import anyio
import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor

import pythoncom
from mcp.server import Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from tools import dispatch, get_schemas, NO_COM_REQUIRED
from model_state import ModelState
import trace


# ── 单一常驻 ctx:整个进程生命周期内持有 COM 句柄 ──
ctx = {
    "app": None,
    "oDesktop": None,
    "oProject": None,
    "oDesign": None,
    "oEditor": None,
    "project_name": None,
    "design_name": None,
    "version": None,
    "state": ModelState(),
}

# ── COM 专用线程 ──
# 所有 COM 调用必须在**创建句柄的那个公寓线程**上发生(否则 RPC_E_WRONG_THREAD)。
# max_workers=1 保证始终是同一个线程(空闲时阻塞在任务队列上,不会被回收重建),
# initializer 在该线程上跑一次 CoInitialize。这样事件循环全程空闲:
# analyze 跑几分钟期间,ping / tools/list / 新请求照样有响应,客户端不会误判 server 死了。
_COM_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hfss-com",
                               initializer=pythoncom.CoInitialize)

server = Server("hfss-agent-native")


@server.list_tools()
async def list_tools():
    tools = []
    for s in get_schemas():
        fn = s["function"]
        tools.append(types.Tool(
            name=fn["name"],
            description=fn.get("description", ""),
            inputSchema=fn.get("parameters", {"type": "object", "properties": {}}),
        ))
    return tools


@server.call_tool()
async def call_tool(name, arguments):
    args = arguments or {}
    try:
        if name in NO_COM_REQUIRED:
            result = dispatch(name, args, ctx)          # 纯本地,直接在事件循环上跑
        else:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                _COM_POOL, functools.partial(dispatch, name, args, ctx))
    except Exception as e:
        result = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]


def _release():
    """退出时只清进程内引用,不主动关用户的 HFSS(COM 连接随进程退出自然断开)。
    清引用会触发 COM Release,必须回到创建句柄的那个线程上做,别跨公寓。"""
    def _clear():
        for k in ("app", "oDesktop", "oProject", "oDesign", "oEditor"):
            ctx[k] = None
    try:
        _COM_POOL.submit(_clear).result(timeout=5)
    except Exception:
        pass
    _COM_POOL.shutdown(wait=False)


atexit.register(_release)


async def main():
    trace.init_session(model="mcp-native-stdio")
    transport_stdout = anyio.wrap_file(
        io.TextIOWrapper(os.fdopen(_real_stdout_fd, "wb", buffering=0), encoding="utf-8")
    )
    async with stdio_server(stdout=transport_stdout) as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    anyio.run(main)
