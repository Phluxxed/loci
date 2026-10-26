"""Fixed R0.6 consumer policy, derived solely from delivered node identities."""

MAX_FOCUSED_CALLS = 4


def next_proof_query(packets: list[dict], asked: list[str]) -> str | None:
    for envelope in packets:
        packet = envelope.get("structuredContent", envelope)
        if packet.get("policy") not in {
            "demand-semantic-v1", "focused-semantic-v1", "focused-semantic-wide-v1"
        }:
            continue
        nodes = {node["id"]: node for node in packet["nodes"]}
        identities = [anchor["node_id"] for anchor in packet["anchors"]]
        identities.extend(node["id"] for node in packet["nodes"])
        for identity in identities:
            node = nodes.get(identity)
            if node and node["kind"] not in {"file", "crate", "package"} and identity not in asked:
                return identity
    return None
