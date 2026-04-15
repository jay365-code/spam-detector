import asyncio
from app.utils.excel_handler import ExcelHandler

handler = ExcelHandler()
fake_logs = [
    {
        "message": "test",
        "result": {
            "is_spam": True,
            "semantic_class": "Type_B_something",
            "classification_code": "1",
            "reason": "bad",
            "ibse_signature": "signature_string",
            "ibse_len": 16
        }
    }
]

try:
    handler.generate_excel_from_json(fake_logs, "output.xlsx", False, "test.xlsx")
    print("Success!")
except Exception as e:
    import traceback
    traceback.print_exc()
