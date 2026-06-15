import os
import time


def main() -> None:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    print(f"ingestion-worker started, waiting for jobs from {redis_url}", flush=True)
    while True:
        time.sleep(30)


if __name__ == "__main__":
    main()

