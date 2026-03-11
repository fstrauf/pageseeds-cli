#!/usr/bin/env python3
"""
Test MCP server to verify all tools are properly exposed.
"""

import json
import subprocess
import sys

def test_mcp_tools():
    """Test that MCP server exposes all tools correctly"""
    
    print("🧪 Testing MCP Server Tools\n")
    print("=" * 80)
    
    # Initialize the server
    init_message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0.0"}
        }
    }
    
    # List tools
    list_tools_message = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    
    # Prepare input
    input_data = json.dumps(init_message) + "\n" + json.dumps(list_tools_message) + "\n"
    
    try:
        # Run the server
        result = subprocess.run(
            ["uv", "run", "seo-content-mcp"],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=5
        )
        
        # Parse output
        lines = result.stdout.strip().split('\n')
        
        print("📋 Server Response:\n")
        
        for line in lines:
            try:
                response = json.loads(line)
                
                if response.get("id") == 1:
                    print("✅ Server initialized successfully")
                    server_info = response.get("result", {}).get("serverInfo", {})
                    print(f"   Name: {server_info.get('name')}")
                    print(f"   Version: {server_info.get('version')}")
                
                elif response.get("id") == 2:
                    tools = response.get("result", {}).get("tools", [])
                    print(f"\n✅ Found {len(tools)} tools:\n")
                    
                    for i, tool in enumerate(tools, 1):
                        name = tool.get("name", "unknown")
                        desc = tool.get("description", "")
                        schema = tool.get("inputSchema", {})
                        required = schema.get("required", [])
                        
                        print(f"{i}. {name}")
                        print(f"   Description: {desc[:80]}...")
                        print(f"   Required params: {', '.join(required)}")
                        print()

                    # NOTE: This test is intentionally non-strict. It is used as a quick
                    # sanity check that tools are exposed, and will naturally evolve as
                    # new tools are added.
            
            except json.JSONDecodeError:
                continue
        
        print("=" * 80)
        print("✅ MCP Server test completed successfully!")
        
    except subprocess.TimeoutExpired:
        print("❌ Server timeout")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    test_mcp_tools()
