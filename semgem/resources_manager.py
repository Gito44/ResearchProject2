"""Download, verify, and reuse external enrichment resources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import BinaryIO, Callable
from urllib.request import Request, urlopen


DEFAULT_RESOURCE_ROOT = Path.home() / ".semgem" / "resources"
RESOURCE_ROOT_ENV = "SEMGEM_RESOURCE_DIR"


class ResourceUnavailableError(RuntimeError):
    """Raised when a required external resource cannot be made available."""


@dataclass(frozen=True)
class ResourceSpec:
    key: str
    provider: str
    version: str
    filename: str
    url: str


@dataclass(frozen=True)
class ManagedResource:
    key: str
    provider: str
    version: str
    path: Path
    url: str
    sha256: str
    downloaded_at: str


RESOURCE_SPECS = {
    "sbo_obo": ResourceSpec(
        key="sbo_obo",
        provider="sbo",
        version="official",
        filename="SBO_OBO.obo",
        url=(
            "https://raw.githubusercontent.com/EBI-BioModels/SBO/"
            "master/SBO_OBO.obo"
        ),
    ),
    "rhea_xref": ResourceSpec(
        key="rhea_xref",
        provider="rhea",
        version="current",
        filename="rhea2xrefs.tsv",
        url="https://ftp.expasy.org/databases/rhea/tsv/rhea2xrefs.tsv",
    ),
    "metanetx_reac_xref": ResourceSpec(
        key="metanetx_reac_xref",
        provider="metanetx",
        version="4.5",
        filename="reac_xref.tsv",
        url="https://www.metanetx.org/ftp/4.5/reac_xref.tsv",
    ),
    "metanetx_chem_xref": ResourceSpec(
        key="metanetx_chem_xref",
        provider="metanetx",
        version="4.5",
        filename="chem_xref.tsv",
        url="https://www.metanetx.org/ftp/4.5/chem_xref.tsv",
    ),
    "metanetx_reac_prop": ResourceSpec(
        key="metanetx_reac_prop",
        provider="metanetx",
        version="4.5",
        filename="reac_prop.tsv",
        url="https://www.metanetx.org/ftp/4.5/reac_prop.tsv",
    ),
    "metanetx_chem_prop": ResourceSpec(
        key="metanetx_chem_prop",
        provider="metanetx",
        version="4.5",
        filename="chem_prop.tsv",
        url="https://www.metanetx.org/ftp/4.5/chem_prop.tsv",
    ),
}


def default_resource_root() -> Path:
    """Return the user resource cache, honoring an environment override."""
    configured = os.environ.get(RESOURCE_ROOT_ENV)
    return Path(configured).expanduser() if configured else DEFAULT_RESOURCE_ROOT


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ResourceManager:
    """Own SemGEM's versioned, user-local provider resource cache."""

    def __init__(
        self,
        root: str | Path | None = None,
        opener: Callable[..., BinaryIO] = urlopen,
        packaged_sbo: str | Path | None = None,
        download_reporter: Callable[[ResourceSpec, Path], None] | None = None,
    ):
        self.root = Path(root) if root is not None else default_resource_root()
        self.opener = opener
        self.packaged_sbo = Path(packaged_sbo) if packaged_sbo else None
        self.download_reporter = download_reporter
        self.manifest_path = self.root / "manifest.json"

    def ensure(
        self,
        key: str,
        *,
        refresh: bool = False,
        offline: bool = False,
    ) -> ManagedResource:
        """Return a verified cached resource, acquiring it when necessary."""
        try:
            spec = RESOURCE_SPECS[key]
        except KeyError as error:
            raise KeyError(f"Unknown managed resource: {key}") from error

        path = self.root / spec.provider / spec.version / spec.filename
        manifest = self._load_manifest()
        cached = manifest.get("resources", {}).get(key)
        if not refresh and self._cache_is_valid(path, spec, cached):
            return self._record(spec, path, cached)

        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if key == "sbo_obo" and self.packaged_sbo is not None and (
                self.packaged_sbo.is_file()
            ) and not refresh:
                self._copy_atomically(self.packaged_sbo, path)
            else:
                if offline:
                    raise ResourceUnavailableError(
                        f"Resource '{key}' is not available in the verified "
                        f"cache at {path}. Run once without --offline to "
                        "download it."
                    )
                if self.download_reporter is not None:
                    self.download_reporter(spec, path)
                self._download_atomically(spec.url, path)
        except ResourceUnavailableError:
            raise
        except (OSError, ValueError) as error:
            raise ResourceUnavailableError(
                f"Could not acquire {spec.provider} resource '{key}' from "
                f"{spec.url}: {error}"
            ) from error

        entry = {
            "provider": spec.provider,
            "version": spec.version,
            "filename": spec.filename,
            "url": spec.url,
            "sha256": file_sha256(path),
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest.setdefault("resources", {})[key] = entry
        self._write_manifest(manifest)
        return self._record(spec, path, entry)

    def status(self) -> list[dict]:
        """Describe every managed resource and whether its cache is valid."""
        manifest = self._load_manifest()
        entries = manifest.get("resources", {})
        results = []
        for key, spec in RESOURCE_SPECS.items():
            path = self.root / spec.provider / spec.version / spec.filename
            entry = entries.get(key)
            results.append(
                {
                    "key": key,
                    "provider": spec.provider,
                    "version": spec.version,
                    "path": str(path),
                    "available": path.is_file(),
                    "verified": self._cache_is_valid(path, spec, entry),
                    "sha256": entry.get("sha256") if entry else None,
                    "downloaded_at": (
                        entry.get("downloaded_at") if entry else None
                    ),
                    "url": spec.url,
                }
            )
        return results

    def _cache_is_valid(self, path: Path, spec: ResourceSpec, entry) -> bool:
        if not path.is_file() or not entry:
            return False
        if entry.get("version") != spec.version or entry.get("url") != spec.url:
            return False
        expected = entry.get("sha256")
        return bool(expected) and file_sha256(path) == expected

    @staticmethod
    def _record(spec: ResourceSpec, path: Path, entry: dict) -> ManagedResource:
        return ManagedResource(
            key=spec.key,
            provider=spec.provider,
            version=spec.version,
            path=path,
            url=spec.url,
            sha256=entry["sha256"],
            downloaded_at=entry["downloaded_at"],
        )

    def _download_atomically(self, url: str, destination: Path) -> None:
        temporary = destination.with_suffix(destination.suffix + ".part")
        request = Request(url, headers={"User-Agent": "SemGEM/0.10"})
        try:
            with self.opener(request, timeout=120) as response:
                with temporary.open("wb") as output:
                    shutil.copyfileobj(response, output)
                headers = getattr(response, "headers", None)
                expected_size = headers.get("Content-Length") if headers else None
                if expected_size is not None and temporary.stat().st_size != int(
                    expected_size
                ):
                    raise ValueError(
                        "download size did not match the server Content-Length"
                    )
            if temporary.stat().st_size == 0:
                raise ValueError("downloaded file was empty")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _copy_atomically(source: Path, destination: Path) -> None:
        temporary = destination.with_suffix(destination.suffix + ".part")
        try:
            shutil.copyfile(source, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)

    def _load_manifest(self) -> dict:
        if not self.manifest_path.is_file():
            return {"manifest_version": 1, "resources": {}}
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as error:
            raise ResourceUnavailableError(
                f"Resource manifest is invalid: {self.manifest_path}"
            ) from error

    def _write_manifest(self, manifest: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.manifest_path.with_suffix(".json.part")
        temporary.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.manifest_path)
