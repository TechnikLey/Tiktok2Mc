from pydantic import BaseModel, Field
from typing import Any, Optional

API_VERSION = "1.0.0"


class HealthResponse(BaseModel):
    status: str
    version: str
    api_version: str


class StatusDetail(BaseModel):
    server: str
    plugins_active: int
    plugins_total: int
    config_loaded: bool
    uptime_seconds: float


# ── Plugin Manifest ──────────────────────────────────────────────────


class PluginManifest(BaseModel):
    """Declarative plugin metadata from ``plugin.json``.

    This is the **only** source of truth for plugin identity.
    The launcher reads these files to discover plugins;
    the API never scans executables or guesses names.
    """

    name: str = Field(
        min_length=1, pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
        description="Unique kebab-case identifier"
    )
    version: str = Field("1.0.0", description="Semver MAJOR.MINOR.PATCH")
    entry_point: str = Field(
        ..., description="Relative path from project root to entry script/binary"
    )
    display_name: str = Field(..., description="Human-readable name for GUI")
    description: str = Field("", description="What the plugin does")
    author: str = Field("", description="Plugin author or maintainer")
    homepage: str = Field("", description="Project URL")

    ports: dict[str, Any] = Field(
        default_factory=lambda: {"declared": [], "protocol": "tcp"},
        description="Port requirements",
    )
    min_api_version: str = Field("1.0.0", description="Lowest API version supported")
    max_api_version: Optional[str] = Field(
        None, description="Highest API version supported (None = no limit)"
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="Feature flags for EventBus routing",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Plugins that must be running first",
    )
    update_url: str = Field(
        "", description="URL for checking plugin updates (GitHub Releases API or direct)")
    auto_enable: bool = Field(
        False, description="Suggested default enabled state (GUI hint)")
    ics: bool = Field(True, description="Interface Control System flag")
    level: int = Field(4, ge=1, le=4, description="Default visibility level")
    port: int = Field(
        0, ge=0, description="Primary web/overlay port from ports.declared"
    )

    @property
    def primary_port(self) -> int:
        ports = (self.ports or {}).get("declared") or []
        return ports[0] if ports else 0


# ── Plugin models ────────────────────────────────────────────────────


class PluginRegistration(BaseModel):
    """Canonical plugin record stored and served by the API registry."""

    name: str = Field(min_length=1, description="Unique plugin name")
    path: str = Field("", description="Filesystem path to the executable")
    entry_point: str = Field(
        "", description="Project-relative entry path from plugin.json"
    )
    display_name: str = Field("", description="Human-readable name for GUI")
    version: str = Field("1.0.0", description="Plugin version string")
    enabled: bool = Field(False, description="Whether the plugin is active")
    level: int = Field(2, ge=1, le=4, description="Visibility level")
    port: int = Field(0, ge=0, description="Web/overlay port, 0=none")
    ics: bool = Field(False, description="Interface Control System flag")
    description: str = Field("", description="Human-readable description")
    capabilities: list[str] = Field(
        default_factory=list,
        description="Feature flags for EventBus routing",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Plugins that must be running first",
    )
    auto_enable: bool = Field(
        False, description="Suggested default enabled state")
    update_url: str = Field(
        "", description="URL for checking plugin updates")
    author: str = Field("", description="Plugin author or maintainer")
    homepage: str = Field("", description="Project URL")
    registered_at: Optional[float] = Field(
        None, description="Unix timestamp of first registration"
    )
    updated_at: Optional[float] = Field(
        None, description="Unix timestamp of last update"
    )

    @classmethod
    def from_manifest(
        cls, manifest: PluginManifest, **overrides: Any
    ) -> "PluginRegistration":
        data = manifest.model_dump()
        data.pop("ports", None)
        data["port"] = manifest.primary_port
        data["path"] = manifest.entry_point
        data.update(overrides)
        return cls(**data)


class PluginRegisterRequest(BaseModel):
    """Request body for ``POST /plugins/register``."""

    name: str = Field(min_length=1)
    path: str = ""
    entry_point: str = ""
    display_name: str = ""
    version: str = "1.0.0"
    enabled: bool = False
    level: int = 2
    port: int = 0
    ics: bool = False
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    auto_enable: bool = False
    update_url: str = ""
    author: str = ""
    homepage: str = ""


class PluginUpdateRequest(BaseModel):
    """Partial-update body for ``PUT /plugins/{name}``."""

    enabled: Optional[bool] = None
    level: Optional[int] = Field(None, ge=1, le=4)
    port: Optional[int] = Field(None, ge=0)
    ics: Optional[bool] = None
    path: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None
    entry_point: Optional[str] = None
    display_name: Optional[str] = None
    capabilities: Optional[list[str]] = None
    depends_on: Optional[list[str]] = None
    auto_enable: Optional[bool] = None
    update_url: Optional[str] = None
    author: Optional[str] = None
    homepage: Optional[str] = None


class PluginListResponse(BaseModel):
    total: int
    enabled: int
    plugins: list[PluginRegistration]


class PluginRegisterResponse(BaseModel):
    status: str
    plugin: PluginRegistration


# ── Update models ────────────────────────────────────────────────────


class PluginUpdateStatus(BaseModel):
    """Update status for a single plugin."""

    name: str
    display_name: str
    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    update_url: str = ""
    checked_at: float | None = None
    error: str | None = None


class PluginUpdatesResponse(BaseModel):
    plugins: list[PluginUpdateStatus]
    total: int
    updates_available: int


# ── Config models ────────────────────────────────────────────────────


class ConfigResponse(BaseModel):
    path: str
    config: dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    config: dict[str, Any]
    backup: bool = True


