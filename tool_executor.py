from tool_registry import TOOLS

def execute_tool(tool_name, *args):

    if tool_name not in TOOLS:
        return f"Tool '{tool_name}' not found."

    try:
        result = TOOLS[tool_name](*args)
        return result

    except Exception as e:
        return f"Tool execution error: {str(e)}"
