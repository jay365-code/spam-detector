import sys
import asyncio
import subprocess

# **CRITICAL FIX**: Force ProactorEventLoop on Windows for Playwright support
if sys.platform == 'win32':
    # This must be set before any async loop is created
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    # Run Uvicorn programmatically
    # equivalent to: uvicorn app.main:app --reload
    print("Starting Uvicorn with WindowsProactorEventLoopPolicy...")
    # NOTE: reload=False is required on Windows with Playwright to ensure the EventLoopPolicy 
    # is correctly inherited/used. Hot reloading spawns subprocesses that reset the policy.
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
