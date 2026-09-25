from newsbrief.evaluate import evaluate
from newsbrief.models import Article


def art(title, n, src="s"):
    return Article(title, f"https://ex.com/{n}", src, summary=title + ".")


def test_pairwise_precision_recall_and_error_lists():
    rates_a = art("Central bank raises interest rates to fight inflation", 1, "wire")
    rates_b = art("Central bank raises interest rates as inflation bites", 2, "atom")
    quake = art("Earthquake strikes coastal city overnight", 3, "wire")
    quake_b = art("Rescue teams search rubble in flattened villages", 4, "atom")  # same event, no shared words
    other = art("Chip maker unveils faster laptop processor", 5, "hn")
    r = evaluate([(rates_a, "rates"), (rates_b, "rates"), (quake, "quake"), (quake_b, "quake"), (other, None)])
    assert (r.items, r.gold_pairs, r.predicted_pairs, r.correct_pairs) == (5, 2, 1, 1)
    assert r.precision == 1.0 and r.recall == 0.5 and round(r.f1, 3) == 0.667
    assert r.false_merges == [] and [{a.url for a in p} for p in r.misses] == [{quake.url, quake_b.url}]


def test_empty_set_scores_perfectly():
    r = evaluate([])
    assert r.precision == r.recall == 1.0


def test_shipped_eval_set_is_well_formed():
    from collections import Counter

    from newsbrief.evaluate import load_set

    items = load_set()
    assert len(items) >= 150 and len({a.url for a, _ in items}) == len(items)
    sizes = Counter(s for _, s in items if s)
    assert all(n >= 2 for n in sizes.values())  # a label only matters if it pairs something
    # the two known failures from the 2026-09-25 run are encoded
    titles = {a.title: s for a, s in items}
    assert titles["What About Rails?"] is None and titles["Rails World 2026 Opening Keynote [video]"] is None
    medicare = [t for t, s in titles.items() if s == "openai-australia-medicare-hack" and "Medicare" in t]
    assert len(medicare) == 2


def test_snapshot_prelabels_clusters_and_round_trips(tmp_path):
    import json

    from newsbrief.evaluate import evaluate, load_set, snapshot
    from newsbrief.models import Article

    arts = [Article("Central bank raises interest rates", "https://a/1?utm_source=x", "a"),
            Article("Central bank raises interest rates again", "https://b/1", "b"),
            Article("Floods hit northern Italy", "https://c/1", "c")]
    data = snapshot(arts, "2026-09-25")
    assert [(it["story"], it["source"]) for it in data["items"]] == [("c1", "a"), ("c1", "b"), (None, "c")]
    p = tmp_path / "day.json"
    p.write_text(json.dumps(data))
    r = evaluate(load_set(p))
    assert (r.precision, r.recall) == (1.0, 1.0)  # unedited, it agrees with itself by construction
