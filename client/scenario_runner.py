import asyncio
import contextlib
import logging
import random

from client.load_generator import run_load_test


logger = logging.getLogger("scenario_runner")


async def run_scenario(config, scheduler, load_balancer):
    scenario = config.scenario

    logger.info(
        "event=scenario_start name=%s users=%s concurrency=%s workers=%s",
        scenario,
        config.num_users,
        config.concurrency,
        len(config.worker_urls),
    )

    background_task = None

    if scenario == "random_failures":
        background_task = asyncio.create_task(
            _random_failure_loop(load_balancer, config.failure_rate, config.recovery_time)
        )
    elif scenario == "node_down_recovery":
        background_task = asyncio.create_task(
            _single_node_recovery_loop(
                load_balancer,
                config.node_down_worker_index,
                config.node_down_after_seconds,
                config.node_recovery_after_seconds,
            )
        )
    elif scenario == "all_nodes_down":
        background_task = asyncio.create_task(
            _all_nodes_down_loop(
                load_balancer,
                config.all_nodes_down_after_seconds,
                config.all_nodes_recovery_after_seconds,
            )
        )
    elif scenario != "normal":
        raise ValueError(
            "Unsupported SCENARIO. Use one of: normal, random_failures, node_down_recovery, all_nodes_down"
        )

    try:
        return await run_load_test(
            scheduler,
            load_balancer,
            num_users=config.num_users,
            max_concurrent=config.concurrency,
        )
    finally:
        if background_task is not None:
            background_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await background_task
        load_balancer.recover_all_workers()


async def _random_failure_loop(load_balancer, failure_rate, recovery_time):
    if len(load_balancer.worker_urls) < 2:
        logger.warning(
            "event=scenario_warning name=random_failures reason=single_worker_only"
        )

    while True:
        await asyncio.sleep(2)

        if random.random() > failure_rate:
            continue

        alive_workers = load_balancer.get_alive_workers()
        if len(alive_workers) <= 1:
            continue

        failed_worker = random.choice(alive_workers)
        load_balancer.mark_worker_unhealthy(failed_worker, reason="random_failure", simulated=True)

        await asyncio.sleep(recovery_time)

        load_balancer.recover_worker(failed_worker)


async def _single_node_recovery_loop(load_balancer, worker_index, drop_delay, recovery_delay):
    if not load_balancer.worker_urls:
        return

    worker_index = max(0, min(worker_index, len(load_balancer.worker_urls) - 1))
    target_worker = load_balancer.worker_urls[worker_index]

    await asyncio.sleep(drop_delay)
    load_balancer.mark_worker_unhealthy(target_worker, reason="node_down_recovery", simulated=True)

    if recovery_delay > 0:
        await asyncio.sleep(recovery_delay)
        load_balancer.recover_worker(target_worker)


async def _all_nodes_down_loop(load_balancer, drop_delay, recovery_delay):
    await asyncio.sleep(drop_delay)
    load_balancer.mark_all_workers_unhealthy(reason="all_nodes_down", simulated=True)

    if recovery_delay > 0:
        await asyncio.sleep(recovery_delay)
        load_balancer.recover_all_workers()