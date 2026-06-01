from openclaw_client import ask_ai

prompt = """
Analyze this business:

Income:
100,000,000

Expense:
40,000,000

Main Expense:
Agrochemical

Sector:
SP Extension

Give:
- business health
- risks
- recommendation
"""

response = ask_ai(prompt)

print(response)
