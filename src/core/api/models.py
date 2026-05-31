from pydantic import BaseModel, Field
from typing import Any, Optional

from core.version import API_VERSION


# ── Plugin Config Schema ──────────────────────────────────────────────


class ConfigSchemaField(BaseModel):
    """A single field inside a plugin's ``config_schema``."""

    key: str = Field(..., description="Dotted path, e.g. 'port' or 'theme.background'")
    type: str = Field("string", description="Data type: string, integer, number, boolean, color, select, array, object")
    default: Any = Field(None, description="Default value used when the key is missing")
    label: str = Field("", description="Human-readable label for the GUI")
    help: str = Field("", description="Tooltip / help text shown in the GUI")
    category: str = Field("General", description="Grouping category for the GUI")
    required: bool = Field(False, description="Whether the field is mandatory")
    secret: bool = Field(False, description="If true, value should be masked in the GUI")
    min: Optional[int] = Field(None, description="Minimum value (for integer/number)")
    max: Optional[int] = Field(None, description="Maximum value (for integer/number)")
    options: list[str] = Field(default_factory=list, description="Allowed values (for select)")
    advanced: bool = Field(False, description="Hide from basic / first-run wizard view")
    widget: Optional[str] = Field(None, description="GUI widget hint (e.g. 'textarea', 'color')")
    item_schema: Optional[dict] = Field(None, description="Schema for array items or nested objects")


class PluginConfigSchemaModel(BaseModel):
    """Root schema object embedded in ``plugin.json``."""

    version: int = Field(1, description="Schema format version")
    fields: list[ConfigSchemaField] = Field(default_factory=list, description="Ordered list of fields")


# ── Plugin Manifest ──────────────────────────────────────────────────


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
    config_schema: Optional[PluginConfigSchemaModel] = Field(
        None, description="Schema for plugin-local config (GUI + validation)"
    )


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


class PluginUpdateInstallResult(BaseModel):
    """Install result for a single plugin."""

    name: str
    display_name: str
    version: str
    success: bool
    error: str | None = None


class PluginUpdatesInstallResponse(BaseModel):
    results: list[PluginUpdateInstallResult]
    installed: int
    failed: int


# ── Config models ────────────────────────────────────────────────────


class ToolUpdateCheckResponse(BaseModel):
    """Response for ``GET /api/v1/updates/check``."""

    current_version: str
    latest_version: str | None = None
    update_available: bool = False
    release_url: str = ""
    published_at: str = ""
    error: str | None = None


class ConfigResponse(BaseModel):
    path: str
    config: dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    config: dict[str, Any]
    backup: bool = True


# ── Actions (actions.mca) models ───────────────────────────────────


class ActionCommand(BaseModel):
    """A single command inside a trigger."""

    type: str = "vanilla"  # vanilla, rcon, script, overlay, named_overlay
    command: str = ""
    multiplier: int = 1
    title: str = ""
    subtitle: str = ""
    duration: int = 3
    overlay_name: str = "default"


class ActionTrigger(BaseModel):
    name: str
    enabled: bool = True
    type: str = "Custom"
    commands: list[ActionCommand] = []


class ActionsResponse(BaseModel):
    triggers: list[ActionTrigger]


class ActionsUpdateRequest(BaseModel):
    triggers: list[ActionTrigger]


class RawActionsResponse(BaseModel):
    content: str
    diagnostics: list[dict] = []


class RawActionsUpdateRequest(BaseModel):
    content: str


