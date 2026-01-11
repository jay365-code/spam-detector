
print("Debug: Starting granular imports...")

try:
    print("Debug: Importing RuleBasedFilter...")
    from app.services.rule_service import RuleBasedFilter
    print("Debug: Instantiating RuleBasedFilter...")
    r = RuleBasedFilter()
    print("Debug: RuleBasedFilter OK!")
except Exception as e:
    print(f"Debug: RuleBasedFilter Error: {e}")

try:
    print("Debug: Importing ExcelHandler...")
    from app.utils.excel_handler import ExcelHandler
    print("Debug: Instantiating ExcelHandler...")
    e = ExcelHandler()
    print("Debug: ExcelHandler OK!")
except Exception as e:
    print(f"Debug: ExcelHandler Error: {e}")

try:
    print("Debug: Importing ContentAnalysisAgent...")
    from app.agents.content_agent.agent import ContentAnalysisAgent
    print("Debug: Instantiating ContentAnalysisAgent...")
    c = ContentAnalysisAgent()
    print("Debug: ContentAnalysisAgent OK!")
except Exception as e:
    print(f"Debug: ContentAnalysisAgent Error: {e}")

try:
    print("Debug: Importing UrlAnalysisAgent...")
    from app.agents.url_agent.agent import UrlAnalysisAgent
    print("Debug: Instantiating UrlAnalysisAgent...")
    u = UrlAnalysisAgent()
    print("Debug: UrlAnalysisAgent OK!")
except Exception as e:
    print(f"Debug: UrlAnalysisAgent Error: {e}")

print("Debug: All checks done.")
