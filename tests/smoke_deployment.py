import argparse
import asyncio
import os
from contextlib import asynccontextmanager

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


URL = "http://127.0.0.1:8765/mcp"


@asynccontextmanager
async def connect(transport):
    if transport == "stdio":
        parameters = StdioServerParameters(
            command="xunji-private-mcp",
            args=["stdio"],
            env={"PATH": os.environ["PATH"], "XUNJI_BODY_KEY": ""},
        )
        async with stdio_client(parameters) as streams:
            yield streams
        return

    async with httpx.AsyncClient(trust_env=False) as http:
        for attempt in range(20):
            try:
                await http.get(URL)
                break
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError):
                if attempt == 19:
                    raise
                await asyncio.sleep(1)

        hostile_host = await http.get(URL, headers={"Host": "untrusted.example"})
        hostile_origin = await http.get(URL, headers={"Origin": "http://untrusted.example"})
        assert hostile_host.status_code == 421, hostile_host.status_code
        assert hostile_origin.status_code == 403, hostile_origin.status_code
        async with streamable_http_client(URL, http_client=http) as (reader, writer, _):
            yield reader, writer


async def smoke(transport):
    async with connect(transport) as (reader, writer), ClientSession(reader, writer) as session:
        initialized = await session.initialize()
        assert initialized.serverInfo.name == "xunji-private-mcp"
        tools = await session.list_tools()
        assert any(tool.name == "query_body_metrics" for tool in tools.tools)
        result = await session.call_tool(
            "query_body_metrics",
            {"start_date": "2026-06-28", "end_date": "2026-06-28"},
        )
        assert result.isError and "XUNJI_BODY_KEY" in str(result.content), result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("transport", choices=("stdio", "http"))
    asyncio.run(asyncio.wait_for(smoke(parser.parse_args().transport), timeout=45))
