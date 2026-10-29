"""native server 隔离冒烟 —— 不启动 HFSS。

起子进程跑真 stdio,验证:① list_tools 列出核心工具(扩展工具不列);② 无 active design 时调建模工具
干净返回 ok=False/"无 active design";③ stdio 往返无协议污染。
"""

import os
import sys
import json
import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command=sys.executable, args=["hfss_mcp_server.py"], env=dict(os.environ),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = (await session.list_tools()).tools
            names = sorted(t.name for t in tools)
            print(f"[1] list_tools -> {len(names)} 个")
            print("    " + ", ".join(names))
            assert "create_box" in names and "open_desktop" in names and "get_s_parameters" in names

            res = await session.call_tool("create_box", {
                "name": "b1", "position": ["0mm", "0mm", "0mm"], "size": ["1mm", "1mm", "1mm"],
            })
            payload = json.loads(res.content[0].text)
            print(f"[2] create_box(无 design) -> {payload}")
            assert payload.get("ok") is False, "应因无 active design 失败"

            from tools.toolsets import EXTRA_TOOLS
            assert "extra_tools" in names and not EXTRA_TOOLS.keys() & set(names), "扩展工具不该进 tools/list"
            res = await session.call_tool("extra_tools", {"group": "eigenmode"})
            payload = json.loads(res.content[0].text)
            assert payload.get("ok") and [t["name"] for t in payload["tools"]] == ["create_eigenmode_setup", "get_eigenmodes"]
            res = await session.call_tool("extra_tools", {"tool": "assign_mesh_length", "arguments": {"name": "m1"}})
            payload = json.loads(res.content[0].text)
            assert payload.get("ok") is False and "schema" in payload, "缺参数应回 schema"
            print(f"[3] extra_tools:分组说明可取、缺参回 schema({payload['error']})")

            print("[4] stdio 往返无污染")
            print("\nSMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
