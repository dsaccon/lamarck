from lamarck import config


def test_default_worker_has_a_price():
    assert config.DEFAULT_WORKER in config.WORKER_MODELS
    pin, pout = config.WORKER_MODELS[config.DEFAULT_WORKER]
    assert pin > 0 and pout > 0


def test_splits_have_counts_and_sizes():
    assert set(config.SPLITS) == {"train", "gate", "long"}
    assert all(n > 0 and lines > 0 for n, lines in config.SPLITS.values())
