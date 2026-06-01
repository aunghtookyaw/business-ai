from tools.openclaw_client import ask_ai
from tool_executor import execute_tool

SYSTEM_PROMPT = """
You are an AI business agent.

Available tools:

1. analyze_business
2. calculate_kpi
3. get_transactions
4. forecast_business
5. top_expenses
6. query_database

Database schema:

Schema:
"pipkgfu2wr9qxyy"

Table:
"Transection"

Important columns:
"Date"
"Income_Expense"
"Categorization"
"Sector"
"Item_Description"
"Amount"
"Payment_Method"

Use exact PostgreSQL quoted names.

If a tool is needed,
reply ONLY like this:

TOOL: tool_name:argument

You may call multiple tools.

Examples:

TOOL: analyze_business
TOOL: forecast_business
TOOL: top_expenses:5
TOOL: query_database:SELECT * FROM "pipkgfu2wr9qxyy"."Transection" LIMIT 5
"""

while True:

    user_input = input("Ask AI > ")

    ai_response = ask_ai(
        SYSTEM_PROMPT + "\n\nUser: " + user_input
    )

    print("\nAI Decision:")
    print(ai_response)

    if "TOOL:" in ai_response:

        tool_lines = []

        for line in ai_response.splitlines():

            if "TOOL:" in line:
                tool_lines.append(line)

        all_results = []

        for t in tool_lines:

            tool_data = t.replace(
                "TOOL:",
                ""
            ).strip()

            parts = tool_data.split(":")

            tool_name = parts[0]

            tool_arg = ""

            if len(parts) > 1:
                tool_arg = parts[1]

            result = execute_tool(
                tool_name,
                tool_arg
            )

            all_results.append(
                f"{tool_name}:\n{result}"
            )

        combined_results = "\n\n".join(all_results)

        final_prompt = f"""
You are an executive business analyst.

IMPORTANT:

Always include REAL RAW TOOL RESULTS first.

User Question:

{user_input}

Tool Results:

{combined_results}

FIRST:

Show exact raw database/tool outputs.

THEN provide:

1. Executive Summary

2. Key Risks

3. Important Insights

4. Recommended Actions

5. Final Conclusion

Do NOT hide raw data.

Do NOT summarize away SQL results.

"""
        final_answer = ask_ai(final_prompt)

        print("\nFINAL EXECUTIVE ANALYSIS:\n")

        print(final_answer)

    print("\n")
