__author__ = 'Peter Chapman'

from random import randint

SHORT_TIMEOUT_THRESHOLD = 1

def central_queue(worker_pool: dict, timeouts: list, selected_timeout: float or int):
    for worker_id, worker in worker_pool.items():
        if worker is None:
            return worker_id
    else:
        return None


def tags(worker_pool: dict, timeouts: list, selected_timeout: float or int):
    timeout_idx = timeouts.index(selected_timeout) + 1
    if timeout_idx > len(worker_pool):
        timeout_idx = len(worker_pool)
    return timeout_idx if worker_pool[timeout_idx] is None else None


def express_checkout(worker_pool: dict, timeouts: list, selected_timeout: float or int):
    if selected_timeout < SHORT_TIMEOUT_THRESHOLD:
        return 1 if worker_pool[1] is None else None
    else:
        return central_queue({worker_id: worker for worker_id, worker in worker_pool.items() if worker_id > 1},
                             timeouts, selected_timeout)

def preemptive(worker_pool: dict, timeouts: list, selected_timeout: float or int):
    free_slot = central_queue(worker_pool, timeouts, selected_timeout)
    if free_slot is not None:
        return free_slot
    if selected_timeout < SHORT_TIMEOUT_THRESHOLD:
        return randint(1, len(worker_pool))
    else:
        return None
