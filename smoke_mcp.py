"""native server 隔离冒烟 —— 不启动 HFSS。

起子进程跑真 stdio,验证:① list_tools 列出全部工具;② 无 active design 时调建模工具
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

            print("[3] stdio 往返无污染")
            print("\nSMOKE OK")


if __name__ == "__main__":
    asyncio.run(main())
