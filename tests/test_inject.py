import numpy as np

from recon.footprints import synthetic_footprints
from recon.inject import build_benchmark
from recon.names import normalize, variant


def _bench(seed=3, n=400):
    return build_benchmark(synthetic_footprints(n, seed=seed), seed=seed)


def test_truth_links_reference_real_parcels():
    b = _bench()
    assert set(b.truth.a_id) <= set(b.A.a_id)
    assert set(b.truth.b_id) <= set(b.B.b_id)


def test_every_non_missing_parcel_is_linked_and_missing_are_not():
    b = _bench()
    linked = set(b.truth.a_id)
    missing = set(b.A[b.A.error_type == "missing"].a_id)
    assert missing and not (missing & linked)
    assert set(b.A.a_id) - missing == linked


def test_split_and_merge_have_one_to_many_links():
    b = _bench()
    sp = b.truth[b.truth.error_type == "split"].groupby("a_id").size()
    mg = b.truth[b.truth.error_type == "merge"].groupby("b_id").size()
    assert (sp == 2).all() and len(sp) > 0
    assert (mg == 2).all() and len(mg) > 0


def test_spurious_revenue_parcels_have_no_truth_link():
    b = _bench()
    sp = set(b.B[b.B.error_type == "spurious"].b_id)
    assert sp and not (sp & set(b.truth.b_id))


def test_benchmark_is_reproducible_for_a_seed():
    a, b = _bench(seed=5), _bench(seed=5)
    assert a.truth.equals(b.truth)
    assert a.B.geometry.geom_equals_exact(b.B.geometry, 1e-9).all()


def test_name_variants_normalise_close_but_not_always_identical():
    rng = np.random.default_rng(0)
    same = sum(normalize(variant("Krishnan Iyer", rng)) == normalize("Krishnan Iyer") for _ in range(200))
    assert same < 100
