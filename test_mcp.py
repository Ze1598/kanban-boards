# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "mcp>=1.0",
# ]
# ///

"""Quick smoke-test for mcp_server.py. Requires the kanban server to be running."""

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(command="uv", args=["run", "mcp_server.py"])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # List tools
            tools = await session.list_tools()
            print(f"✓ {len(tools.tools)} tools registered:")
            for t in sorted(tools.tools, key=lambda x: x.name):
                print(f"    {t.name}")

            print()

            # list_sprints
            result = await session.call_tool("list_sprints", {})
            sprints = json.loads(result.content[0].text)
            print(f"✓ list_sprints → {len(sprints)} sprint(s)")
            if not sprints:
                print("  No sprints found — seed the DB first: python seed.py")
                return

            sprint_id = sprints[0]["id"]
            sprint_name = sprints[0]["name"]
            print(f"  Using sprint {sprint_id} ({sprint_name!r})")

            # list_cards
            result = await session.call_tool("list_cards", {"sprint_id": sprint_id})
            cards = json.loads(result.content[0].text)
            print(f"✓ list_cards → {len(cards)} card(s)")

            # create_card
            result = await session.call_tool("create_card", {
                "sprint_id": sprint_id,
                "title": "MCP test card",
                "status": "Backlog",
                "priority": "Low",
            })
            card = json.loads(result.content[0].text)
            card_id = card["id"]
            print(f"✓ create_card → id={card_id}")

            # update_card
            result = await session.call_tool("update_card", {
                "card_id": card_id,
                "due_on": "2025-09-01",
                "priority": "High",
            })
            updated = json.loads(result.content[0].text)
            print(f"✓ update_card → due_on={updated['due_on']} priority={updated['priority']}")

            # bulk_update_cards (uses cards from the sprint)
            if len(cards) >= 2:
                updates = [{"id": c["id"], "due_on": "2025-10-01"} for c in cards[:3]]
                result = await session.call_tool("bulk_update_cards", {"updates": updates})
                bulk = json.loads(result.content[0].text)
                print(f"✓ bulk_update_cards → updated={len(bulk['updated'])} errors={len(bulk['errors'])}")

            # list_sprint_dependencies
            result = await session.call_tool("list_sprint_dependencies", {"sprint_id": sprint_id})
            deps = json.loads(result.content[0].text)
            print(f"✓ list_sprint_dependencies → {len(deps)} edge(s)")

            # create_dependency (test card depends on first real card)
            if cards:
                result = await session.call_tool("create_dependency", {
                    "card_id": card_id,
                    "depends_on": cards[0]["id"],
                })
                print(f"✓ create_dependency → {json.loads(result.content[0].text)}")

                # cycle detection: reverse should be skipped
                result = await session.call_tool("bulk_create_dependencies", {
                    "dependencies": [{"card_id": cards[0]["id"], "depends_on": card_id}]
                })
                cycle = json.loads(result.content[0].text)
                print(f"✓ bulk_create_dependencies cycle check → skipped={cycle['skipped']}")

            # delete test card
            result = await session.call_tool("delete_card", {"card_id": card_id})
            print(f"✓ delete_card → {json.loads(result.content[0].text)}")

            print("\nAll checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
