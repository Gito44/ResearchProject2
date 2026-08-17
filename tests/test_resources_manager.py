import io
import json

import pytest

from semgem.resources_manager import (
    RESOURCE_SPECS,
    ResourceManager,
    ResourceUnavailableError,
    file_sha256,
)


class Download(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_missing_resource_is_downloaded_versioned_and_reused(tmp_path):
    requests = []

    def opener(request, timeout):
        requests.append((request.full_url, timeout))
        return Download(b"RHEA_ID\tDIRECTION\tMASTER_ID\tID\tDB\n")

    manager = ResourceManager(tmp_path, opener=opener)
    first = manager.ensure("rhea_xref")
    second = manager.ensure("rhea_xref")

    assert first == second
    assert first.path == (
        tmp_path / "rhea" / RESOURCE_SPECS["rhea_xref"].version
        / "rhea2xrefs.tsv"
    )
    assert first.path.read_bytes().startswith(b"RHEA_ID")
    assert requests == [(RESOURCE_SPECS["rhea_xref"].url, 120)]

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["manifest_version"] == 1
    assert manifest["resources"]["rhea_xref"]["sha256"] == file_sha256(
        first.path
    )


def test_corrupt_cached_resource_is_downloaded_again(tmp_path):
    payloads = iter((b"first", b"second"))
    manager = ResourceManager(
        tmp_path,
        opener=lambda request, timeout: Download(next(payloads)),
    )
    resource = manager.ensure("rhea_xref")
    resource.path.write_bytes(b"corrupt")

    refreshed = manager.ensure("rhea_xref")

    assert refreshed.path.read_bytes() == b"second"
    assert refreshed.sha256 == file_sha256(refreshed.path)


def test_offline_mode_rejects_missing_downloaded_resource(tmp_path):
    manager = ResourceManager(tmp_path)

    with pytest.raises(ResourceUnavailableError, match="without --offline"):
        manager.ensure("rhea_xref", offline=True)


def test_packaged_sbo_seeds_cache_even_in_offline_mode(tmp_path):
    packaged = tmp_path / "packaged.obo"
    packaged.write_text("format-version: 1.2\n", encoding="utf-8")
    cache = tmp_path / "cache"
    manager = ResourceManager(cache, packaged_sbo=packaged)

    resource = manager.ensure("sbo_obo", offline=True)

    assert resource.path.read_text(encoding="utf-8") == "format-version: 1.2\n"
    assert manager.status()[0]["verified"] is True


def test_resource_status_reports_missing_and_verified_entries(tmp_path):
    manager = ResourceManager(
        tmp_path,
        opener=lambda request, timeout: Download(b"xref\n"),
    )
    manager.ensure("rhea_xref")

    statuses = {item["key"]: item for item in manager.status()}

    assert statuses["rhea_xref"]["verified"] is True
    assert statuses["metanetx_reac_xref"]["available"] is False
