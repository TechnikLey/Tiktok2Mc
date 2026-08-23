from typing import Any

from pydantic import BaseModel, Field

from core.version import (
    API_VERSION,  # noqa: F401  # re-export: importers use core.api.models.API_VERSION
    TOOL_VERSION,  # noqa: F401  # re-export: importers use core.api.models.TOOL_VERSION
)

# ── Plugin Config Schema ──────────────────────────────────────────────


class ConfigSchemaField(BaseModel):
    """A single field inside a plugin's ``config_schema``."""

    key: str = Field(..., description="Dotted path, e.g. 'port' or 'theme.background'")
    type: str = Field(
        "string",
        description="Data type: string, integer, number, boolean, color, select, array, object",
    )
    default: Any = Field(None, description="Default value used when the key is missing")
    label: str = Field("", description="Human-readable label for the GUI")
    help: str = Field("", description="Tooltip / help text shown in the GUI")
    category: str = Field("General", description="Grouping category for the GUI")
    required: bool = Field(False, description="Whether the field is mandatory")
    secret: bool = Field(
        False, description="If true, value should be masked in the GUI"
    )
    min: int | None = Field(None, description="Minimum value (for integer/number)")
    max: int | None = Field(None, description="Maximum value (for integer/number)")
    options: list[str] = Field(
        default_factory=list, description="Allowed values (for select)"
    )
    advanced: bool = Field(False, description="Hide from basic / first-run wizard view")
    widget: str | None = Field(
        None, description="GUI widget hint (e.g. 'textarea', 'color')"
    )
    item_schema: dict | None = Field(
        None, description="Schema for array items or nested objects"
    )


class PluginConfigSchemaModel(BaseModel):
    """Root schema object embedded in ``plugin.json``."""

    version: int = Field(1, description="Schema format version")
    fields: list[ConfigSchemaField] = Field(
        default_factory=list, description="Ordered list of fields"
    )


# ── Plugin Manifest ──────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str
    version: str
    api_version: str
    tool_version: str


class StatusDetail(BaseModel):
    server: str
    plugins_active: int
    plugins_total: int
    config_loaded: bool
    uptime_seconds: float
    tiktok_live: bool | None = Field(
        None,
        description="Whether the TikTok live connection is currently active (None = unknown)",
    )
    tiktok_live_last_update: float | None = Field(
        None,
        description="Unix timestamp of the last live-status report from the bridge",
    )
    tiktok_live_last_event: float | None = Field(
        None,
        description="Unix timestamp of the last genuine TikTok event (test triggers excluded)",
    )
    tiktok_live_source: str = Field(
        "", description="Source of the last live-status report"
    )
    # Bridge metrics
    rcon_queue_size: int | None = Field(
        None, description="Current size of the RCON command queue"
    )
    trigger_queue_size: int | None = Field(
        None, description="Current size of the trigger queue"
    )
    events_per_minute: int | None = Field(
        None, description="Events processed per minute (rolling 60s window)"
    )
    gift_value_usd_today: float | None = Field(
        None, description="Total gift value in USD today"
    )


# ── Reaction Catalog ─────────────────────────────────────────────────


class ReactionEvent(BaseModel):
    """An event a plugin publishes to the EventBus — a reaction trigger.

    The GUI groups plugin events by the plugin's own name (the category
    is derived server-side, plugins never declare a category themselves).
    """

    key: str = Field(..., description="Event identifier, e.g. 'timer.zero'")
    name: str = Field("", description="Human-readable name shown in the GUI")
    desc: str = Field("", description="Short description shown in the GUI")
    icon: str = Field("⚡", description="Emoji icon shown in the GUI")
    name_i18n: dict[str, str] = Field(
        default_factory=dict,
        description='Optional localized names keyed by language code (e.g. {"de": "Neuer Follower"}). '
        "Falls back to ``name`` when the requested language is absent.",
    )
    desc_i18n: dict[str, str] = Field(
        default_factory=dict,
        description="Optional localized descriptions keyed by language code. "
        "Falls back to ``desc`` when the requested language is absent.",
    )


class ReactionCommandArg(BaseModel):
    """Schema for a single argument of a plugin reaction command."""

    type: str = Field("string", description="string, number, or select")
    label: str = Field("", description="Human-readable label for the GUI")
    default: Any = Field(None, description="Default value used when the arg is missing")
    min: int | None = Field(None, description="Minimum value (for number)")
    max: int | None = Field(None, description="Maximum value (for number)")
    options: list[str] = Field(
        default_factory=list, description="Allowed values (for select)"
    )
    placeholder: str = Field("", description="Input placeholder for the GUI")
    hint: str = Field("", description="Help text shown under the input")
    label_i18n: dict[str, str] = Field(
        default_factory=dict,
        description="Optional localized labels keyed by language code.",
    )


class ReactionCommand(BaseModel):
    """A command a plugin accepts via the command queue — a reaction action."""

    name: str = Field(..., description="Human-readable name shown in the GUI")
    desc: str = Field("", description="Short description shown in the GUI")
    args: dict[str, ReactionCommandArg] = Field(
        default_factory=dict, description="Argument schemas keyed by argument name"
    )
    name_i18n: dict[str, str] = Field(
        default_factory=dict,
        description="Optional localized names keyed by language code.",
    )
    desc_i18n: dict[str, str] = Field(
        default_factory=dict,
        description="Optional localized descriptions keyed by language code.",
    )


# ── Plugin Manifest ──────────────────────────────────────────────────


class CommentHandlerConfig(BaseModel):
    """Declares that a plugin receives prefixed TikTok comments.

    See ``docs/dev-book`` ch03-05: comments starting with ``prefix`` are
    forwarded to the plugin as a ``comment`` command with the prefix
    stripped from the text.
    """

    prefix: str = Field(
        "$", description="Character(s) marking a plugin command comment"
    )
    enabled: bool = Field(True, description="Whether the handler is active")


class PluginManifest(BaseModel):
    """Declarative plugin metadata from ``plugin.json``.

    This is the **only** source of truth for plugin identity.
    The launcher reads these files to discover plugins;
    the API never scans executables or guesses names.
    """

    name: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
        description="Unique kebab-case identifier",
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
    max_api_version: str | None = Field(
        None, description="Highest API version supported (None = no limit)"
    )
    capabilities: list[str] = Field(
        default_factory=list,
        description="Feature flags for EventBus routing",
    )
    permissions: list[str] = Field(
        default_factory=list,
        description=(
            "Opt-in capability restrictions for the BasePlugin API surface "
            "(store, network, plugins, events). An empty list means the "
            "plugin runs unrestricted (backward compatible)."
        ),
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Plugins that must be running first",
    )
    event_subscriptions: list[str] = Field(
        default_factory=list,
        description="Event types this plugin wants to receive via CommandQueue. Supports wildcards: tiktok.*, tiktok.gift, etc.",
    )
    comment_handler: CommentHandlerConfig | None = Field(
        None,
        description="Declares that this plugin receives TikTok comments starting with a prefix via 'comment' commands",
    )
    update_url: str = Field(
        "",
        description="URL for checking plugin updates (GitHub Releases API or direct)",
    )
    ics: bool = Field(True, description="Interface Control System flag")
    level: int = Field(4, ge=1, le=4, description="Default visibility level")
    config_schema: PluginConfigSchemaModel | None = Field(
        None, description="Schema for plugin-local config (GUI + validation)"
    )
    icon: str = Field("🔌", description="Display icon (emoji) shown in the GUI")
    platform: str = Field(
        "all",
        description="Target platform: 'all', 'linux', or 'windows'. "
        "Incompatible plugins cannot be enabled.",
    )
    emitted_events: list[ReactionEvent] = Field(
        default_factory=list,
        description="Events this plugin publishes to the EventBus; shown as reaction triggers in the GUI",
    )
    accepted_commands: dict[str, ReactionCommand] = Field(
        default_factory=dict,
        description="Commands this plugin accepts via the command queue; shown as reaction actions in the GUI",
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
    permissions: list[str] = Field(
        default_factory=list,
        description=(
            "Opt-in capability restrictions for the BasePlugin API surface "
            "(store, network, plugins, events). Empty = unrestricted."
        ),
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Plugins that must be running first",
    )
    update_url: str = Field("", description="URL for checking plugin updates")
    author: str = Field("", description="Plugin author or maintainer")
    homepage: str = Field("", description="Project URL")
    registered_at: float | None = Field(
        None, description="Unix timestamp of first registration"
    )
    updated_at: float | None = Field(None, description="Unix timestamp of last update")
    health_status: str = Field(
        "unknown", description="Current health: unknown, healthy, unhealthy, dead"
    )
    last_heartbeat: float | None = Field(
        None, description="Unix timestamp of last successful health check"
    )
    error: str = Field("", description="Error message if plugin manifest is broken")
    platform: str = Field(
        "all",
        description="Target platform: 'all', 'linux', or 'windows'",
    )
    dashboard_ui: bool = Field(
        default=False,
        description="Plugin provides a dashboard tab (manifest 'dashboard_ui')",
    )
    bundled: bool = Field(
        default=False,
        description="Plugin ships with the application (manifest 'bundled')",
    )
    queries: list[str] = Field(
        default_factory=list,
        description="Declared query names for POST /plugins/{name}/query "
        "(manifest 'queries'; refreshed per request)",
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
    update_url: str = ""
    author: str = ""
    homepage: str = ""
    health_status: str = "unknown"
    last_heartbeat: float | None = None
    platform: str = "all"


class PluginUpdateRequest(BaseModel):
    """Partial-update body for ``PUT /plugins/{name}``."""

    enabled: bool | None = None
    level: int | None = Field(None, ge=1, le=4)
    ics: bool | None = None
    path: str | None = None
    version: str | None = None
    description: str | None = None
    entry_point: str | None = None
    display_name: str | None = None
    capabilities: list[str] | None = None
    depends_on: list[str] | None = None
    update_url: str | None = None
    author: str | None = None
    homepage: str | None = None
    health_status: str | None = None
    last_heartbeat: float | None = None


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


class UpdateResultResponse(BaseModel):
    """Response for ``GET /api/v1/updates/result``.

    Describes how the last tool-updater run ended (exit code + message).
    """

    exit_code: int | None = None
    ok: bool = True
    message: str | None = None
    source: str = "startup"
    timestamp: float | None = None


class ToolUpdateApplyResponse(BaseModel):
    """Response for ``POST /api/v1/updates/apply``."""

    status: str = "started"
    message: str = ""


class ConfigResponse(BaseModel):
    path: str
    config: dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    config: dict[str, Any]
    backup: bool = True


class EventCommandsResponse(BaseModel):
    path: str
    event_commands: dict[str, list[dict[str, Any]]]


class EventCommandsUpdateRequest(BaseModel):
    event_commands: dict[str, list[dict[str, Any]]]


# ── Comment Commands models ────────────────────────────────────────


class CommentCommandsResponse(BaseModel):
    path: str
    comment_commands: dict[str, Any]


class CommentCommandsUpdateRequest(BaseModel):
    comment_commands: dict[str, Any]


# ── Chatbot models ─────────────────────────────────────────────────


class ChatbotConfigResponse(BaseModel):
    path: str
    chatbot: dict[str, Any]
    reloaded: bool = True  # False when the bridge reload signal could not be written


class ChatbotConfigUpdateRequest(BaseModel):
    chatbot: dict[str, Any]


class ChatbotStatusResponse(BaseModel):
    status: dict[str, Any] | None


class ChatbotSessionResponse(BaseModel):
    """Secret-free view of the stored TikTok session credentials."""

    configured: bool = False
    masked_session_id: str | None = None
    tt_target_idc: str = ""
    updated: float | None = None


class ChatbotSessionUpdateRequest(BaseModel):
    session_id: str
    tt_target_idc: str | None = None


class NotificationRequest(BaseModel):
    """Body for ``POST /notifications``.

    ``channels`` selects the delivery targets: either a list of channel
    names (global config params apply) or a mapping of channel name to
    inline params (merged over the global config) so plugins/hooks can
    stay fully self-contained.
    """

    title: str
    body: str = ""
    level: str = "info"
    channels: list[str] | dict[str, dict[str, Any]] | None = None


class NotificationResponse(BaseModel):
    """Per-outcome channel lists after a notification fan-out."""

    sent: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []


class ReactionCatalogResponse(BaseModel):
    """Merged reaction catalog served to the GUI reactions wizard."""

    version: int
    events: dict[str, dict[str, Any]]
    plugins: dict[str, dict[str, Any]]
    commands: dict[str, dict[str, Any]]
    templates: list[dict[str, Any]]


# ── Actions (actions.mca) models ───────────────────────────────────


class ActionCommand(BaseModel):
    """A single command inside a trigger."""

    type: str = "vanilla"  # vanilla, rcon, script, overlay, named_overlay, shell
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


# ── Trigger (Event Tester) models ───────────────────────────────────


class TriggerTypesResponse(BaseModel):
    types: list[str]


class TriggerExecuteRequest(BaseModel):
    trigger: str
    user: str = "System"
    gift_id: str | None = None
    gift_name: str | None = None


class TriggerCommentRequest(BaseModel):
    user: str = "TestUser"
    text: str
    moderator: bool = False
    superfan: bool = False
    fanclub: bool = False


class TriggerResponse(BaseModel):
    status: str
    message: str = ""
    trigger: str = ""
    user: str = ""


class TiktokToggleResponse(BaseModel):
    status: str
    message: str = ""
    connected: bool = False


class TriggerHistoryEntry(BaseModel):
    timestamp: float
    duration_ms: float = 0.0
    kind: str
    payload: dict[str, Any]
    status: str
    message: str = ""
    success: bool = True


class TriggerHistoryResponse(BaseModel):
    history: list[TriggerHistoryEntry]


# ── Revenue (daily gift revenue log) models ─────────────────────────


class RevenueEntry(BaseModel):
    date: str
    estimated_revenue_usd: float


class RevenueSummary(BaseModel):
    count: int
    total_usd: float
    average_usd: float
    min_usd: float
    max_usd: float
    min_day: str | None = None
    max_day: str | None = None
    days_with_revenue: int
    last_change_usd: float | None = None
    last_change_day: str | None = None
    last7_usd: float
    prev7_usd: float
    last7_delta_usd: float


class RevenueFileInfo(BaseModel):
    exists: bool
    path: str
    size: int | None = None
    modified: float | None = None


class RevenueResponse(BaseModel):
    entries: list[RevenueEntry]
    file: RevenueFileInfo


# ── Backup models ────────────────────────────────────────────────────


class BackupEntry(BaseModel):
    """A single backup file inside a category."""

    category: str = Field("", description="Backup category, e.g. 'config'")
    filename: str = Field(
        ...,
        description="Backup file name, e.g. 'config.v20260529_143021_123456.yaml.bak'",
    )
    label: str = Field("", description="Human-readable creation timestamp")
    size: int = Field(0, description="File size in bytes")
    modified: float | None = Field(None, description="Last-modified Unix timestamp")
    created: float | None = Field(
        None, description="Creation Unix timestamp parsed from the file name"
    )
    restorable: bool = Field(
        True, description="Whether a restore target is known for this backup"
    )


class BackupCategory(BaseModel):
    """A group of backups (config, actions, plugins/<name>, ...)."""

    category: str = Field(..., description="Category identifier")
    label: str = Field("", description="Human-readable category label")
    count: int = Field(0, description="Number of entries")
    entries: list[BackupEntry] = Field(default_factory=list)


class BackupListResponse(BaseModel):
    """Response for ``GET /api/v1/backups``."""

    root: str = Field("", description="Absolute path of the backup root directory")
    categories: list[BackupCategory] = Field(default_factory=list)
    total: int = Field(0, description="Total number of backup files")


class BackupRestoreRequest(BaseModel):
    """Request body for ``POST /api/v1/backups/restore``."""

    category: str = Field(..., description="Category of the backup to restore")
    filename: str = Field(..., description="File name of the backup to restore")
    target: str | None = Field(
        None,
        description=(
            "Optional custom restore target path (relative to project root). "
            "Required for categories without a fixed target (_other, hook_registry)."
        ),
    )


class BackupRestoreResponse(BaseModel):
    status: str
    category: str = ""
    filename: str = ""
    target: str = Field("", description="Absolute path of the restored target file")


class BackupCreateRequest(BaseModel):
    """Request body for ``POST /api/v1/backups/create``."""

    targets: list[str] = Field(
        default_factory=lambda: ["config", "actions"],
        description="Which targets to back up now: config, actions, plugin_registry",
    )


class BackupCreateResponse(BaseModel):
    created: list[dict[str, str]] = Field(
        default_factory=list, description="Created backups: [{target, category, path}]"
    )
    skipped: list[str] = Field(
        default_factory=list,
        description="Targets with no new backup (unchanged / missing)",
    )


class BundleImportResponse(BaseModel):
    """Response body for ``POST /api/v1/config-bundle/import``."""

    applied: list[str] = Field(
        default_factory=list, description="Bundle-internal names that were applied"
    )
    count: int = Field(0, description="Number of applied files")


# ── Session models ───────────────────────────────────────────────────


class SessionEntry(BaseModel):
    """One completed TikTok stream session summary."""

    start: str = Field(..., description="Session start (ISO 8601 UTC)")
    end: str = Field(..., description="Session end (ISO 8601 UTC)")
    duration_seconds: float = Field(0, description="Session duration in seconds")
    gifts: int = Field(0, description="Gifts received")
    gift_value_usd: float = Field(0, description="Estimated gift value in USD")
    likes: int = Field(0, description="Likes received")
    follows: int = Field(0, description="Follows received")
    comments: int = Field(0, description="Comments received")
    shares: int = Field(0, description="Shares received")
    joins: int = Field(0, description="Joins received")


class SessionsResponse(BaseModel):
    """List of session summaries plus totals."""

    total: int = Field(0, description="Number of recorded sessions")
    total_gifts: int = Field(0, description="Gifts across all sessions")
    total_gift_value_usd: float = Field(0, description="Gift value across all sessions")
    total_likes: int = Field(0, description="Likes across all sessions")
    total_follows: int = Field(0, description="Follows across all sessions")
    total_comments: int = Field(0, description="Comments across all sessions")
    total_shares: int = Field(0, description="Shares across all sessions")
    total_joins: int = Field(0, description="Joins across all sessions")
    sessions: list[SessionEntry] = Field(default_factory=list)
