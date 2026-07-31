import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["app/mcp_servers/job_search_server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List available tools - confirms the server exposes search_jobs correctly
            tools = await session.list_tools()
            print("Available MCP tools:", [t.name for t in tools.tools])

            # Call the tool for real, through the MCP protocol
            result = await session.call_tool(
                "search_jobs",
                arguments={"title": "backend developer", "location": "Pune", "results": 5},
            )

            print("\n=== MCP TOOL RESULT ===\n")
            for content_block in result.content:
                print(content_block.text)


if __name__ == "__main__":
    asyncio.run(main())