"""Pydantic request and response models for the HTTP API."""

from typing import Any, Literal

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
    """Response for the API health endpoint."""

    status: str
    version: str
    api_version: str
    tool_version: str


class StatusDetail(BaseModel):
    """Detailed runtime status reported by the health endpoint."""

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


EVENT_DATA_TYPES = ("string", "number", "boolean", "object", "array", "any")


class EventDataField(BaseModel):
    """A single field of an event payload schema (``data_schema``)."""

    key: str = Field(
        ...,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$",
        description="Payload key, e.g. 'count'",
    )
    type: str = Field(
        "any",
        description=f"One of: {', '.join(EVENT_DATA_TYPES)}",
    )
    desc: str = Field("", description="Short human-readable description")
    required: bool = Field(False, description="Whether publishers must include the key")


class ReactionEvent(BaseModel):
    """An event a plugin publishes to the EventBus — a reaction trigger.

    The GUI groups plugin events by the plugin's own name (the category
    is derived server-side, plugins never declare a category themselves).
    """

    key: str = Field(..., description="Event identifier, e.g. 'timer.zero'")
    name: str = Field("", description="Human-readable name shown in the GUI")
    desc: str = Field("", description="Short description shown in the GUI")
    icon: str = Field("⚡", description="Emoji icon shown in the GUI")
    version: int = Field(
        1,
        ge=1,
        description=(
            "Payload contract version. Bump when data_schema changes in a "
            "breaking way; consumers can branch on it."
        ),
    )
    data_schema: list[EventDataField] = Field(
        default_factory=list,
        description=(
            "Declared payload fields. Publishers posting this event type "
            "with missing/mistyped required fields are rejected with "
            "422 API-0010."
        ),
    )
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

    See ``CommentHandlerConfig.prefix``: comments starting with ``prefix`` are
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
            "Mandatory capability declarations for the BasePlugin API "
            "surface (store, network, plugins, events). Undeclared "
            "families are denied by default."
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
            "Mandatory capability declarations for the BasePlugin API "
            "surface (store, network, plugins, events); undeclared "
            "families are denied by default."
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
        """Build a registry entry from a parsed plugin manifest.

        ``overrides`` are applied after dumping the manifest fields; the manifest's
        ``entry_point`` is exposed as the registration ``path``."""

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


class GiftSyncRequest(BaseModel):
    """Body for ``POST /api/v1/gifts/sync``."""

    source: Literal["auto", "official", "fallback"] = Field(
        default="auto",
        description=(
            "Gift source: 'auto' tries the official endpoint first, then the "
            "antiops GitHub mirror; 'official' / 'fallback' pin one source."
        ),
    )


class GiftSyncResponse(BaseModel):
    """Result of a gift catalog sync run."""

    ok: bool
    source: str | None = None
    total: int = 0
    added: int = 0
    removed: int = 0
    renamed: int = 0
    target: str | None = None
    error: str | None = None


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
    """Response listing registered plugins with summary counts."""

    total: int
    enabled: int
    plugins: list[PluginRegistration]


class PluginRegisterResponse(BaseModel):
    """Response returned after registering a plugin."""

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
    """Response listing available plugin updates and counts."""

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
    """Response summarising plugin update installation results."""

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
    """Response containing the config file path and parsed contents."""

    path: str
    config: dict[str, Any]


class ConfigUpdateRequest(BaseModel):
    """Request body for replacing the main config.

    ``backup`` controls whether a pre-write backup is created."""

    config: dict[str, Any]
    backup: bool = True


class EventCommandsResponse(BaseModel):
    """Response containing the event-command mapping and its source path."""

    path: str
    event_commands: dict[str, list[dict[str, Any]]]


class EventCommandsUpdateRequest(BaseModel):
    """Request body replacing the event-command mapping."""

    event_commands: dict[str, list[dict[str, Any]]]


# ── Comment Commands models ────────────────────────────────────────


class CommentCommandsResponse(BaseModel):
    """Response containing the comment-command mapping and its source path."""

    path: str
    comment_commands: dict[str, Any]


class CommentCommandsUpdateRequest(BaseModel):
    """Request body replacing the comment-command mapping."""

    comment_commands: dict[str, Any]


# ── Chatbot models ─────────────────────────────────────────────────


class ChatbotConfigResponse(BaseModel):
    """Response containing chatbot config contents and whether it was reloaded."""

    path: str
    chatbot: dict[str, Any]
    reloaded: bool = True  # False when the bridge reload signal could not be written


class ChatbotConfigUpdateRequest(BaseModel):
    """Request body replacing the chatbot config."""

    chatbot: dict[str, Any]


class ChatbotStatusResponse(BaseModel):
    """Response containing the chatbot runtime status, or ``None`` when unavailable."""

    status: dict[str, Any] | None


class ChatbotSessionResponse(BaseModel):
    """Secret-free view of the stored TikTok session credentials."""

    configured: bool = False
    masked_session_id: str | None = None
    tt_target_idc: str = ""
    updated: float | None = None


class ChatbotSessionUpdateRequest(BaseModel):
    """Request body updating the stored chatbot session identifiers."""

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
    dynamic_vanilla: bool = False
    title: str = ""
    subtitle: str = ""
    duration: int = 3
    overlay_name: str = "default"


class ActionTrigger(BaseModel):
    """Structured representation of one ``.mca`` trigger block."""

    name: str
    enabled: bool = True
    type: str = "Custom"
    commands: list[ActionCommand] = []


class ActionsResponse(BaseModel):
    """Response listing parsed action triggers."""

    triggers: list[ActionTrigger]


class ActionsUpdateRequest(BaseModel):
    """Request body replacing the structured action triggers."""

    triggers: list[ActionTrigger]


class RawActionsResponse(BaseModel):
    """Response containing raw ``.mca`` content and parse diagnostics."""

    content: str
    diagnostics: list[dict] = []


class RawActionsUpdateRequest(BaseModel):
    """Request body containing raw ``.mca`` content."""

    content: str


# ── Trigger (Event Tester) models ───────────────────────────────────


class TriggerTypesResponse(BaseModel):
    """Response listing supported trigger type names."""

    types: list[str]


class LikeMilestone(BaseModel):
    """Configuration for one like-count milestone."""

    id: str
    every: int
    function: str
    payload: str = "Community"
    enabled: bool = True


class LikeMilestonesResponse(BaseModel):
    """Response listing configured like milestones."""

    milestones: list[LikeMilestone]


class TriggerExecuteRequest(BaseModel):
    """Request body for executing a test trigger."""

    trigger: str
    user: str = "System"
    gift_id: str | None = None
    gift_name: str | None = None


class TriggerCommentRequest(BaseModel):
    """Request body for injecting a test comment."""

    user: str = "TestUser"
    text: str
    moderator: bool = False
    superfan: bool = False
    fanclub: bool = False


class TriggerResponse(BaseModel):
    """Generic response for trigger execution requests."""

    status: str
    message: str = ""
    trigger: str = ""
    user: str = ""


class TiktokToggleResponse(BaseModel):
    """Response for TikTok connection toggle requests."""

    status: str
    message: str = ""
    connected: bool = False


class TriggerHistoryEntry(BaseModel):
    """One executed trigger in the in-memory history."""

    timestamp: float
    duration_ms: float = 0.0
    kind: str
    payload: dict[str, Any]
    status: str
    message: str = ""
    success: bool = True


class TriggerHistoryResponse(BaseModel):
    """Response listing recent trigger history entries."""

    history: list[TriggerHistoryEntry]


# ── Revenue (daily gift revenue log) models ─────────────────────────


class RevenueEntry(BaseModel):
    """Estimated revenue for one day."""

    date: str
    estimated_revenue_usd: float


class RevenueSummary(BaseModel):
    """Aggregate revenue statistics over the available entries."""

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
    """Metadata about the revenue data file."""

    exists: bool
    path: str
    size: int | None = None
    modified: float | None = None


class RevenueResponse(BaseModel):
    """Response containing revenue entries and file metadata."""

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
    """Response describing a restored backup."""

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
    """Response listing created and skipped backups."""

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

    session_id: str | None = Field(None, description="Analytics session id")
    start: str = Field(..., description="Session start (ISO 8601 UTC)")
    end: str = Field(..., description="Session end (ISO 8601 UTC)")
    duration_seconds: float = Field(0, description="Session duration in seconds")
    gifts: int = Field(0, description="Gift units received (compatibility field)")
    gift_value_usd: float = Field(0, description="Estimated gift value in USD")
    likes: int = Field(0, description="Counted likes (compatibility field)")
    follows: int = Field(0, description="Follows received")
    comments: int = Field(0, description="Comments received")
    shares: int = Field(0, description="Shares received")
    joins: int = Field(0, description="Joins received")
    # Extended analytics totals. All optional so legacy JSONL sessions and
    # older clients keep working unchanged.
    gift_events: int = Field(0, description="Gift events (not units)")
    gift_units: int = Field(0, description="Gift units (combo count applied)")
    gift_diamonds: int = Field(0, description="Gift diamonds received")
    unique_gifters: int = Field(0, description="Distinct gift senders")
    likes_raw: int = Field(0, description="Likes before rate limiting")
    likes_counted: int = Field(0, description="Likes counted after rate limiting")
    unique_likers: int = Field(0, description="Distinct viewers who liked")
    unique_followers: int = Field(0, description="Distinct new followers")
    unique_commenters: int = Field(0, description="Distinct commenters")
    unique_sharers: int = Field(0, description="Distinct sharers")
    unique_joiners: int = Field(0, description="Distinct joiners")
    unique_viewers: int = Field(0, description="Distinct viewers seen")
    largest_gift_name: str | None = Field(None, description="Largest single gift")
    largest_gift_value_usd: float = Field(0, description="Largest single gift value")
    largest_gift_diamonds: int = Field(0, description="Largest single gift diamonds")
    largest_combo_name: str | None = Field(None, description="Largest combo gift")
    largest_combo_units: int = Field(0, description="Largest combo unit count")
    reconnect_count: int = Field(0, description="Reconnects during the session")
    end_reason: str | None = Field(None, description="Why the session ended")
    tiktok_user: str = Field("", description="Streamer username")


class SessionsResponse(BaseModel):
    """List of session summaries plus totals."""

    total: int = Field(0, description="Number of recorded sessions")
    total_gifts: int = Field(0, description="Gift units across all sessions")
    total_gift_events: int = Field(0, description="Gift events across all sessions")
    total_gift_units: int = Field(0, description="Gift units across all sessions")
    total_gift_diamonds: int = Field(0, description="Diamonds across all sessions")
    total_gift_value_usd: float = Field(0, description="Gift value across all sessions")
    total_unique_gifters: int = Field(0, description="Unique gifters (sum per session)")
    total_likes: int = Field(0, description="Counted likes across all sessions")
    total_likes_raw: int = Field(0, description="Raw likes across all sessions")
    total_likes_counted: int = Field(0, description="Counted likes across all sessions")
    total_unique_likers: int = Field(0, description="Unique likers (sum per session)")
    total_follows: int = Field(0, description="Follows across all sessions")
    total_unique_followers: int = Field(
        0, description="Unique followers (sum per session)"
    )
    total_comments: int = Field(0, description="Comments across all sessions")
    total_unique_commenters: int = Field(
        0, description="Unique commenters (sum per session)"
    )
    total_shares: int = Field(0, description="Shares across all sessions")
    total_unique_sharers: int = Field(0, description="Unique sharers (sum per session)")
    total_joins: int = Field(0, description="Joins across all sessions")
    total_unique_joiners: int = Field(0, description="Unique joiners (sum per session)")
    total_unique_viewers: int = Field(0, description="Unique viewers (sum per session)")
    sessions: list[SessionEntry] = Field(default_factory=list)


class SessionViewerStats(BaseModel):
    """Per-viewer aggregates for one session."""

    user_key: str = Field("", description="Stable internal viewer key")
    user_id: str | None = Field(None, description="TikTok numeric user id")
    username: str = Field("", description="TikTok unique id")
    display_name: str = Field("", description="TikTok nickname")
    gift_events: int = Field(0, description="Gift events")
    gift_units: int = Field(0, description="Gift units")
    gift_diamonds: int = Field(0, description="Gift diamonds")
    gift_value_usd: float = Field(0, description="Gift value in USD")
    likes_raw: int = Field(0, description="Likes before rate limiting")
    likes_counted: int = Field(0, description="Likes counted")
    comments: int = Field(0, description="Comments")
    follows: int = Field(0, description="Follows")
    shares: int = Field(0, description="Shares")
    joins: int = Field(0, description="Joins")
    first_seen: str = Field("", description="First event (ISO 8601 UTC)")
    last_seen: str = Field("", description="Last event (ISO 8601 UTC)")


class SessionGiftStats(BaseModel):
    """Per-gift aggregates for one session."""

    gift_id: str = Field("", description="TikTok gift id")
    gift_name: str = Field("", description="Gift name")
    events: int = Field(0, description="Gift events")
    units: int = Field(0, description="Gift units")
    diamonds: int = Field(0, description="Gift diamonds")
    value_usd: float = Field(0, description="Gift value in USD")
    unique_gifters: int = Field(0, description="Distinct senders")
    largest_combo_units: int = Field(0, description="Largest combo for this gift")
    first_seen: str = Field("", description="First event (ISO 8601 UTC)")
    last_seen: str = Field("", description="Last event (ISO 8601 UTC)")


class TopEntry(BaseModel):
    """One ranked entry in a session or all-time top list."""

    entry_key: str = Field("", description="Viewer or gift key")
    name: str = Field("", description="Display name")
    value: float = Field(0, description="Primary ranking value")
    units: int = Field(0, description="Gift units (where applicable)")
    diamonds: int = Field(0, description="Diamonds (where applicable)")


class SessionDetailResponse(SessionEntry):
    """One session with per-viewer, per-gift and top-list detail."""

    viewers: list[SessionViewerStats] = Field(default_factory=list)
    gift_stats: list[SessionGiftStats] = Field(default_factory=list)
    tops: dict[str, list[TopEntry]] = Field(default_factory=dict)


class LeaderboardEntry(BaseModel):
    """One row of an all-time leaderboard."""

    user_key: str = Field("", description="Viewer key")
    username: str = Field("", description="TikTok unique id")
    display_name: str = Field("", description="TikTok nickname")
    entry_key: str = Field("", description="Gift key (gift leaderboards)")
    name: str = Field("", description="Gift name (gift leaderboards)")
    value: float = Field(0, description="Primary ranking value")
    units: int = Field(0, description="Gift units")
    diamonds: int = Field(0, description="Diamonds")
    sessions_seen: int = Field(
        0, description="Distinct sessions the viewer appeared in"
    )


class LeaderboardResponse(BaseModel):
    """All-time leaderboards computed from lifetime aggregates."""

    generated_at: str = Field("", description="Generation time (ISO 8601 UTC)")
    top_gifters_value: list[LeaderboardEntry] = Field(default_factory=list)
    top_gifters_units: list[LeaderboardEntry] = Field(default_factory=list)
    top_likers: list[LeaderboardEntry] = Field(default_factory=list)
    top_commenters: list[LeaderboardEntry] = Field(default_factory=list)
    top_gifts_units: list[LeaderboardEntry] = Field(default_factory=list)
    top_gifts_value: list[LeaderboardEntry] = Field(default_factory=list)
