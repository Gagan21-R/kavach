"""Watchman on Render Workflows: check every tracked policy in parallel, each on its own compute with retries.

    python -m app.watchman.workflow        (start command of the Render workflow service)

check_all lists the policies and fans out one check_policy run per policy, at most CC_WATCHMAN_PARALLEL at a time
(default 20). A policy that keeps failing is retried by Render, then counted as an error; it never stops the others.
The cron job starts check_all every 6 hours (see app.watchman.cron).
"""
import asyncio
import os

from render import Retry, TaskContext, Workflows

from app.watchman import cron

app = Workflows(default_retry=Retry(max_retries=2, wait_duration_ms=2000, backoff_scaling=2.0))


@app.task(timeout_seconds=120)
def check_policy(ctx: TaskContext, policy_id: str) -> list[str]:
    return cron.check_one(policy_id)


@app.task(timeout_seconds=3600)
async def check_all(ctx: TaskContext) -> dict:
    limit = asyncio.Semaphore(max(1, int(os.environ.get("CC_WATCHMAN_PARALLEL", "20"))))

    async def one(pid: str) -> list[str]:
        async with limit:
            try:
                return await ctx.run(check_policy, pid)
            except Exception:  # retries exhausted
                return ["errors"]

    ids = cron.policy_ids()
    return {"policies": len(ids), **cron.tally(await asyncio.gather(*(one(pid) for pid in ids)))}


if __name__ == "__main__":
    app.start()
