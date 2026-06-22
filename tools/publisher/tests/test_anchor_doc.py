from locksmith_publisher.anchor_doc import build_publisher_anchor


def test_build_publisher_anchor_shape():
    doc = build_publisher_anchor(
        publisher_aid="EpubAID000000000000000000000000000000000000",
        witness_oobis=[f"https://w{i}.example.com/oobi/Bw{i}/witness" for i in range(5)],
        toad=3,
    )
    assert doc == {
        "publisher_aid": "EpubAID000000000000000000000000000000000000",
        "embedded_kel_sn": 0,
        "embedded_kel_hash": "EpubAID000000000000000000000000000000000000",
        "toad": 3,
        "witness_oobis": [f"https://w{i}.example.com/oobi/Bw{i}/witness" for i in range(5)],
    }
