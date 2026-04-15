import asyncio
from app.agents.history_manager import HistoryManager

def test():
    res = HistoryManager.get_history_paginated(page=1, limit=5, sort_col="count")
    print("History Paginated:", len(res["data"]), "Total:", res["total"])

if __name__ == '__main__':
    test()
