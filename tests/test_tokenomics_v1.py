import tokenomics_v1 as t


def test_allocations_sum_to_supply():
    assert sum(t.allocation_table().values()) == t.total_supply()


def test_vesting_boundaries():
    amount = 1000
    start = 1_700_000_000
    cliff = 10
    duration = 100
    assert t.vesting_unlock(amount, start, start + cliff, cliff, duration) == 0
    assert t.vesting_unlock(amount, start, start + cliff + duration, cliff, duration) == amount


def test_reward_never_exceeds_pool():
    reward = t.compute_block_reward({}, remaining_pool=7, epochs_remaining=1)
    assert 0 <= reward <= 7
