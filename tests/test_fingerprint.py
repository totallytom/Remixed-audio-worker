import numpy as np

from audio_worker.fingerprint import find_matches, similarity

rng = np.random.default_rng(7)


def random_fp(n: int = 600) -> list[int]:
    return rng.integers(0, 2**32, size=n, dtype=np.uint64).astype(np.uint32).tolist()


def flip_bits(fp: list[int], fraction: float) -> list[int]:
    """Simulate a re-encode: flip a random `fraction` of the bits."""
    a = np.asarray(fp, dtype=np.uint32)
    bits = np.unpackbits(a.view(np.uint8))
    idx = rng.choice(bits.size, size=int(bits.size * fraction), replace=False)
    bits[idx] ^= 1
    return np.packbits(bits).view(np.uint32).tolist()


def test_identical_is_one():
    fp = random_fp()
    assert similarity(fp, fp) == 1.0


def test_unrelated_is_about_half():
    assert 0.45 < similarity(random_fp(), random_fp()) < 0.6


def test_re_encode_still_matches():
    fp = random_fp()
    assert similarity(fp, flip_bits(fp, 0.05)) > 0.93


def test_extra_intro_is_aligned():
    fp = random_fp()
    with_intro = random_fp(25) + fp          # ~3 s of extra audio at the start
    assert similarity(with_intro, fp) == 1.0


def test_find_matches_filters_and_sorts():
    fp = random_fp()
    candidates = [
        ("unrelated", random_fp()),
        ("close", flip_bits(fp, 0.08)),
        ("exact", fp),
    ]
    hits = find_matches(fp, candidates, threshold=0.85)
    assert [tid for tid, _ in hits] == ["exact", "close"]
