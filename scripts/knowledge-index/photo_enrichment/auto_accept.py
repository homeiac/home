"""Run the optional acceptance rule independently of an open browser tab."""
import json
import logging
import time


def run(store, stop, interval: float = 30) -> None:
    """Apply bounded batches until shutdown; report failures without losing reviews."""
    while not stop.wait(interval):
        try:
            store.auto_accept_pass()
        except Exception:
            logging.exception('Automatic acceptance pass failed')
            try:
                with store.lock:
                    value=dict(checked_at=time.time(),error='Automatic acceptance failed; see service logs. Existing labels are retained.')
                    store.db.execute("INSERT INTO pipeline_state VALUES ('auto_accept_status',?,now()) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()",[json.dumps(value)])
            except Exception:
                logging.exception('Could not record automatic acceptance status')
