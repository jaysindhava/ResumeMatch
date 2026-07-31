import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["app/mcp_servers/ats_tracker_server.py"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Available MCP tools:", [t.name for t in tools.tools])

            print("\n--- Logging a test application ---")
            result = await session.call_tool(
                "log_application",
                arguments={
                    "job_id": "test_job_001",
                    "job_title": "Python Developer",
                    "company": "157 Industries",
                    "tailored_resume_summary": "Rephrased data preprocessing bullet to emphasize pipeline language",
                },
            )
            for block in result.content:
                print(block.text)

            print("\n--- Fetching application history ---")
            result = await session.call_tool("get_application_history", arguments={})
            for block in result.content:
                print(block.text)

            print("\n--- Updating status to 'applied' ---")
            # Note: adjust the id below based on what was printed above if this
            # isn't your first-ever run (ids increment across runs since the
            # database is persistent, matching real ATS behavior)
            result = await session.call_tool("update_status", arguments={"application_id": 1, "new_status": "applied"})
            for block in result.content:
                print(block.text)


if __name__ == "__main__":
    asyncio.run(main())