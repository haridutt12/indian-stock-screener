"""
Entry point for running individual scheduler jobs from GitHub Actions.
Usage: python -m scripts.run_job <job_name>

Available jobs (mirrors scheduler/jobs.py):
  price_warmup            8:30 AM IST
  pre_market_scan         8:45 AM IST
  intraday_signal_scan    9:30 AM IST
  daily_top3             10:00 AM IST
  midday_update          12:00 PM IST
  closing_update          3:35 PM IST
  post_market_scan        4:00 PM IST
  outcome_tracker         4:30 PM IST
  intraday_refresh        every 5 min 9:15–15:30 IST
"""
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("run_job")

_JOB_MAP = {
    "price_warmup":         "scheduler.jobs.run_price_warmup",
    "pre_market_scan":      "scheduler.jobs.run_pre_market_scan",
    "intraday_signal_scan": "scheduler.jobs.run_intraday_signal_scan",
    "daily_top3":           "scheduler.jobs.run_daily_top3",
    "midday_update":        "scheduler.jobs.run_midday_update",
    "closing_update":       "scheduler.jobs.run_closing_update",
    "post_market_scan":     "scheduler.jobs.run_post_market_scan",
    "outcome_tracker":      "scheduler.jobs.run_outcome_tracker",
    "intraday_refresh":     "scheduler.jobs.run_intraday_refresh",
}


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python -m scripts.run_job <job_name>")
        print(f"Available jobs: {', '.join(_JOB_MAP)}")
        sys.exit(1)

    job_name = sys.argv[1]
    if job_name not in _JOB_MAP:
        logger.error("Unknown job '%s'. Valid jobs: %s", job_name, list(_JOB_MAP))
        sys.exit(1)

    module_path, func_name = _JOB_MAP[job_name].rsplit(".", 1)
    try:
        import importlib
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
    except (ImportError, AttributeError) as e:
        logger.error("Failed to load job '%s': %s", job_name, e)
        sys.exit(1)

    logger.info("Starting job: %s", job_name)
    try:
        func()
        logger.info("Job '%s' completed successfully.", job_name)
    except Exception as e:
        logger.error("Job '%s' failed: %s", job_name, e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
