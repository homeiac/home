"""Run the optional acceptance rule independently of an open browser tab."""
import json
import logging
import time


def run(store, stop, interval: float = 30) -> None:
    """Apply bounded batches until shutdown; report failures without losing reviews."""
    from .telemetry import get_telemetry
    while not stop.is_set():
        try:
            started=time.monotonic()
            with get_telemetry().stage('background.matching') as span:
                store.matching_pass()
                trace_id=format(span.get_span_context().trace_id,'032x') if span else None
                get_telemetry().emit('matching.finished',duration_seconds=round(time.monotonic()-started,3),
                    trace_id=trace_id,category='background_face_matching')
            store.auto_accept_pass()
        except Exception:
            logging.exception('Automatic acceptance pass failed')
            try:
                with store.lock:
                    value=dict(checked_at=time.time(),error='Automatic acceptance failed; see service logs. Existing labels are retained.')
                    store.db.execute("INSERT INTO pipeline_state VALUES ('auto_accept_status',?,now()) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now()",[json.dumps(value)])
            except Exception:
                logging.exception('Could not record automatic acceptance status')
        if stop.wait(interval):break
