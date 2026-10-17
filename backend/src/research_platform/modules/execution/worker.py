import argparse
import json
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

from research_platform.core.config import Settings
from research_platform.core.database import make_engine

from .service import claim_job, finish_job


def run_once(session: Session) -> bool:
    lease = claim_job(session)
    if lease is None:
        return False
    # Only a bounded infrastructure diagnostic is registered in the starter.
    # Real research needs heartbeat/cancellation/Run integration before registration.
    if lease.job_type == "system.check":
        try:
            session.execute(text("SELECT 1"))
            accepted = finish_job(session, lease, {"database": "reachable"})
        except Exception:
            session.rollback()
            accepted = finish_job(session, lease, None, "DIAGNOSTIC_FAILED")
    else:
        accepted = finish_job(session, lease, None, "HANDLER_NOT_REGISTERED")
    print(json.dumps({"job_id": lease.job_id, "completion_accepted": accepted}), flush=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the bounded diagnostic worker")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    settings.require_development_release()
    engine = make_engine(settings.database_url.get_secret_value())
    try:
        while True:
            with Session(engine) as session:
                did_work = run_once(session)
            if args.once:
                break
            if not did_work:
                time.sleep(2)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
