
print("Starting debug script...")
try:
    print("Importing app.main...")
    from app.main import app
    print("Successfully imported app.main!")
except Exception as e:
    print(f"Error importing app.main: {e}")
