"""Keep automatic scans disabled until reference selection and validation finish."""
import asyncio
import os
import sys

sys.path.insert(0, '/app')
import main
import uvicorn


async def wait_for_enrollment() -> None:
    """Leave manual UI/API scans available while the automatic poller is disabled."""
    while True:
        await asyncio.sleep(3600)


if os.environ.get('AUTOMATIC_SCANS', 'false').lower() != 'true':
    main.polling_loop = wait_for_enrollment

uvicorn.run(main.app, host='0.0.0.0', port=8000, timeout_keep_alive=120)
