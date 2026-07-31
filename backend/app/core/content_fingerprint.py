from hashlib import sha256


def ordered_content_fingerprint(content_hashes: list[str]) -> str:
    normalized_hashes = [value.strip() for value in content_hashes if value.strip()]
    if not normalized_hashes:
        return ""
    digest = sha256()
    for content_hash in normalized_hashes:
        digest.update(content_hash.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()
