from tool_registry import TOOLS

def route_question(question):

    q = question.lower()

    if "profit" in q:
        return TOOLS["calculate_kpi"]()

    if "sector" in q:
        return TOOLS["analyze_business"](question)

    return TOOLS["analyze_business"](question)
