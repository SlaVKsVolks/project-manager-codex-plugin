#!/usr/bin/env python3
"""Generic stdio MCP server for project manager coordination."""
from __future__ import annotations

import html
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import traceback
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_MANIFEST_PATH = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
CANONICAL_PLUGIN_ROOT = Path(
    os.environ.get(
        "PROJECT_MANAGER_CANONICAL_PLUGIN_ROOT",
        str(Path.home() / ".codex" / "plugins" / "local-marketplaces" / "personal" / "plugins" / "project-manager"),
    )
).expanduser()
SOURCE_PLUGIN_ROOT = CANONICAL_PLUGIN_ROOT
AGENTS_PLUGIN_ROOT = Path(
    os.environ.get(
        "PROJECT_MANAGER_AGENTS_PLUGIN_ROOT",
        str(Path.home() / ".agents" / "plugins" / "plugins" / "project-manager"),
    )
).expanduser()
AGENTS_MARKETPLACE_ROOT = Path(
    os.environ.get(
        "PROJECT_MANAGER_MARKETPLACE_ROOT",
        str(Path.home() / ".agents" / "plugins"),
    )
).expanduser()
CACHE_PLUGIN_BASE = Path.home() / ".codex" / "plugins" / "cache" / "personal" / "project-manager"
DEFAULT_LOG_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Codex" / "project-manager"
MCP_LOG_PATH = Path(os.environ.get("PROJECT_MANAGER_MCP_LOG", str(DEFAULT_LOG_DIR / "project-manager-mcp.log"))).expanduser()
CODEX_DESKTOP_LOG_ROOT = Path(
    os.environ.get(
        "CODEX_DESKTOP_LOG_ROOT",
        str(Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "Codex" / "Logs"),
    )
).expanduser()
WINDOWLESS_STDIO_WRAPPER_COMMAND = "./scripts/project-manager-mcp.exe"
PROCESS_SNAPSHOT_ENV = "PROJECT_MANAGER_PROCESS_SNAPSHOT"
MCP_PROCESS_LIMIT = int(os.environ.get("PROJECT_MANAGER_MCP_PROCESS_LIMIT", "8"))
MCP_SAFE_WRAPPER_GROUP_LIMIT = int(os.environ.get("PROJECT_MANAGER_MCP_SAFE_WRAPPER_GROUP_LIMIT", "5"))
MCP_WRAPPER_CLEANUP_MIN_AGE_SECONDS = int(os.environ.get("PROJECT_MANAGER_MCP_WRAPPER_CLEANUP_MIN_AGE_SECONDS", "45"))
CODEX_HOME = Path.home() / ".codex"
CODEX_STARTUP_VBS_PATH = Path(
    os.environ.get(
        "CODEX_STARTUP_VBS_PATH",
        str(
            Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
            / "Startup"
            / "CodexHybridProxy-Startup.vbs"
        ),
    )
).expanduser()
CODEX_LOGON_BOOTSTRAP_PATH = Path(
    os.environ.get("CODEX_LOGON_BOOTSTRAP_PATH", str(CODEX_HOME / "codex-logon-bootstrap.ps1"))
).expanduser()
CODEX_HEALTH_GUARDIAN_PATH = Path(
    os.environ.get("CODEX_HEALTH_GUARDIAN_PATH", str(CODEX_HOME / "codex-health-guardian.ps1"))
).expanduser()
CODEX_WATCHDOG_STATE_PATH = Path(
    os.environ.get("CODEX_WATCHDOG_STATE_PATH", str(CODEX_HOME / "codex-watchdog-state.json"))
).expanduser()
CODEX_LAUNCH_LOG_PATH = Path(os.environ.get("CODEX_LAUNCH_LOG_PATH", str(CODEX_HOME / "launch-codex.log"))).expanduser()
CODEX_HEALTH_BOOTSTRAP_TASK_NAME = os.environ.get("CODEX_HEALTH_BOOTSTRAP_TASK_NAME", "Codex Health Bootstrap - SlaVKs")
CHAT_PROCESS_REGISTRY_PATH = Path(
    os.environ.get("CODEX_CHAT_PROCESS_REGISTRY_PATH", str(CODEX_HOME / "process_manager" / "chat_processes.json"))
).expanduser()
LIVE_MODELS_PATH = Path(os.environ.get("CODEX_MODELS_PATH", str(CODEX_HOME / "models.json"))).expanduser()
PROXY_LOG_PATH = Path(os.environ.get("CODEX_PROXY_LOG_PATH", str(CODEX_HOME / "proxy.log"))).expanduser()
OPENCODE_POOL_STATE_PATH = Path(os.environ.get("OPENCODE_GO_POOL_STATE_PATH", str(CODEX_HOME / "opencode_go_pool_state.json"))).expanduser()
MODEL_EXPORT_DIR = CANONICAL_PLUGIN_ROOT / "generated"
MODEL_CATALOG_EXPORT_PATH = MODEL_EXPORT_DIR / "canonical-model-catalog.json"
PROXY_MODEL_LIST_EXPORT_PATH = MODEL_EXPORT_DIR / "proxy-model-list.json"
PROXY_RUNTIME_EXPORT_PATH = MODEL_EXPORT_DIR / "proxy-runtime-instructions.json"
MODEL_RELIABILITY_EVIDENCE_PATH = Path(
    os.environ.get("PROJECT_MANAGER_MODEL_EVIDENCE_PATH", str(DEFAULT_LOG_DIR / "model-reliability-evidence.json"))
).expanduser()
REQUIRED_DISPATCH_FIELDS = ["assignmentId", "assignmentPath"]
REQUIRED_WORKER_FINAL_FIELDS = [
    "assignment_id",
    "status",
    "summary",
    "artifacts",
    "verification",
    "blockers",
    "next_recommended_action",
]
ACTIVE_WORKER_STATUSES = {"active", "running", "working", "in_progress", "healthy"}
COMPLETED_WORKER_STATUSES = {
    "done",
    "complete",
    "completed",
    "needs_review",
    "review",
    "completed_needs_manager_review",
}
ALLOWED_EVIDENCE_SOURCES = {
    "verified_readback",
    "worker_final",
    "manager_direct_artifact",
    "registry_reconcile",
}
PACKET_ROLES = {
    "implementer",
    "spec_reviewer",
    "code_quality_reviewer",
    "repo_explorer",
    "log_analyst",
}
MAX_INLINE_PROMPT_CHARS = int(os.environ.get("PROJECT_MANAGER_MAX_INLINE_PROMPT_CHARS", "6000"))
MAX_PROMPT_TITLE_CHARS = int(os.environ.get("PROJECT_MANAGER_MAX_PROMPT_TITLE_CHARS", "160"))
MAX_PROMPT_PATH_CHARS = int(os.environ.get("PROJECT_MANAGER_MAX_PROMPT_PATH_CHARS", "400"))
MAX_PROMPT_GOAL_CHARS = int(os.environ.get("PROJECT_MANAGER_MAX_PROMPT_GOAL_CHARS", "1400"))
MAX_PROMPT_CONSTRAINTS_CHARS = int(os.environ.get("PROJECT_MANAGER_MAX_PROMPT_CONSTRAINTS_CHARS", "1800"))
MAX_PROMPT_DOD_CHARS = int(os.environ.get("PROJECT_MANAGER_MAX_PROMPT_DOD_CHARS", "1200"))
NATIVE_REASONING_LEVELS = [
    {"effort": "low", "description": "Fast responses with lighter reasoning"},
    {"effort": "medium", "description": "Balances speed and reasoning depth for everyday tasks"},
    {"effort": "high", "description": "Greater reasoning depth for complex problems"},
    {"effort": "xhigh", "description": "Extra high reasoning depth for complex problems"},
]
MODEL_CATALOG_BASE: dict[str, dict[str, Any]] = {
    "gpt-5.5": {
        "slug": "gpt-5.5",
        "displayName": "GPT-5.5",
        "family": "gpt",
        "provider": "openai-quota",
        "providerLabel": "Codex GPT quota",
        "providerCreditSource": "codex-quota",
        "transportRoute": "native",
        "contextWindow": 272000,
        "supportedReasoningLevels": NATIVE_REASONING_LEVELS,
        "defaultThinking": "medium",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": True,
        "supportsSearchTool": True,
        "supportsVerbosity": True,
        "defaultVerbosity": "low",
        "supportsReasoningSummaries": True,
        "reasoningSummaryFormat": "experimental",
        "policyRole": "root_manager",
        "roleHint": "root-manager",
        "costClass": "quota",
        "compatibilityClass": "native",
        "usageTier": "manager_or_final_review",
        "recommendedTasks": ["root-cause analysis", "architecture decisions", "conflict resolution", "final gate"],
        "avoidTasks": ["bulk worker fan-out", "cheap repetitive scans"],
        "recommendedForSummary": "Native Codex frontier manager/generalist for root-cause analysis, architecture decisions, and final review.",
        "avoidForSummary": "Avoid using it as a cheap bulk worker lane when a lower-cost worker is sufficient.",
        "continuationReliability": "strong",
        "toolLoopReliability": "strong",
        "compatibilityNotes": "Native Codex model with the strongest expected tool and thread parity.",
        "knownFailureModes": [],
        "aliases": ["gpt55", "gpt-5.5"],
        "enabled": True,
        "disabledReason": None,
        "description": "Native Codex frontier manager/generalist. Best for top-level planning, architecture, serious debugging, and final review. Uses included Codex GPT quota.",
    },
    "gpt-5.4": {
        "slug": "gpt-5.4",
        "displayName": "GPT-5.4",
        "family": "gpt",
        "provider": "openai-quota",
        "providerLabel": "Codex GPT quota",
        "providerCreditSource": "codex-quota",
        "transportRoute": "native",
        "contextWindow": 272000,
        "supportedReasoningLevels": NATIVE_REASONING_LEVELS,
        "defaultThinking": "medium",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": True,
        "supportsSearchTool": True,
        "supportsVerbosity": True,
        "defaultVerbosity": "low",
        "supportsReasoningSummaries": True,
        "reasoningSummaryFormat": "experimental",
        "policyRole": "senior_reviewer",
        "roleHint": "generalist-manager",
        "costClass": "quota",
        "compatibilityClass": "native",
        "usageTier": "manager_or_final_review",
        "recommendedTasks": ["senior review", "serious native implementation", "behavior regressions", "code quality review"],
        "avoidTasks": ["cheap fan-out"],
        "recommendedForSummary": "Native Codex default generalist for everyday coding, review, and larger multi-step implementation.",
        "avoidForSummary": "Avoid using it for cheap repetitive worker fan-out when a lower-cost worker will do.",
        "continuationReliability": "strong",
        "toolLoopReliability": "strong",
        "compatibilityNotes": "Native Codex model with strong tool-loop and review behavior.",
        "knownFailureModes": [],
        "aliases": ["gpt54", "gpt-5.4"],
        "enabled": True,
        "disabledReason": None,
        "description": "Native Codex generalist. Strong default for everyday coding, multi-step implementation, and review. Uses included Codex GPT quota.",
    },
    "gpt-5.4-mini": {
        "slug": "gpt-5.4-mini",
        "displayName": "GPT-5.4-Mini",
        "family": "gpt",
        "provider": "openai-quota",
        "providerLabel": "Codex GPT quota",
        "providerCreditSource": "codex-quota",
        "transportRoute": "native",
        "contextWindow": 272000,
        "supportedReasoningLevels": NATIVE_REASONING_LEVELS,
        "defaultThinking": "medium",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": True,
        "supportsSearchTool": True,
        "supportsVerbosity": True,
        "defaultVerbosity": "medium",
        "supportsReasoningSummaries": True,
        "reasoningSummaryFormat": "experimental",
        "policyRole": "light_native_worker",
        "roleHint": "light-native-worker",
        "costClass": "quota",
        "compatibilityClass": "native",
        "usageTier": "allowed_fallback",
        "recommendedTasks": ["small bug fixes", "small tests", "light native subagent work"],
        "avoidTasks": ["architecture-sensitive tasks", "final approval"],
        "recommendedForSummary": "Native Codex fast GPT lane for simpler coding tasks, short tool loops, and light worker work.",
        "avoidForSummary": "Avoid final approval or architecture-sensitive ownership.",
        "continuationReliability": "strong",
        "toolLoopReliability": "strong",
        "compatibilityNotes": "Native Codex model with good tool compatibility, but intended for lighter work than GPT-5.4/5.5.",
        "knownFailureModes": [],
        "aliases": ["gpt54mini", "gpt-5.4-mini"],
        "enabled": True,
        "disabledReason": None,
        "description": "Native Codex fast GPT lane for simpler coding tasks, quick follow-ups, and light worker work. Uses included Codex GPT quota.",
    },
    "gpt-5.3-codex-spark": {
        "slug": "gpt-5.3-codex-spark",
        "displayName": "GPT-5.3-Codex-Spark",
        "family": "gpt",
        "provider": "openai-quota",
        "providerLabel": "Codex GPT quota",
        "providerCreditSource": "codex-quota",
        "transportRoute": "native",
        "contextWindow": 128000,
        "supportedReasoningLevels": NATIVE_REASONING_LEVELS,
        "defaultThinking": "high",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": False,
        "supportsSearchTool": True,
        "supportsVerbosity": True,
        "defaultVerbosity": "low",
        "supportsReasoningSummaries": True,
        "reasoningSummaryFormat": "experimental",
        "policyRole": "micro_edit_worker",
        "roleHint": "micro-edit-worker",
        "costClass": "quota",
        "compatibilityClass": "native",
        "usageTier": "allowed_fallback",
        "recommendedTasks": ["tiny edits", "rename/fix/logging passes", "interactive one-file loops"],
        "avoidTasks": ["multi-file features", "architecture work", "hidden-state debugging"],
        "recommendedForSummary": "Native Codex ultra-fast lane for very small edits, quick checks, and short bounded loops.",
        "avoidForSummary": "Avoid larger multi-file features or hidden-state debugging.",
        "continuationReliability": "strong",
        "toolLoopReliability": "strong",
        "compatibilityNotes": "Native Codex model optimized for speed over depth; keep the scope tight.",
        "knownFailureModes": [],
        "aliases": ["spark", "gpt53spark", "gpt-5.3-codex-spark"],
        "enabled": True,
        "disabledReason": None,
        "description": "Native Codex ultra-fast micro-task lane for tiny edits, quick checks, and short bounded loops. Uses included Codex GPT quota.",
    },
    "deepseek-v4-flash": {
        "slug": "deepseek-v4-flash",
        "displayName": "DeepSeek V4 Flash",
        "family": "deepseek",
        "provider": "opencode-go",
        "providerLabel": "OpenCode Go",
        "providerCreditSource": "opencode-go",
        "transportRoute": "chat",
        "contextWindow": 1000000,
        "supportedReasoningLevels": [
            {"effort": "low", "description": "Fastest bounded worker mode: one-pass reads, one narrow action, minimal exploration"},
            {"effort": "medium", "description": "Balanced cheap-worker mode for ordinary implementation, light debugging, and short tool loops"},
            {"effort": "high", "description": "Recommended default for steadier inspect-patch-verify loops and better follow-through on bounded tasks"},
            {"effort": "xhigh", "description": "Maximum Codex-side care for stubborn bounded tasks before escalating to DeepSeek Pro or GPT review"},
        ],
        "defaultThinking": "high",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": False,
        "supportsSearchTool": True,
        "supportsVerbosity": False,
        "defaultVerbosity": "low",
        "supportsReasoningSummaries": False,
        "reasoningSummaryFormat": None,
        "policyRole": "default_implementer",
        "roleHint": "cheap-worker",
        "costClass": "cheap",
        "compatibilityClass": "bridged",
        "usageTier": "default_implementation",
        "recommendedTasks": ["fan-out subagent implementation", "small multi-step fix loops", "mechanical refactors", "routine spec review", "routine log analysis"],
        "avoidTasks": ["final approval", "wide architecture design"],
        "recommendedForSummary": "Default cheap OpenCode Go worker for bounded implementation, quick fixes, and fan-out execution lanes.",
        "avoidForSummary": "Avoid final ownership, final review, and broad architecture decisions.",
        "continuationReliability": "conditional",
        "toolLoopReliability": "conditional",
        "compatibilityNotes": "Bridged through the local Responses/SSE proxy. The proxy maps Codex reasoning selection into worker-behavior instructions while keeping upstream provider thinking disabled for steadier tool use. GPT remains preferable for final ownership.",
        "knownFailureModes": [
            "follow-up tool loops can degrade into raw unparsed tool-call text when transport shape drifts",
            "tool-loop viability can look healthy on a fresh wrapper smoke while stale loaded sessions remain risky",
            "comment-only reasoning lines can leak into PowerShell if proxy sanitization regresses",
        ],
        "aliases": ["flash", "deepseek-flash", "v4-flash", "deepseek v4 flash", "deepseekv4flash"],
        "enabled": True,
        "disabledReason": None,
        "description": "Codex-tuned OpenCode Go cheap worker. 1M context, high-effort default, strong for fan-out implementation, bounded coding, and fast tool-driven work with steadier tool-use behavior. Uses OpenCode Go credits.",
    },
    "deepseek-v4-pro": {
        "slug": "deepseek-v4-pro",
        "displayName": "DeepSeek V4 Pro",
        "family": "deepseek",
        "provider": "opencode-go",
        "providerLabel": "OpenCode Go",
        "providerCreditSource": "opencode-go",
        "transportRoute": "chat",
        "contextWindow": 1000000,
        "supportedReasoningLevels": [
            {"effort": "low", "description": "Quick pass when you want Pro's style with lower latency"},
            {"effort": "medium", "description": "Balanced mode for hard coding, debugging, and nontrivial repo work"},
            {"effort": "high", "description": "Recommended default for stubborn bugs, tricky tool loops, and larger multi-file reasoning"},
            {"effort": "xhigh", "description": "Maximum effort and cost; reserve for the nastiest bugs, ambiguity, or review-heavy work"},
        ],
        "defaultThinking": "high",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": False,
        "supportsSearchTool": True,
        "supportsVerbosity": False,
        "defaultVerbosity": "low",
        "supportsReasoningSummaries": False,
        "reasoningSummaryFormat": None,
        "policyRole": "escalation_implementer",
        "roleHint": "escalation-worker",
        "costClass": "medium",
        "compatibilityClass": "bridged",
        "usageTier": "escalation_implementation",
        "recommendedTasks": ["higher-risk implementation", "multi-file debugging", "architecture-sensitive edits", "fallback from degraded flash"],
        "avoidTasks": ["cheap bulk work"],
        "recommendedForSummary": "Escalation OpenCode Go worker for harder debugging, multi-file fixes, and architecture-sensitive implementation.",
        "avoidForSummary": "Avoid using it for cheap repetitive work where Flash is sufficient.",
        "continuationReliability": "strong",
        "toolLoopReliability": "strong",
        "compatibilityNotes": "Bridged through the local Responses/SSE proxy. Best third-party implementation lane here when Flash is not enough.",
        "knownFailureModes": [
            "transport remains sensitive to stale loaded Codex sessions even when fresh wrapper smoke passes",
        ],
        "aliases": ["pro", "deepseek-pro", "v4-pro", "deepseek v4 pro", "deepseekv4pro"],
        "enabled": True,
        "disabledReason": None,
        "description": "OpenCode Go escalation worker. 1M context, high-effort default, suited for harder debugging, multi-file fixes, and architecture-sensitive implementation. Uses OpenCode Go credits.",
    },
    "glm-5.2": {
        "slug": "glm-5.2",
        "displayName": "GLM-5.2",
        "family": "glm",
        "provider": "opencode-go",
        "providerLabel": "OpenCode Go",
        "providerCreditSource": "opencode-go",
        "transportRoute": "chat",
        "contextWindow": 1000000,
        "supportedReasoningLevels": [
            {"effort": "low", "description": "Quick long-context pass for broad scans and rough synthesis"},
            {"effort": "medium", "description": "Balanced long-context mode for planning, repo reasoning, and implementation work"},
            {"effort": "high", "description": "Recommended default for multi-file reasoning, tricky refactors, and architecture-sensitive work"},
            {"effort": "xhigh", "description": "Maximum patience for ambiguous problems, long-context debugging, and stubborn architecture questions"},
        ],
        "defaultThinking": "high",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": False,
        "supportsSearchTool": True,
        "supportsVerbosity": False,
        "defaultVerbosity": "low",
        "supportsReasoningSummaries": False,
        "reasoningSummaryFormat": None,
        "policyRole": "long_context_synthesizer",
        "roleHint": "long-context-worker",
        "costClass": "medium",
        "compatibilityClass": "bridged",
        "usageTier": "allowed_fallback",
        "recommendedTasks": ["large-context scans", "repo synthesis", "architecture mapping", "repo exploration"],
        "avoidTasks": ["cheap repetitive helper work"],
        "recommendedForSummary": "Long-context OpenCode Go worker for large repo scans, planning, synthesis, and broad context reduction before implementation.",
        "avoidForSummary": "Avoid low-value cheap helper work when a simpler worker would suffice.",
        "continuationReliability": "strong",
        "toolLoopReliability": "strong",
        "compatibilityNotes": "Bridged through the local Responses/SSE proxy. Best third-party option for broad repo reading and synthesis before coding.",
        "knownFailureModes": [],
        "aliases": ["glm52", "glm 5.2", "glm-5.2"],
        "enabled": True,
        "disabledReason": None,
        "description": "OpenCode Go long-context analysis worker. 1M context, high-effort default, best for repo scans, planning, synthesis, and broad context reduction. Uses OpenCode Go credits.",
    },
    "kimi-k2.7-code": {
        "slug": "kimi-k2.7-code",
        "displayName": "Kimi K2.7 Code",
        "family": "kimi",
        "provider": "opencode-go",
        "providerLabel": "OpenCode Go",
        "providerCreditSource": "opencode-go",
        "transportRoute": "chat",
        "contextWindow": 262144,
        "supportedReasoningLevels": [
            {"effort": "low", "description": "Fast coding pass when latency matters more than completeness"},
            {"effort": "medium", "description": "Balanced mode for edits, debugging, and test-oriented code work"},
            {"effort": "high", "description": "Recommended default for subtle bugs, larger changes, and steadier coding work"},
            {"effort": "xhigh", "description": "Use when the bug is stubborn and you want extra persistence before escalating to a GPT manager"},
        ],
        "defaultThinking": "high",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": False,
        "supportsSearchTool": True,
        "supportsVerbosity": False,
        "defaultVerbosity": "low",
        "supportsReasoningSummaries": False,
        "reasoningSummaryFormat": None,
        "policyRole": "rival_coder",
        "roleHint": "coding-specialist-worker",
        "costClass": "medium",
        "compatibilityClass": "bridged",
        "usageTier": "allowed_fallback",
        "recommendedTasks": ["independent second implementation", "adversarial debugging pass", "code-heavy implementation"],
        "avoidTasks": ["cheap bulk scans"],
        "recommendedForSummary": "Coding-specialist OpenCode Go worker for direct edits, debugging, tests, and second-pass implementation.",
        "avoidForSummary": "Avoid cheap bulk scan work where GLM or MiMo is a better fit.",
        "continuationReliability": "strong",
        "toolLoopReliability": "strong",
        "compatibilityNotes": "Bridged through the local Responses/SSE proxy. Good second-pass coder when you want an independent implementation voice.",
        "knownFailureModes": [],
        "aliases": ["kimi-k2-7-code", "kimi k2.7 code", "k2.7-code", "k2.7 code"],
        "enabled": True,
        "disabledReason": None,
        "description": "OpenCode Go coding specialist. 262k context, high-effort default, strong for direct edits, debugging, tests, and second-pass implementation work. Uses OpenCode Go credits.",
    },
    "mimo-v2.5": {
        "slug": "mimo-v2.5",
        "displayName": "MiMo-V2.5",
        "family": "mimo",
        "provider": "opencode-go",
        "providerLabel": "OpenCode Go",
        "providerCreditSource": "opencode-go",
        "transportRoute": "chat",
        "contextWindow": 1000000,
        "supportedReasoningLevels": [
            {"effort": "low", "description": "Fastest mode for cheap helper threads, summaries, and routine tasks"},
            {"effort": "medium", "description": "Recommended default when a low-cost worker needs more care on bounded work"},
            {"effort": "high", "description": "Stretch mode for tougher bounded tasks, validation, and cleanup without switching models"},
            {"effort": "xhigh", "description": "Rare stretch mode only; prefer a stronger worker or GPT manager for very hard tasks"},
        ],
        "defaultThinking": "medium",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": False,
        "supportsSearchTool": True,
        "supportsVerbosity": False,
        "defaultVerbosity": "low",
        "supportsReasoningSummaries": False,
        "reasoningSummaryFormat": None,
        "policyRole": "cheap_support_worker",
        "roleHint": "cheap-helper-worker",
        "costClass": "cheap",
        "compatibilityClass": "bridged",
        "usageTier": "allowed_fallback",
        "recommendedTasks": ["cheap support slices", "classification", "bounded helper tasks", "log triage"],
        "avoidTasks": ["serious architecture or final review"],
        "recommendedForSummary": "Cheap OpenCode Go helper for summaries, low-risk edits, cleanup, and bounded support tasks.",
        "avoidForSummary": "Avoid serious architecture decisions or final review ownership.",
        "continuationReliability": "strong",
        "toolLoopReliability": "strong",
        "compatibilityNotes": "Bridged through the local Responses/SSE proxy. Best used for tightly bounded helper work rather than broad ownership.",
        "knownFailureModes": [],
        "aliases": ["mimo-v25", "mimo-v2_5", "mimo v2.5", "mimo 2.5"],
        "enabled": True,
        "disabledReason": None,
        "description": "OpenCode Go cheap helper. 1M context, medium-effort default, suited for summaries, low-risk edits, cleanup, and bounded support work. Uses OpenCode Go credits.",
    },
    "codex-auto-review": {
        "slug": "codex-auto-review",
        "displayName": "Codex Auto Review",
        "family": "codex",
        "provider": "openai-quota",
        "providerLabel": "Codex internal",
        "providerCreditSource": "codex-quota",
        "transportRoute": "native",
        "contextWindow": 272000,
        "supportedReasoningLevels": NATIVE_REASONING_LEVELS,
        "defaultThinking": "medium",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": False,
        "policyRole": "review_surface",
        "usageTier": "manager_or_final_review",
        "recommendedTasks": ["native auto-review surfaces", "review-only flows"],
        "avoidTasks": ["manager-owned worker lanes", "implementation fan-out"],
        "continuationReliability": "strong",
        "toolLoopReliability": "strong",
        "knownFailureModes": [],
        "aliases": ["auto-review", "codex-auto-review"],
        "enabled": True,
        "disabledReason": None,
        "description": "Native Codex review-only surface, not a general worker lane.",
    },
    "qwen3.7-plus": {
        "slug": "qwen3.7-plus",
        "displayName": "Qwen3.7 Plus",
        "family": "qwen",
        "provider": "opencode-go",
        "providerLabel": "OpenCode Go",
        "providerCreditSource": "opencode-go",
        "transportRoute": "messages",
        "contextWindow": 1000000,
        "supportedReasoningLevels": [
            {"effort": "low", "description": "Fast pass for long-context reading tasks"},
            {"effort": "medium", "description": "Balanced mode for repo reading and synthesis"},
            {"effort": "high", "description": "Higher effort reading and reasoning mode"},
            {"effort": "xhigh", "description": "Maximum effort for stubborn long-context understanding"},
        ],
        "defaultThinking": "medium",
        "supportsTools": True,
        "supportsParallelToolCalls": True,
        "supportsImages": True,
        "policyRole": "disabled",
        "usageTier": "disabled",
        "recommendedTasks": [],
        "avoidTasks": ["all autonomous worker routing"],
        "continuationReliability": "disabled",
        "toolLoopReliability": "disabled",
        "knownFailureModes": [
            "disabled due to continuation reliability and routing policy",
            "messages-route model family is not currently approved for autonomous manager worker lanes",
        ],
        "aliases": ["qwen", "qwen3.7 plus", "qwen3.7-plus"],
        "enabled": False,
        "disabledReason": "Hard-disabled in the project-manager plugin. Use deepseek-v4-flash as the cheap worker and deepseek-v4-pro for harder slices until Qwen transport/reliability is proven.",
        "description": "Explicitly cataloged as disabled until transport and reliability standards are met.",
    },
}
KNOWN_WORKER_MODELS = {
    "deepseek-v4-flash": {
        "role": "fast worker",
        "thinking": "high",
        "recommendedFor": "default cheap OpenCode Go worker for narrow implementation, quick fixes, test repair, mechanical refactors, and bounded exploration",
    },
    "deepseek-v4-pro": {
        "role": "senior worker",
        "thinking": "high",
        "recommendedFor": "larger implementation slices, debugging, architecture-sensitive edits",
    },
    "gpt-5.4": {
        "role": "manager",
        "thinking": "medium",
        "recommendedFor": "default GPT manager/reviewer thread",
    },
    "gpt-5.5": {
        "role": "senior manager",
        "thinking": "high",
        "recommendedFor": "hard root-cause, architecture, and final review decisions",
    },
    "glm-5.2": {
        "role": "long-context worker",
        "thinking": "medium",
        "recommendedFor": "large-context repo scans, planning, synthesis, and broader implementation slices",
    },
    "kimi-k2.7-code": {
        "role": "coding specialist worker",
        "thinking": "medium",
        "recommendedFor": "code-heavy implementation, debugging, tests, and agent-style software work",
    },
    "mimo-v2.5": {
        "role": "cheap support worker",
        "thinking": "low",
        "recommendedFor": "support slices, drafting, classification, and bounded helper tasks",
    },
    "qwen3.7-plus": {
        "role": "disabled worker",
        "thinking": "low",
        "recommendedFor": "disabled in this plugin due continuation reliability and routing policy; use deepseek-v4-flash or deepseek-v4-pro instead",
    },
}
DISABLED_WORKER_MODELS = {
    "qwen3.7-plus": "Hard-disabled in the project-manager plugin. Use deepseek-v4-flash as the main cheap worker and deepseek-v4-pro only for harder escalation slices.",
}
DEFAULT_WORKER_MODELS = (
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "glm-5.2",
    "kimi-k2.7-code",
    "mimo-v2.5",
)
LEDGER_EVENT_TYPES = {
    "tick",
    "dispatch_prepared",
    "dispatch_sent",
    "dispatch_failed",
    "worker_final",
    "thread_observation",
    "model_route",
    "blocker",
    "decision",
    "transaction_prepared",
    "transaction_failed",
    "transaction_finalized",
    "host_action_failed",
    "supervisor_check",
    "automation_updated",
}
PROJECT_PROFILES = {
    "generic": {
        "staleAfterMinutes": 30,
        "ledgerPathHint": "docs/project-manager/manager-ledger.jsonl",
        "registryPathHint": "docs/project-manager/worker-registry.json",
        "transactionJournalPathHint": "docs/project-manager/transaction-journal.jsonl",
        "heartbeatIntervalMinutes": 5,
        "managerModels": ["gpt-5.4", "gpt-5.5"],
        "workerModels": ["deepseek-v4-flash", "deepseek-v4-pro", "glm-5.2", "kimi-k2.7-code", "mimo-v2.5"],
        "defaultWorkerModel": "deepseek-v4-flash",
        "seniorWorkerModel": "deepseek-v4-pro",
        "defaultManagerModel": "gpt-5.4",
        "finalExpectations": ["artifacts", "verification", "blockers", "next_recommended_action"],
    },
    "minecraft": {
        "staleAfterMinutes": 20,
        "ledgerPathHint": "docs/production-readiness/project-manager-ledger.jsonl",
        "registryPathHint": "docs/production-readiness/project-manager-workers.json",
        "transactionJournalPathHint": "docs/production-readiness/project-manager-transactions.jsonl",
        "heartbeatIntervalMinutes": 5,
        "managerModels": ["gpt-5.4", "gpt-5.5"],
        "workerModels": ["deepseek-v4-flash", "deepseek-v4-pro", "glm-5.2", "kimi-k2.7-code", "mimo-v2.5"],
        "defaultWorkerModel": "deepseek-v4-flash",
        "seniorWorkerModel": "deepseek-v4-pro",
        "defaultManagerModel": "gpt-5.5",
        "finalExpectations": ["runtime evidence", "artifact paths", "verification output", "exact blockers"],
    },
    "conan": {
        "staleAfterMinutes": 30,
        "ledgerPathHint": "work/project-manager-ledger.jsonl",
        "registryPathHint": "work/project-manager-workers.json",
        "transactionJournalPathHint": "work/project-manager-transactions.jsonl",
        "heartbeatIntervalMinutes": 5,
        "managerModels": ["gpt-5.4", "gpt-5.5"],
        "workerModels": ["deepseek-v4-flash", "deepseek-v4-pro", "glm-5.2", "kimi-k2.7-code", "mimo-v2.5"],
        "defaultWorkerModel": "deepseek-v4-flash",
        "seniorWorkerModel": "deepseek-v4-pro",
        "defaultManagerModel": "gpt-5.5",
        "finalExpectations": ["packet path", "artifact path", "verification command", "next blocker"],
    },
    "saas": {
        "staleAfterMinutes": 45,
        "ledgerPathHint": "docs/project-manager/manager-ledger.jsonl",
        "registryPathHint": "docs/project-manager/worker-registry.json",
        "transactionJournalPathHint": "docs/project-manager/transaction-journal.jsonl",
        "heartbeatIntervalMinutes": 10,
        "managerModels": ["gpt-5.4", "gpt-5.5"],
        "workerModels": ["deepseek-v4-flash", "deepseek-v4-pro", "glm-5.2", "kimi-k2.7-code", "mimo-v2.5"],
        "defaultWorkerModel": "deepseek-v4-flash",
        "seniorWorkerModel": "deepseek-v4-pro",
        "defaultManagerModel": "gpt-5.4",
        "finalExpectations": ["changed files", "tests", "product risk", "deploy blockers"],
    },
}


def _load_plugin_version(manifest_path: Path = PLUGIN_MANIFEST_PATH, default_version: str = "0.3.2") -> str:
    try:
        parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_version
    return str(parsed.get("version") or default_version)


PLUGIN_VERSION = _load_plugin_version(PLUGIN_MANIFEST_PATH)
CANONICAL_PLUGIN_MANIFEST_PATH = CANONICAL_PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
CANONICAL_PLUGIN_VERSION = _load_plugin_version(CANONICAL_PLUGIN_MANIFEST_PATH, PLUGIN_VERSION)


def _log_event(event: str, **fields: Any) -> None:
    try:
        MCP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "time": _now_iso8601(),
            "event": event,
            **fields,
        }
        with MCP_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    except Exception:
        pass


def _now_iso8601() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_json_file(path_value: str) -> dict[str, Any]:
    path = Path(path_value).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("stateFile must contain a JSON object")
    return parsed


def _merge_profile(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if value is not None:
            merged[key] = value
    return merged


def _profile_settings_from_args(args: dict[str, Any]) -> tuple[str, dict[str, Any], str | None]:
    profile_name = str(args.get("profile") or "generic").strip().lower()
    base = PROJECT_PROFILES.get(profile_name, PROJECT_PROFILES["generic"])
    resolved_name = profile_name if profile_name in PROJECT_PROFILES else "generic"
    profile_file = args.get("profileFile")
    if not profile_file:
        return resolved_name, base, None
    try:
        override = _read_json_file(str(profile_file))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return resolved_name, base, str(exc)
    selected = override.get("profile")
    if isinstance(selected, str) and selected.strip():
        selected_name = selected.strip().lower()
        base = PROJECT_PROFILES.get(selected_name, PROJECT_PROFILES["generic"])
        resolved_name = selected_name if selected_name in PROJECT_PROFILES else "generic"
    settings = override.get("settings") if isinstance(override.get("settings"), dict) else override
    return resolved_name, _merge_profile(base, settings), None


def _model_meta(model: str, role_hint: str = "worker") -> dict[str, Any]:
    entry = _find_catalog_entry(model, include_disabled=True)
    if entry:
        return {
            "role": entry.get("policyRole") or role_hint,
            "thinking": entry.get("defaultThinking") or "medium",
            "recommendedFor": ", ".join(str(item) for item in entry.get("recommendedTasks") or []),
            "providerLabel": entry.get("providerLabel"),
            "transportRoute": entry.get("transportRoute"),
            "usageTier": entry.get("usageTier"),
            "enabled": bool(entry.get("enabled")),
            "disabledReason": entry.get("disabledReason"),
        }
    return {
        "role": role_hint,
        "thinking": "medium",
        "recommendedFor": "profile-provided model; follow project-owned routing policy",
        "providerLabel": None,
        "transportRoute": "unknown",
        "usageTier": "allowed_fallback",
        "enabled": True,
        "disabledReason": None,
    }


def _profile_model_list(settings: dict[str, Any], key: str, fallback: list[str]) -> list[str]:
    value = settings.get(key)
    if isinstance(value, list):
        models = [str(item).strip() for item in value if str(item).strip()]
        if models:
            return models
    return fallback


def _disabled_worker_model(model: Any) -> str | None:
    if not isinstance(model, str) or not model.strip():
        return None
    normalized = _normalize_model(model.strip(), model.strip())
    return normalized if normalized in DISABLED_WORKER_MODELS else None


def _disabled_worker_model_failure(model: str) -> dict[str, Any]:
    return _failure(
        "disabled worker model requested",
        workerModel=model,
        disabledModels=sorted(DISABLED_WORKER_MODELS),
        reason=DISABLED_WORKER_MODELS[model],
    )


def _validate_worker_model_policy(
    worker_models: list[str],
    default_worker_model: str | None = None,
    senior_worker_model: str | None = None,
) -> dict[str, Any] | None:
    candidates = list(worker_models)
    if default_worker_model:
        candidates.append(default_worker_model)
    if senior_worker_model:
        candidates.append(senior_worker_model)
    for candidate in candidates:
        disabled = _disabled_worker_model(candidate)
        if disabled:
            return _disabled_worker_model_failure(disabled)
    return None


def _path_status(path_value: Any, project_root: Any = None) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value.strip():
        return {"path": None, "exists": False, "parentExists": False, "status": "missing"}
    path = Path(path_value).expanduser()
    if not path.is_absolute() and isinstance(project_root, str) and project_root.strip():
        path = Path(project_root).expanduser() / path
    return {
        "path": str(path),
        "exists": path.exists(),
        "parentExists": path.parent.exists(),
        "status": "ready" if path.exists() else ("parent_ready" if path.parent.exists() else "parent_missing"),
    }


def _resolve_ledger_path(path_value: Any) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("ledgerFile is required")
    path = Path(path_value).expanduser()
    if path.exists() and path.is_dir():
        raise ValueError(f"ledgerFile must be a file path, not a directory: {path}")
    return path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        parsed = json.loads(line)
        if not isinstance(parsed, dict):
            raise ValueError(f"ledger line {line_number} is not a JSON object")
        events.append(parsed)
    return events


def _write_jsonl_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def _read_registry(path_value: Any) -> tuple[Path, dict[str, Any]]:
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("registryFile is required")
    path = Path(path_value).expanduser()
    if not path.exists():
        return path, {"workers": {}, "updated_at": None}
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("registryFile must contain a JSON object")
    return path, _normalize_registry(parsed)


def _write_registry(path: Path, registry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _registry_field(worker: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in worker and worker.get(key) is not None:
            return worker.get(key)
    return None


def _normalize_registry_worker(raw_worker: Any) -> dict[str, Any]:
    worker = dict(raw_worker) if isinstance(raw_worker, Mapping) else {}
    normalized = dict(worker)
    normalized["deliveryVisible"] = bool(
        _registry_field(worker, "deliveryVisible", "delivery_visible", "deliveryVerified", "delivery_verified") or False
    )
    normalized["workerAcknowledged"] = bool(
        _registry_field(worker, "workerAcknowledged", "worker_acknowledged") or False
    )
    normalized["acknowledgedAt"] = _registry_field(worker, "acknowledgedAt", "acknowledged_at")
    normalized["acknowledgedTurnId"] = _registry_field(worker, "acknowledgedTurnId", "acknowledged_turn_id")
    normalized["acknowledgedMessageId"] = _registry_field(worker, "acknowledgedMessageId", "acknowledged_message_id")
    normalized["progressState"] = _registry_field(worker, "progressState", "progress_state") or "unknown"
    normalized["evidenceSource"] = _registry_field(worker, "evidenceSource", "evidence_source")
    normalized["transportConfidenceAtDispatch"] = _registry_field(
        worker,
        "transportConfidenceAtDispatch",
        "transport_confidence_at_dispatch",
    )
    normalized["packetRole"] = _registry_field(worker, "packetRole", "packet_role") or "implementer"
    normalized["lastVisibleTurnAt"] = _registry_field(worker, "lastVisibleTurnAt", "last_visible_turn_at")
    normalized["lastVerifiedHealthyAt"] = _registry_field(worker, "lastVerifiedHealthyAt", "last_verified_healthy_at")
    normalized["deliveryTurnId"] = _registry_field(worker, "deliveryTurnId", "delivery_turn_id")
    normalized["deliveryMessageId"] = _registry_field(worker, "deliveryMessageId", "delivery_message_id")
    normalized["deliveryVerificationEvidence"] = _registry_field(
        worker,
        "deliveryVerificationEvidence",
        "delivery_verification_evidence",
    )
    normalized["lastReadbackSummary"] = _registry_field(worker, "lastReadbackSummary", "last_readback_summary")
    normalized["deliveryVerified"] = bool(_registry_field(worker, "deliveryVerified", "delivery_verified") or False)
    normalized["replacementOfThreadId"] = _registry_field(worker, "replacementOfThreadId", "replacement_of_thread_id")
    normalized["deadReferenceReason"] = _registry_field(worker, "deadReferenceReason", "dead_reference_reason")
    stale_confidence = _registry_field(worker, "staleConfidence", "stale_confidence")
    if isinstance(stale_confidence, (int, float)):
        normalized["staleConfidence"] = float(stale_confidence)
    else:
        normalized["staleConfidence"] = 0.0
    return normalized


def _normalize_registry(registry: dict[str, Any]) -> dict[str, Any]:
    workers = registry.get("workers")
    if not isinstance(workers, dict):
        registry["workers"] = {}
    else:
        registry["workers"] = {
            str(worker_id): _normalize_registry_worker(worker)
            for worker_id, worker in workers.items()
        }
    archived_workers = registry.get("archivedWorkers")
    if not isinstance(archived_workers, dict):
        registry["archivedWorkers"] = {}
    else:
        registry["archivedWorkers"] = {
            str(worker_id): _normalize_registry_worker(worker)
            for worker_id, worker in archived_workers.items()
        }
    return registry


def _failure(error: str, **extra: Any) -> dict[str, Any]:
    return {"status": "failed", "error": error, **extra}


def _success(**extra: Any) -> dict[str, Any]:
    return {"status": "ok", **extra}


def _normalize_prompt_text(value: Any, *, max_chars: int, field_name: str) -> tuple[str, list[str]]:
    text = str(value or "")
    warnings: list[str] = []
    if not text.strip():
        return "", warnings
    decoded = html.unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    matches = re.findall(r"<input>(.*?)</input>", decoded, flags=re.IGNORECASE | re.DOTALL)
    if matches:
        decoded = matches[-1].strip()
        warnings.append(f"{field_name}: nested_codex_delegation_compacted")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in decoded.splitlines()]
    compacted = "\n".join(line for line in lines if line)
    compacted = re.sub(r"\n{3,}", "\n\n", compacted).strip()
    if len(compacted) > max_chars:
        compacted = compacted[: max(0, max_chars - 72)].rstrip() + " [truncated for Codex transport safety]"
        warnings.append(f"{field_name}: truncated")
    return compacted, warnings


def _safe_packet_prompt(
    *,
    title: Any,
    assignment_id: Any,
    assignment_path: Any,
    goal: Any,
    constraints: Any,
    definition_of_done: Any,
    packet_role: str,
    worker_model: str,
    model_guidance: str,
    include_manager_banner: bool,
    final_instruction: str,
) -> tuple[str, dict[str, Any]]:
    warnings: list[str] = []
    safe_title, title_warnings = _normalize_prompt_text(title, max_chars=MAX_PROMPT_TITLE_CHARS, field_name="title")
    safe_path, path_warnings = _normalize_prompt_text(assignment_path, max_chars=MAX_PROMPT_PATH_CHARS, field_name="assignment_path")
    safe_goal, goal_warnings = _normalize_prompt_text(goal, max_chars=MAX_PROMPT_GOAL_CHARS, field_name="goal")
    safe_constraints, constraints_warnings = _normalize_prompt_text(
        constraints, max_chars=MAX_PROMPT_CONSTRAINTS_CHARS, field_name="constraints"
    )
    safe_dod, dod_warnings = _normalize_prompt_text(
        definition_of_done, max_chars=MAX_PROMPT_DOD_CHARS, field_name="definition_of_done"
    )
    safe_guidance, guidance_warnings = _normalize_prompt_text(
        model_guidance, max_chars=900, field_name="model_guidance"
    )
    warnings.extend(title_warnings + path_warnings + goal_warnings + constraints_warnings + dod_warnings + guidance_warnings)
    sections = [safe_title or f"PM worker {assignment_id}"]
    if include_manager_banner:
        sections.append("You are a Codex worker thread managed by a GPT project-manager thread.")
    sections.append(f"assignment_id: {assignment_id}")
    sections.append(f"assignment_path: {safe_path}")
    sections.append(f"goal: {safe_goal}")
    sections.append(f"constraints: {safe_constraints}")
    sections.append(f"definition_of_done: {safe_dod}")
    sections.append(_packet_role_contract(packet_role))
    sections.append(_packet_guidance_block(packet_role, worker_model))
    sections.append(safe_guidance)
    sections.append(final_instruction)
    prompt = "\n\n".join(section for section in sections if section)
    if len(prompt) > MAX_INLINE_PROMPT_CHARS:
        prompt = prompt[: max(0, MAX_INLINE_PROMPT_CHARS - 80)].rstrip() + "\n\n[prompt truncated for Codex transport safety; use assignment_path as source of truth]"
        warnings.append("prompt: truncated")
    return prompt, {
        "maxInlinePromptChars": MAX_INLINE_PROMPT_CHARS,
        "promptChars": len(prompt),
        "compacted": bool(warnings),
        "warnings": warnings,
    }


def _mcp_runtime_status() -> tuple[dict[str, Any], list[str]]:
    config_path = PLUGIN_ROOT / ".mcp.json"
    expected_wrapper = PLUGIN_ROOT / "scripts" / "project-manager-mcp.exe"
    status: dict[str, Any] = {
        "mcpConfigPath": str(config_path),
        "mcpConfigExists": config_path.exists(),
        "mcpCommand": None,
        "mcpArgs": [],
        "mcpWrapperPath": str(expected_wrapper),
        "mcpWrapperExists": expected_wrapper.exists(),
        "stdioWrapperReady": False,
    }
    issues: list[str] = []
    if not config_path.exists():
        issues.append(".mcp.json missing")
        return status, issues
    try:
        parsed = json.loads(config_path.read_text(encoding="utf-8"))
        server = parsed.get("mcpServers", {}).get("project-manager", {})
        command = server.get("command")
        args = server.get("args") or []
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f".mcp.json unreadable: {exc}")
        return status, issues
    status["mcpCommand"] = command
    status["mcpArgs"] = args if isinstance(args, list) else []
    command_text = str(command or "")
    if command_text.lower().endswith("pythonw.exe") or command_text.lower() == "pythonw":
        issues.append("MCP command uses pythonw; stdio MCP must use the windowless wrapper executable")
    if command_text != WINDOWLESS_STDIO_WRAPPER_COMMAND:
        issues.append(f"MCP command should be {WINDOWLESS_STDIO_WRAPPER_COMMAND}")
    if not expected_wrapper.exists():
        issues.append("project-manager-mcp.exe wrapper missing")
    status["stdioWrapperReady"] = (
        status["mcpConfigExists"]
        and status["mcpWrapperExists"]
        and command_text == WINDOWLESS_STDIO_WRAPPER_COMMAND
    )
    return status, issues


def _missing_fields(payload: dict[str, Any], required: list[str]) -> list[str]:
    missing: list[str] = []
    for key in required:
        value = payload.get(key)
        if value is None:
            missing.append(key)
            continue
        if isinstance(value, str) and not value.strip():
            missing.append(key)
    return missing


def _coerce_worker_final(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("workerFinalJson is required; provide a JSON object string")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("workerFinalJson must decode to a JSON object")
    return parsed


def _coerce_worker_final_from_args(args: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    worker_final_path = args.get("workerFinalPath")
    if isinstance(worker_final_path, str) and worker_final_path.strip():
        path = Path(worker_final_path).expanduser()
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"workerFinalPath unreadable: {exc}") from exc
        parsed = _coerce_worker_final(text)
        return parsed, {"source": "path", "workerFinalPath": str(path), "workerFinalChars": len(text)}
    raw = args.get("workerFinalJson")
    parsed = _coerce_worker_final(raw)
    text = raw if isinstance(raw, str) else json.dumps(raw, separators=(",", ":"))
    return parsed, {"source": "inline_json", "workerFinalChars": len(text)}


def _coerce_workers(raw_workers: Any) -> list[dict[str, Any]]:
    if raw_workers is None:
        return []
    if isinstance(raw_workers, list):
        return [worker for worker in raw_workers if isinstance(worker, dict)]
    if isinstance(raw_workers, dict):
        workers: list[dict[str, Any]] = []
        for label, raw_worker in raw_workers.items():
            if not isinstance(raw_worker, dict):
                continue
            worker = dict(raw_worker)
            worker.setdefault("label", str(label))
            workers.append(worker)
        return workers
    return []


def _worker_identifier(worker: dict[str, Any]) -> str:
    for key in ("label", "name", "thread_id", "threadId", "id"):
        value = worker.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "worker"


def _worker_last_progress(worker: dict[str, Any]) -> datetime | None:
    for key in (
        "lastVisibleTurnAt",
        "last_visible_turn_at",
        "acknowledgedAt",
        "acknowledged_at",
        "lastVerifiedHealthyAt",
        "last_verified_healthy_at",
        "last_progress_at",
        "lastProgressAt",
        "updated_at",
        "updatedAt",
        "heartbeat_at",
        "heartbeatAt",
    ):
        parsed = _parse_time(worker.get(key))
        if parsed is not None:
            return parsed
    return None


def _worker_blockers(worker: dict[str, Any]) -> list[Any]:
    blockers = worker.get("blockers")
    if isinstance(blockers, list):
        return blockers
    blocker = worker.get("blocker")
    if blocker:
        return [blocker]
    return []


def _classify_worker(worker: dict[str, Any], now: datetime, stale_after_minutes: int) -> dict[str, Any]:
    worker_id = _worker_identifier(worker)
    declared_status = str(worker.get("status") or worker.get("state") or "unknown").lower()
    blockers = _worker_blockers(worker)
    last_progress_at = _worker_last_progress(worker)
    delivery_visible_raw = _registry_field(worker, "deliveryVisible", "delivery_visible", "deliveryVerified", "delivery_verified")
    delivery_visible = bool(delivery_visible_raw or False)
    delivery_field_present = delivery_visible_raw is not None
    worker_acknowledged = bool(_registry_field(worker, "workerAcknowledged", "worker_acknowledged") or False)
    progress_state = str(_registry_field(worker, "progressState", "progress_state") or "unknown").strip().lower()
    evidence_source = _registry_field(worker, "evidenceSource", "evidence_source")
    last_verified_healthy_at = _registry_field(worker, "lastVerifiedHealthyAt", "last_verified_healthy_at")
    dead_reference_reason = worker.get("deadReferenceReason") or worker.get("dead_reference_reason")
    replacement_of_thread_id = worker.get("replacementOfThreadId") or worker.get("replacement_of_thread_id")
    stale_confidence = worker.get("staleConfidence") if worker.get("staleConfidence") is not None else worker.get("stale_confidence")
    minutes_since_progress: int | None = None
    stale = False
    if last_progress_at is not None:
        elapsed = now - last_progress_at
        minutes_since_progress = max(0, int(elapsed.total_seconds() // 60))
        stale = minutes_since_progress >= stale_after_minutes

    if dead_reference_reason or declared_status in {"dead_reference", "unreadable", "historical_dead"}:
        attention = "dead_reference"
    elif blockers or declared_status in {"blocked", "failed", "interrupted", "error"}:
        attention = "blocked"
    elif declared_status in COMPLETED_WORKER_STATUSES or progress_state == "finaled":
        attention = "needs_review"
    elif declared_status in ACTIVE_WORKER_STATUSES and delivery_field_present and not delivery_visible:
        attention = "unverified_dispatch"
    elif declared_status in ACTIVE_WORKER_STATUSES and delivery_visible and not worker_acknowledged and not last_verified_healthy_at:
        attention = "silent_after_delivery"
    elif stale:
        attention = "stale"
    elif declared_status in ACTIVE_WORKER_STATUSES or progress_state in {"acknowledged", "progressing"}:
        attention = "healthy"
    else:
        attention = "unknown"

    return {
        "worker": worker_id,
        "label": worker.get("label"),
        "threadId": worker.get("threadId") or worker.get("thread_id"),
        "assignmentId": worker.get("assignmentId") or worker.get("assignment_id"),
        "declaredStatus": declared_status,
        "attention": attention,
        "lastProgressAt": last_progress_at.isoformat().replace("+00:00", "Z") if last_progress_at else None,
        "minutesSinceProgress": minutes_since_progress,
        "blockers": blockers,
        "deliveryVisible": delivery_visible,
        "deliveryVerified": delivery_visible,
        "workerAcknowledged": worker_acknowledged,
        "acknowledgedAt": _registry_field(worker, "acknowledgedAt", "acknowledged_at"),
        "acknowledgedTurnId": _registry_field(worker, "acknowledgedTurnId", "acknowledged_turn_id"),
        "acknowledgedMessageId": _registry_field(worker, "acknowledgedMessageId", "acknowledged_message_id"),
        "progressState": progress_state,
        "evidenceSource": evidence_source,
        "transportConfidenceAtDispatch": _registry_field(worker, "transportConfidenceAtDispatch", "transport_confidence_at_dispatch"),
        "lastVisibleTurnAt": worker.get("lastVisibleTurnAt") or worker.get("last_visible_turn_at"),
        "lastVerifiedHealthyAt": worker.get("lastVerifiedHealthyAt") or worker.get("last_verified_healthy_at"),
        "deliveryTurnId": _registry_field(worker, "deliveryTurnId", "delivery_turn_id"),
        "deliveryMessageId": _registry_field(worker, "deliveryMessageId", "delivery_message_id"),
        "deliveryVerificationEvidence": _registry_field(worker, "deliveryVerificationEvidence", "delivery_verification_evidence"),
        "lastReadbackSummary": _registry_field(worker, "lastReadbackSummary", "last_readback_summary"),
        "replacementOfThreadId": replacement_of_thread_id,
        "deadReferenceReason": dead_reference_reason,
        "staleConfidence": float(stale_confidence) if isinstance(stale_confidence, (int, float)) else 0.0,
    }


def _recommend_next_action(classified_workers: list[dict[str, Any]], dispatch_required: bool) -> str:
    dead_reference = [worker for worker in classified_workers if worker["attention"] == "dead_reference"]
    blocked = [worker for worker in classified_workers if worker["attention"] == "blocked"]
    review = [worker for worker in classified_workers if worker["attention"] == "needs_review"]
    silent = [worker for worker in classified_workers if worker["attention"] == "silent_after_delivery"]
    stale = [worker for worker in classified_workers if worker["attention"] == "stale"]
    unverified = [worker for worker in classified_workers if worker["attention"] == "unverified_dispatch"]
    unknown = [worker for worker in classified_workers if worker["attention"] == "unknown"]
    if dead_reference:
        return f"replace_dead_reference_worker:{dead_reference[0]['worker']}"
    if blocked:
        return f"read_or_recover_blocked_worker:{blocked[0]['worker']}"
    if review:
        return f"review_worker_final:{review[0]['worker']}"
    if silent:
        return f"recover_silent_lane:{silent[0]['worker']}"
    if stale:
        return f"read_or_reassign_stale_worker:{stale[0]['worker']}"
    if unverified:
        return f"verify_dispatch_delivery:{unverified[0]['worker']}"
    if dispatch_required:
        return "prepare_next_dispatch"
    if unknown:
        return f"inspect_unknown_worker:{unknown[0]['worker']}"
    return "no_interrupt_active_workers"


def _heartbeat_decision_hint(attention_required: bool) -> str:
    return "NOTIFY" if attention_required else "DONT_NOTIFY"


def _worker_recommended_action(worker: dict[str, Any]) -> str:
    attention = str(worker.get("attention") or "unknown")
    worker_id = str(worker.get("worker") or "worker")
    mapping = {
        "dead_reference": f"replace_dead_reference_worker:{worker_id}",
        "blocked": f"read_or_recover_blocked_worker:{worker_id}",
        "needs_review": f"review_worker_final:{worker_id}",
        "silent_after_delivery": f"recover_silent_lane:{worker_id}",
        "stale": f"read_or_reassign_stale_worker:{worker_id}",
        "unverified_dispatch": f"verify_dispatch_delivery:{worker_id}",
        "unknown": f"inspect_unknown_worker:{worker_id}",
        "healthy": f"no_interrupt_active_worker:{worker_id}",
    }
    return mapping.get(attention, f"inspect_unknown_worker:{worker_id}")


def _worker_action_severity(worker: dict[str, Any]) -> int:
    attention = str(worker.get("attention") or "unknown")
    return {
        "dead_reference": 100,
        "blocked": 90,
        "silent_after_delivery": 85,
        "unverified_dispatch": 80,
        "stale": 70,
        "needs_review": 60,
        "unknown": 50,
        "healthy": 10,
    }.get(attention, 40)


def _operator_runbook_steps(action: str) -> list[str]:
    normalized = action.strip().lower()
    if normalized == "reload session":
        return [
            "Stop trusting the current thread-bound MCP transport for new delivery decisions.",
            "If a healthy external manager thread or heartbeat still has a working project-manager MCP surface, prefer `manager_loaded_turn_rescue_plan` to send a fresh same-thread rebind follow-up before abandoning the manager thread entirely.",
            "Open a fresh Codex thread or restart the affected Codex session if the same stale transport symptoms persist.",
            "Run `manager_environment_health` first in the fresh session and confirm `transportHealth.recommendedOperatorAction` is no longer `reload session`.",
            "Resume worker coordination only through verified flows such as `manager_verified_dispatch` or `manager_replace_dead_lane`.",
        ]
    if normalized == "new thread recommended":
        return [
            "Preserve current state with the project ledger, registry, or a compact handoff before switching threads.",
            "Open a fresh Codex thread for this manager role and carry forward only durable project state, not assumptions from the stale thread.",
            "Run `manager_environment_health` and then re-read the registry/ledger before attempting any worker delivery.",
            "Treat any prior lane as healthy only after fresh thread readback or direct-manager artifact evidence confirms it.",
        ]
    return [
        "Run `manager_environment_health` and verify transport health is acceptable for continued operation.",
        "Use `manager_tick` or `manager_operational_audit` to determine whether any lane needs review, replacement, or verified dispatch follow-up.",
        "Use `manager_verified_dispatch` for delivery and `manager_replace_dead_lane` for unreadable/dead historical workers instead of manual bookkeeping.",
        "Update the registry and ledger only from verified readback or direct manager takeover artifacts.",
    ]


def _normalize_model(model: Any, default: str = "deepseek-v4-flash") -> str:
    if not isinstance(model, str) or not model.strip():
        return default
    entry = _find_catalog_entry(model, include_disabled=True)
    if entry:
        return str(entry["slug"])
    return model.strip()


def _thinking_for_model(model: str, requested: Any = None) -> str:
    if isinstance(requested, str) and requested.strip():
        return requested.strip()
    meta = _model_meta(model)
    if meta:
        return str(meta["thinking"])
    return "medium"


def _select_worker_model(args: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any] | dict[str, str]:
    worker_models = [_normalize_model(model) for model in _profile_model_list(settings, "workerModels", list(DEFAULT_WORKER_MODELS))]
    default_worker_model = _normalize_model(settings.get("defaultWorkerModel"), worker_models[0] if worker_models else "deepseek-v4-flash")
    senior_worker_model = _normalize_model(settings.get("seniorWorkerModel"), worker_models[-1] if worker_models else "deepseek-v4-pro")
    disabled_failure = _validate_worker_model_policy(worker_models, default_worker_model, senior_worker_model)
    if disabled_failure:
        return disabled_failure
    requested_model = _normalize_model(args.get("workerModel"), default_worker_model)
    disabled = _disabled_worker_model(requested_model)
    if disabled:
        return _disabled_worker_model_failure(disabled)
    if args.get("workerModel"):
        return {
            "workerModel": requested_model,
            "defaultWorkerModel": default_worker_model,
            "seniorWorkerModel": senior_worker_model,
            "escalated": requested_model == senior_worker_model and requested_model != default_worker_model,
            "reason": "explicit workerModel request",
            "policy": "requested",
        }
    assignment_risk = str(args.get("assignmentRisk") or "routine").strip().lower()
    packet_shape = str(args.get("packetShape") or "narrow").strip().lower()
    packet_role = str(args.get("packetRole") or "implementer").strip().lower()
    need_long_context = bool(args.get("needLongContext"))
    needs_native_quota = bool(args.get("needsNativeQuota"))
    architecture_sensitive = bool(args.get("architectureSensitive"))
    multi_file_debugging = bool(args.get("multiFileDebugging"))
    repeated_blockage = bool(args.get("repeatedImplementerBlockage") or args.get("priorFlashBlocked"))
    transport_confidence = str(args.get("transportConfidence") or "healthy").strip().lower()
    pressure_summary = _model_pressure_summary({"evidenceFile": args.get("evidenceFile")})
    flash_pressure = (pressure_summary.get("models") or {}).get("deepseek-v4-flash", {})
    flash_degraded = str(flash_pressure.get("reliabilityStatus") or "healthy") in {"degraded", "single_turn_only"}
    if packet_role == "repo_explorer" or need_long_context:
        return {
            "workerModel": "glm-5.2",
            "defaultWorkerModel": default_worker_model,
            "seniorWorkerModel": senior_worker_model,
            "escalated": False,
            "reason": "long-context repo exploration or synthesis",
            "policy": f"profile-driven:{packet_role}",
        }
    if packet_role == "code_quality_reviewer" and needs_native_quota:
        return {
            "workerModel": "gpt-5.4",
            "defaultWorkerModel": default_worker_model,
            "seniorWorkerModel": senior_worker_model,
            "escalated": True,
            "reason": "native senior review requested",
            "policy": f"profile-driven:{packet_role}",
        }
    higher_risk = (
        assignment_risk in {"high", "elevated", "senior", "critical"}
        or packet_shape in {"large", "broad", "wide"}
        or architecture_sensitive
        or multi_file_debugging
        or repeated_blockage
        or flash_degraded
        or transport_confidence in {"degraded", "poor", "reload_session", "new_thread_recommended"}
    )
    selected = senior_worker_model if higher_risk else default_worker_model
    disabled = _disabled_worker_model(selected)
    if disabled:
        return _disabled_worker_model_failure(disabled)
    reason = "routine narrow slice"
    if higher_risk:
        if transport_confidence in {"degraded", "poor", "reload_session", "new_thread_recommended"}:
            reason = "flash transport confidence degraded"
        elif flash_degraded:
            reason = "flash pressure evidence degraded"
        elif repeated_blockage:
            reason = "prior flash blockage or repeated implementer blockage"
        elif architecture_sensitive or multi_file_debugging:
            reason = "architecture-sensitive or multi-file debugging slice"
        else:
            reason = "high-risk slice"
    return {
        "workerModel": selected,
        "defaultWorkerModel": default_worker_model,
        "seniorWorkerModel": senior_worker_model,
        "escalated": higher_risk,
        "reason": reason,
        "policy": f"profile-driven:{packet_role}",
    }


def _packet_role_contract(packet_role: str) -> str:
    if packet_role == "repo_explorer":
        return (
            "Read broadly enough to map the relevant repo/runtime surfaces, but do not change code. "
            "Return touched paths, architecture constraints, risks, and the smallest useful next implementation slice."
        )
    if packet_role == "log_analyst":
        return (
            "Analyze logs, traces, and failure evidence only. "
            "Return the most likely failure classes, supporting evidence, and the next narrow debugging step."
        )
    if packet_role == "spec_reviewer":
        return (
            "Review the implementation strictly against the assignment/spec. "
            "Do not broaden scope. Return whether the packet satisfies the requested contract, what is missing, and whether the next step should be rework or code-quality review."
        )
    if packet_role == "code_quality_reviewer":
        return (
            "Review the already-implemented packet for code quality, maintainability, and regression risk. "
            "Do not invent new scope. Return whether the packet is ready for manager acceptance or needs targeted rework."
        )
    return (
        "Implement exactly one bounded assignment packet. "
        "Do not broaden scope. Produce concrete artifacts, verification, blockers, and a deterministic next action."
    )


def _packet_expected_evidence(packet_role: str) -> str:
    mapping = {
        "implementer": "changed files, concrete artifacts, verification commands/results, blockers, next action",
        "repo_explorer": "read paths, architecture constraints, risk notes, next implementation slice",
        "log_analyst": "log fragments, failure classes, supporting evidence, next debugging step",
        "spec_reviewer": "pass/fail against the spec, exact missing items, whether to rework or proceed",
        "code_quality_reviewer": "quality findings, regression risks, approval or rework decision",
    }
    return mapping.get(packet_role, "artifacts, verification, blockers, next action")


def _packet_allowed_scope(packet_role: str) -> str:
    mapping = {
        "implementer": "one bounded implementation slice",
        "repo_explorer": "read-only, broad enough to map the relevant repo surface",
        "log_analyst": "read-only evidence analysis",
        "spec_reviewer": "review only; no scope expansion",
        "code_quality_reviewer": "review only; no scope expansion",
    }
    return mapping.get(packet_role, "one bounded slice")


def _packet_escalation_boundary(packet_role: str) -> str:
    mapping = {
        "implementer": "escalate if architecture changes, repeated blockage, or the task broadens materially",
        "repo_explorer": "escalate if missing context prevents a stable map of the relevant surfaces",
        "log_analyst": "escalate if evidence is insufficient to distinguish the likely failure classes",
        "spec_reviewer": "escalate only when the spec itself is ambiguous",
        "code_quality_reviewer": "escalate only when review requires manager-grade judgment or policy change",
    }
    return mapping.get(packet_role, "escalate when the slice cannot stay bounded")


def _packet_guidance_block(packet_role: str, model_slug: str) -> str:
    entry = _find_catalog_entry(model_slug, include_disabled=True) or {}
    parts = [
        f"packet_role: {packet_role}",
        f"worker_model: {model_slug}",
        f"transport_route: {entry.get('transportRoute') or 'unknown'}",
        f"expected_evidence: {_packet_expected_evidence(packet_role)}",
        f"allowed_scope: {_packet_allowed_scope(packet_role)}",
        f"escalation_boundary: {_packet_escalation_boundary(packet_role)}",
    ]
    guidance = _catalog_entry_model_guidance(entry)
    if guidance:
        parts.append(guidance)
    return "\n".join(parts)


def _native_thread_creation_surface(requested_model: str | None = None) -> dict[str, Any]:
    payload = {
        "surface": "create_thread.model",
        "modelAware": True,
        "consistency": "native",
    }
    if requested_model:
        payload["requestedModel"] = requested_model
    return payload


def _active_cache_version() -> str | None:
    if not CACHE_PLUGIN_BASE.exists():
        return None
    candidates = [path for path in CACHE_PLUGIN_BASE.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime).name


def _plugin_metadata(root: Path) -> dict[str, Any] | None:
    manifest_path = root / ".codex-plugin" / "plugin.json"
    if not manifest_path.exists():
        return None
    try:
        parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict):
        return None
    return {
        "root": str(root),
        "manifestPath": str(manifest_path),
        "version": str(parsed.get("version") or ""),
        "name": str(parsed.get("name") or ""),
    }


def _plugin_root_kind(root: Path | None) -> str:
    if root is None:
        return "missing"
    try:
        resolved = str(root.resolve()).lower()
    except OSError:
        resolved = str(root).lower()
    if resolved == str(CANONICAL_PLUGIN_ROOT).lower():
        return "canonical"
    if resolved == str(AGENTS_PLUGIN_ROOT).lower():
        return "mirror"
    if "\\plugins\\cache\\personal\\project-manager\\" in resolved:
        return "cache"
    return "other"


def _plugin_wrapper_path(root: Path | None) -> Path | None:
    if root is None:
        return None
    return root / "scripts" / "project-manager-mcp.exe"


def _plugin_wrapper_hash(root: Path | None) -> str | None:
    wrapper_path = _plugin_wrapper_path(root)
    if wrapper_path is None:
        return None
    return _file_sha256(wrapper_path)


def _source_alignment_status(
    *,
    resolved_root: Path,
    resolved_version: str | None,
    canonical_version: str | None,
    canonical_wrapper_hash: str | None,
    mirror_version: str | None,
    mirror_wrapper_hash: str | None,
    cache_version: str | None,
) -> str:
    resolved_kind = _plugin_root_kind(resolved_root)
    resolved_wrapper_hash = _plugin_wrapper_hash(resolved_root)
    if not canonical_version:
        return "canonical_missing"
    if resolved_kind == "canonical":
        if resolved_version == canonical_version and resolved_wrapper_hash == canonical_wrapper_hash:
            return "aligned"
        return "resolved_version_drift"
    if resolved_kind == "mirror":
        if (
            resolved_version == canonical_version
            and resolved_wrapper_hash == canonical_wrapper_hash
            and mirror_version == canonical_version
            and mirror_wrapper_hash == canonical_wrapper_hash
            and (not cache_version or cache_version == canonical_version)
        ):
            return "aligned_via_mirror"
        if mirror_version != canonical_version or mirror_wrapper_hash != canonical_wrapper_hash:
            return "mirror_drift"
        if cache_version and cache_version != canonical_version:
            return "cache_drift"
        return "resolved_version_drift"
    if resolved_kind == "cache":
        if resolved_version == canonical_version and resolved_wrapper_hash == canonical_wrapper_hash:
            return "aligned_via_cache"
        return "cache_drift"
    if cache_version and cache_version != canonical_version:
        return "cache_drift"
    return "resolved_root_drift"


def _plugin_install_state() -> dict[str, Any]:
    active_cache_version = _active_cache_version()
    active_cache_root = CACHE_PLUGIN_BASE / active_cache_version if active_cache_version else None
    source_meta = _plugin_metadata(SOURCE_PLUGIN_ROOT)
    mirror_meta = _plugin_metadata(AGENTS_PLUGIN_ROOT)
    cache_meta = _plugin_metadata(active_cache_root) if active_cache_root else None
    current_meta = _plugin_metadata(PLUGIN_ROOT)
    current_root_text = str(PLUGIN_ROOT)
    current_kind = _plugin_root_kind(PLUGIN_ROOT)
    current_cache_version = _extract_cache_version(current_root_text)
    source_version = source_meta.get("version") if source_meta else None
    mirror_version = mirror_meta.get("version") if mirror_meta else None
    cache_version = cache_meta.get("version") if cache_meta else None
    current_version = current_meta.get("version") if current_meta else None
    cache_matches_source = bool(source_version and cache_version and source_version == cache_version == active_cache_version)
    source_wrapper_hash = _plugin_wrapper_hash(SOURCE_PLUGIN_ROOT)
    mirror_wrapper_hash = _plugin_wrapper_hash(AGENTS_PLUGIN_ROOT)
    current_wrapper_path = _plugin_wrapper_path(PLUGIN_ROOT)
    current_wrapper_hash = _plugin_wrapper_hash(PLUGIN_ROOT)
    source_alignment_status = _source_alignment_status(
        resolved_root=PLUGIN_ROOT,
        resolved_version=current_version,
        canonical_version=source_version,
        canonical_wrapper_hash=source_wrapper_hash,
        mirror_version=mirror_version,
        mirror_wrapper_hash=mirror_wrapper_hash,
        cache_version=cache_version,
    )
    stale_loaded_session_suspicion = False
    issues: list[str] = []
    if not source_meta:
        issues.append(f"canonical plugin root missing manifest: {SOURCE_PLUGIN_ROOT}")
    if source_alignment_status not in {"aligned", "aligned_via_mirror", "aligned_via_cache"}:
        stale_loaded_session_suspicion = True
        issues.append(f"source alignment degraded: {source_alignment_status}")
    if source_version and cache_version and source_version != cache_version:
        stale_loaded_session_suspicion = True
        issues.append(f"source/cache version mismatch: source={source_version} cache={cache_version}")
    if source_version and mirror_version and source_version != mirror_version:
        stale_loaded_session_suspicion = True
        issues.append(f"canonical/mirror version mismatch: canonical={source_version} mirror={mirror_version}")
    if source_wrapper_hash and mirror_wrapper_hash and source_wrapper_hash != mirror_wrapper_hash:
        stale_loaded_session_suspicion = True
        issues.append("canonical/mirror wrapper hash mismatch")
    if current_kind == "cache" and current_cache_version and active_cache_version and current_cache_version != active_cache_version:
        stale_loaded_session_suspicion = True
        issues.append(f"loaded cache version differs from active cache: loaded={current_cache_version} active={active_cache_version}")
    if current_version and active_cache_version and current_version != active_cache_version and current_kind == "cache":
        stale_loaded_session_suspicion = True
        issues.append(f"loaded plugin version differs from active cache directory: loaded={current_version} active={active_cache_version}")
    return {
        "currentRoot": current_root_text,
        "currentKind": current_kind,
        "currentVersion": current_version,
        "resolvedPluginRoot": current_root_text,
        "resolvedPluginVersion": current_version,
        "resolvedWrapperPath": str(current_wrapper_path) if current_wrapper_path else None,
        "resolvedWrapperHash": current_wrapper_hash,
        "expectedCanonicalRoot": str(SOURCE_PLUGIN_ROOT),
        "expectedCanonicalVersion": source_version,
        "expectedCanonicalWrapperPath": str(_plugin_wrapper_path(SOURCE_PLUGIN_ROOT)),
        "expectedCanonicalWrapperHash": source_wrapper_hash,
        "sourceAlignmentStatus": source_alignment_status,
        "sourceRoot": str(SOURCE_PLUGIN_ROOT),
        "sourceVersion": source_version,
        "mirrorRoot": str(AGENTS_PLUGIN_ROOT),
        "mirrorVersion": mirror_version,
        "mirrorWrapperPath": str(_plugin_wrapper_path(AGENTS_PLUGIN_ROOT)),
        "mirrorWrapperHash": mirror_wrapper_hash,
        "activeCacheRoot": str(active_cache_root) if active_cache_root else None,
        "activeCacheVersion": active_cache_version,
        "cacheVersion": cache_version,
        "cacheVersionMatchesSource": cache_matches_source,
        "staleLoadedSessionSuspicion": stale_loaded_session_suspicion,
        "issues": issues,
    }


def _mcp_log_summary(limit: int = 30) -> dict[str, Any]:
    if not MCP_LOG_PATH.exists():
        return {
            "status": "missing",
            "path": str(MCP_LOG_PATH),
            "eventCount": 0,
            "errorCount": 0,
            "warningCount": 0,
            "serverStartCount": 0,
            "startupStormSuspected": False,
            "latestEvent": None,
        }
    lines = MCP_LOG_PATH.read_text(encoding="utf-8").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    error_events = [
        event
        for event in events
        if str(event.get("event") or "").lower()
        in {"request_exception", "fatal_exception", "json_decode_error", "tool_call_error"}
    ]
    warning_events = [event for event in events if "warn" in str(event.get("level") or "").lower()]
    server_start_events = [event for event in events if str(event.get("event") or "").lower() == "server_start"]
    startup_storm_suspected = False
    startup_storm_window_seconds = None
    if len(server_start_events) >= 3:
        timestamps = [
            _parse_time(event.get("time"))
            for event in server_start_events
            if _parse_time(event.get("time")) is not None
        ]
        if len(timestamps) >= 3:
            timestamps.sort()
            startup_storm_window_seconds = int((timestamps[-1] - timestamps[0]).total_seconds())
            startup_storm_suspected = startup_storm_window_seconds <= 30
    return {
        "status": "ok",
        "path": str(MCP_LOG_PATH),
        "eventCount": len(events),
        "errorCount": len(error_events),
        "warningCount": len(warning_events),
        "serverStartCount": len(server_start_events),
        "startupStormSuspected": startup_storm_suspected,
        "startupStormWindowSeconds": startup_storm_window_seconds,
        "latestEvent": events[-1] if events else None,
        "recentEvents": events[-5:],
    }


def _codex_desktop_log_summary(limit_files: int = 6, tail_chars: int = 250000) -> dict[str, Any]:
    if not CODEX_DESKTOP_LOG_ROOT.exists():
        return {
            "status": "missing",
            "root": str(CODEX_DESKTOP_LOG_ROOT),
            "filesScanned": 0,
            "nullByteJsonWarningCount": 0,
            "hugeGitCommandCount": 0,
            "maxGitArgsCount": 0,
            "recentFindings": [],
        }
    try:
        candidates = sorted(
            [path for path in CODEX_DESKTOP_LOG_ROOT.rglob("*.log") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[: max(1, limit_files)]
    except OSError:
        candidates = []
    null_byte_warnings = 0
    huge_git_commands = 0
    max_git_args = 0
    findings: list[dict[str, Any]] = []
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if tail_chars > 0 and len(text) > tail_chars:
            text = text[-tail_chars:]
        for line in text.splitlines():
            lower = line.lower()
            if "unexpected token" in lower and ("\\u0000" in line or "\x00" in line):
                null_byte_warnings += 1
                if len(findings) < 8:
                    findings.append(
                        {
                            "type": "null_byte_json_warning",
                            "file": str(path),
                            "line": line[:300],
                        }
                    )
            if "git.command.complete" in line and "argscount=" in lower:
                match = re.search(r"argsCount=(\d+)", line)
                args_count = int(match.group(1)) if match else 0
                max_git_args = max(max_git_args, args_count)
                if args_count >= 500:
                    huge_git_commands += 1
                    if len(findings) < 8:
                        findings.append(
                            {
                                "type": "huge_git_command",
                                "file": str(path),
                                "argsCount": args_count,
                                "line": line[:300],
                            }
                        )
    return {
        "status": "ok",
        "root": str(CODEX_DESKTOP_LOG_ROOT),
        "filesScanned": len(candidates),
        "nullByteJsonWarningCount": null_byte_warnings,
        "hugeGitCommandCount": huge_git_commands,
        "maxGitArgsCount": max_git_args,
        "recentFindings": findings,
    }


def _read_tail_lines(path: Path, count: int = 8) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-max(1, count) :]


def _file_contains(path: Path, pattern: str) -> bool:
    try:
        return pattern.lower() in path.read_text(encoding="utf-8", errors="replace").lower()
    except OSError:
        return False


def _codex_host_scheduled_task(task_name: str, scan_live: bool = False) -> dict[str, Any]:
    if not scan_live:
        return {
            "status": "not_scanned",
            "taskName": task_name,
        }
    escaped_name = task_name.replace("'", "''")
    query = (
        f"$task = Get-ScheduledTask -TaskName '{escaped_name}' -ErrorAction SilentlyContinue; "
        "if ($null -eq $task) { [pscustomobject]@{ status='missing'; taskName='"
        + escaped_name
        + "' } | ConvertTo-Json -Compress } "
        "else { [pscustomobject]@{ "
        "status='ok'; "
        "taskName=$task.TaskName; "
        "taskPath=$task.TaskPath; "
        "state=[string]$task.State; "
        "execute=[string]$task.Actions[0].Execute; "
        "arguments=[string]$task.Actions[0].Arguments "
        "} | ConvertTo-Json -Compress }"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", query],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "error",
            "taskName": task_name,
            "error": str(exc),
        }
    if proc.returncode != 0:
        return {
            "status": "error",
            "taskName": task_name,
            "stderr": (proc.stderr or "").strip(),
        }
    try:
        parsed = json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return {
            "status": "error",
            "taskName": task_name,
            "stdout": proc.stdout.strip(),
        }
    return parsed if isinstance(parsed, dict) else {"status": "error", "taskName": task_name}


def _codex_host_process_counts(scan_live: bool = False) -> dict[str, Any]:
    if not scan_live:
        return {
            "status": "not_scanned",
            "watchdogCount": 0,
            "bootstrapCount": 0,
            "guardianCount": 0,
            "sample": [],
        }
    query = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { "
        "($_.Name -eq 'powershell.exe' -or $_.Name -eq 'pwsh.exe') -and "
        "$_.CommandLine -and "
        "($_.CommandLine -match 'codex-watchdog\\.ps1' -or $_.CommandLine -match 'codex-logon-bootstrap\\.ps1' -or $_.CommandLine -match 'codex-health-guardian\\.ps1') "
        "} | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Depth 3 -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", query],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "error",
            "watchdogCount": 0,
            "bootstrapCount": 0,
            "guardianCount": 0,
            "error": str(exc),
            "sample": [],
        }
    if proc.returncode != 0 or not proc.stdout.strip():
        return {
            "status": "ok",
            "watchdogCount": 0,
            "bootstrapCount": 0,
            "guardianCount": 0,
            "sample": [],
        }
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "watchdogCount": 0,
            "bootstrapCount": 0,
            "guardianCount": 0,
            "stdout": proc.stdout.strip(),
            "sample": [],
        }
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        parsed = []
    sample = [entry for entry in parsed[:5] if isinstance(entry, dict)]
    watchdog_count = 0
    bootstrap_count = 0
    guardian_count = 0
    for entry in sample if len(parsed) <= 5 else parsed:
        if not isinstance(entry, dict):
            continue
        command_line = str(entry.get("CommandLine") or entry.get("commandLine") or "")
        if "codex-watchdog.ps1" in command_line:
            watchdog_count += 1
        if "codex-logon-bootstrap.ps1" in command_line:
            bootstrap_count += 1
        if "codex-health-guardian.ps1" in command_line:
            guardian_count += 1
    return {
        "status": "ok",
        "watchdogCount": watchdog_count,
        "bootstrapCount": bootstrap_count,
        "guardianCount": guardian_count,
        "sample": sample,
    }


def _codex_host_health(scan_live: bool = False) -> dict[str, Any]:
    state = _read_json_object_if_exists(CODEX_WATCHDOG_STATE_PATH) or {}
    keepalive_until = state.get("keepalive_until_utc")
    keepalive_active = False
    if isinstance(keepalive_until, str):
        try:
            keepalive_active = datetime.fromisoformat(keepalive_until.replace("Z", "+00:00")) > datetime.now(timezone.utc)
        except ValueError:
            keepalive_active = False
    task = _codex_host_scheduled_task(CODEX_HEALTH_BOOTSTRAP_TASK_NAME, scan_live=scan_live)
    processes = _codex_host_process_counts(scan_live=scan_live)
    launch_log_exists = CODEX_LAUNCH_LOG_PATH.exists()
    launch_log_tail = _read_tail_lines(CODEX_LAUNCH_LOG_PATH, count=8) if launch_log_exists else []
    startup_exists = CODEX_STARTUP_VBS_PATH.exists()
    bootstrap_exists = CODEX_LOGON_BOOTSTRAP_PATH.exists()
    guardian_exists = CODEX_HEALTH_GUARDIAN_PATH.exists()
    startup_targets_guardian = startup_exists and _file_contains(CODEX_STARTUP_VBS_PATH, "codex-health-guardian.ps1")
    armed = bool(state.get("managed_launch")) and keepalive_active
    task_ready = task.get("status") == "ok" and str(task.get("state") or "").lower() != "disabled"
    watchdog_running = int(processes.get("watchdogCount") or 0) > 0
    guardian_running = int(processes.get("guardianCount") or 0) > 0
    recovery_loop_ready = guardian_exists and startup_targets_guardian and guardian_running
    status = "healthy"
    recommended_action = "continue"
    issues: list[str] = []
    if not startup_exists:
        status = "degraded"
        recommended_action = "repair startup bootstrap"
        issues.append("startup bootstrap VBS is missing")
    if not bootstrap_exists:
        status = "degraded"
        recommended_action = "repair startup bootstrap"
        issues.append("Codex logon bootstrap script is missing")
    if not guardian_exists:
        status = "degraded"
        recommended_action = "repair codex health guardian"
        issues.append("Codex health guardian script is missing")
    if startup_exists and not startup_targets_guardian:
        status = "degraded"
        recommended_action = "update startup bootstrap to launch guardian"
        issues.append("startup bootstrap is not configured to launch the Codex health guardian")
    if scan_live and not guardian_running:
        status = "degraded"
        recommended_action = "start codex health guardian"
        issues.append("Codex health guardian process is not running")
    if scan_live and task.get("status") not in {"not_scanned", "ok", "missing"} and not task_ready:
        status = "degraded"
        if recommended_action == "continue":
            recommended_action = "inspect codex health bootstrap task"
        issues.append("Codex health bootstrap scheduled task is unavailable")
    if scan_live and not watchdog_running:
        status = "degraded"
        recommended_action = "run codex logon bootstrap"
        issues.append("Codex watchdog process is not running")
    if state and not armed:
        status = "degraded"
        if recommended_action == "continue":
            recommended_action = "run codex logon bootstrap"
        issues.append("Codex watchdog state is present but not armed for crash recovery")
    if not state:
        status = "degraded"
        if recommended_action == "continue":
            recommended_action = "run codex logon bootstrap"
        issues.append("Codex watchdog state file is missing")
    return {
        "status": status,
        "recommendedAction": recommended_action,
        "recoveryLoopReady": recovery_loop_ready,
        "startupVbs": {"path": str(CODEX_STARTUP_VBS_PATH), "exists": startup_exists},
        "bootstrapScript": {"path": str(CODEX_LOGON_BOOTSTRAP_PATH), "exists": bootstrap_exists},
        "guardianScript": {
            "path": str(CODEX_HEALTH_GUARDIAN_PATH),
            "exists": guardian_exists,
            "startupTargetsGuardian": startup_targets_guardian,
            "running": guardian_running,
        },
        "watchdogState": {
            "path": str(CODEX_WATCHDOG_STATE_PATH),
            "exists": CODEX_WATCHDOG_STATE_PATH.exists(),
            "managedLaunch": state.get("managed_launch"),
            "keepaliveUntilUtc": keepalive_until,
            "keepaliveActive": keepalive_active,
            "lastBootstrapUtc": state.get("last_bootstrap_utc"),
            "maxRestarts": state.get("max_restarts"),
            "restartCount": state.get("restart_count"),
            "armed": armed,
        },
        "scheduledTask": task,
        "processes": processes,
        "launchLog": {
            "path": str(CODEX_LAUNCH_LOG_PATH),
            "exists": launch_log_exists,
            "tail": launch_log_tail,
        },
        "issues": issues,
    }


def _chat_process_registry_health(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or CHAT_PROCESS_REGISTRY_PATH
    result: dict[str, Any] = {
        "path": str(registry_path),
        "exists": registry_path.exists(),
        "status": "missing",
        "sizeBytes": 0,
        "leadingNullBytes": 0,
        "nullByteCount": 0,
        "jsonValid": True,
        "readThreadSafe": True,
        "repairSuggested": False,
        "recordCount": 0,
        "corruptionKind": None,
    }
    if not registry_path.exists():
        return result
    try:
        data = registry_path.read_bytes()
    except OSError as exc:
        result.update(
            {
                "status": "read_error",
                "jsonValid": False,
                "readThreadSafe": False,
                "repairSuggested": False,
                "error": str(exc),
            }
        )
        return result
    result["sizeBytes"] = len(data)
    result["nullByteCount"] = data.count(b"\x00")
    result["leadingNullBytes"] = len(data) - len(data.lstrip(b"\x00")) if data else 0
    if not data:
        result.update(
            {
                "status": "empty",
                "jsonValid": False,
                "readThreadSafe": False,
                "repairSuggested": True,
                "corruptionKind": "empty_file",
            }
        )
        return result
    if result["leadingNullBytes"] == len(data):
        result.update(
            {
                "status": "corrupt",
                "jsonValid": False,
                "readThreadSafe": False,
                "repairSuggested": True,
                "corruptionKind": "all_null_bytes",
            }
        )
        return result
    if result["leadingNullBytes"] > 0:
        result.update(
            {
                "status": "corrupt",
                "jsonValid": False,
                "readThreadSafe": False,
                "repairSuggested": True,
                "corruptionKind": "leading_null_bytes",
            }
        )
        return result
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        result.update(
            {
                "status": "corrupt",
                "jsonValid": False,
                "readThreadSafe": False,
                "repairSuggested": True,
                "corruptionKind": "invalid_json",
                "error": str(exc),
            }
        )
        return result
    if isinstance(parsed, list):
        result.update(
            {
                "status": "ok",
                "recordCount": len(parsed),
            }
        )
        return result
    result.update(
        {
            "status": "shape_mismatch",
            "jsonValid": True,
            "readThreadSafe": True,
            "repairSuggested": False,
            "topLevelType": type(parsed).__name__,
        }
    )
    return result


def _read_json_object_if_exists(path: Path) -> dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _read_thread_guard_failure() -> dict[str, Any] | None:
    registry_health = _chat_process_registry_health()
    if registry_health.get("readThreadSafe", True):
        orphan_diagnostics = _project_manager_mcp_diagnostics(scan_live=True)
        if _effective_thread_read_safe(registry_health, orphan_diagnostics):
            return None
        return _failure(
            "Codex read_thread is unsafe while duplicate or cache-bound project-manager MCP wrapper groups are live",
            chatProcessRegistry=registry_health,
            orphanMcpDiagnostics=orphan_diagnostics,
            recommendedAction=_recommended_operator_action(
                {"status": "ok"},
                {
                    "staleLoadedSessionSuspicion": False,
                    "cacheVersionMatchesSource": True,
                },
                {"errorCount": 0},
                orphan_diagnostics,
                registry_health,
            ),
        )
    return _failure(
        "Codex read_thread is unsafe until the chat process registry is repaired",
        chatProcessRegistry=registry_health,
        recommendedAction="run codex self repair",
    )


def _live_models_by_slug(path: Path | None = None) -> dict[str, dict[str, Any]]:
    catalog_path = path or LIVE_MODELS_PATH
    parsed = _read_json_object_if_exists(catalog_path)
    models = parsed.get("models") if isinstance(parsed, dict) else None
    if not isinstance(models, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for raw_model in models:
        if not isinstance(raw_model, dict):
            continue
        slug = str(raw_model.get("slug") or raw_model.get("id") or "").strip()
        if slug:
            result[slug] = dict(raw_model)
    return result


def _catalog_entry_runtime_rules(entry: Mapping[str, Any]) -> list[str]:
    slug = str(entry.get("slug") or "")
    if slug == "deepseek-v4-flash":
        return [
            "immediate-tool-use: when tools are available and the task requires external action, use the tool immediately instead of narrating intentions.",
            "flash-bounded-loop: keep loops small and deterministic; prefer one concrete read or edit step at a time over broad speculative exploration.",
            "work-to-completion: if the user asked you to implement, fix, test, or verify something and tools are available, keep working until the requested slice is complete or a real blocker is proven.",
            "post-read-action: after inspecting files, logs, code, or test output, take the next concrete tool step if work remains; do not stop at diagnosis alone.",
            "strict-json-tool-args: every function tool call must emit valid JSON arguments that match the callable schema.",
            "no-simulated-tool-call: never replace a required tool call with an explanation, JSON example, or simulated tool usage.",
            "no-invented-edit-tools: if apply_patch is not callable, do not invent it.",
            "no-shell-thinking: never place reasoning, markdown, or comment-prefixed notes inside exec_command payloads.",
            "stay-in-workspace: stay inside the active workspace and prefer relative paths unless tool output proves an absolute path is required.",
            "verify-from-source: when asked for exact values or file-derived data, read the file or tool output back before replying.",
            "exact-output-discipline: when the user or manager requests exact output, emit exactly the requested block and nothing else.",
            "compaction-is-authoritative: treat compacted context as authoritative state and continue from it directly.",
            "finish-the-loop: after each tool result, either take the next concrete step or conclude; do not spend a turn restating the plan.",
        ]
    if slug == "deepseek-v4-pro":
        return [
            "immediate-tool-use: when tools are available and the task requires external action, use the tool immediately instead of narrating intentions.",
            "work-to-completion: if the user asked you to implement, fix, test, or verify something and tools are available, keep working until the requested slice is complete or a real blocker is proven.",
            "post-read-action: after inspecting files, logs, code, or test output, take the next concrete tool step if work remains; do not stop at diagnosis alone.",
            "strict-json-tool-args: every function tool call must emit valid JSON arguments that match the callable schema.",
            "no-simulated-tool-call: never replace a required tool call with an explanation, JSON example, or simulated tool usage.",
            "no-invented-edit-tools: if apply_patch is not callable, do not invent it.",
            "no-shell-thinking: never place reasoning, markdown, or comment-prefixed notes inside exec_command payloads.",
            "stay-in-workspace: stay inside the active workspace and prefer relative paths unless tool output proves an absolute path is required.",
            "verify-from-source: when asked for exact values or file-derived data, read the file or tool output back before replying.",
            "exact-output-discipline: when the user or manager requests exact output, emit exactly the requested block and nothing else.",
            "compaction-is-authoritative: treat compacted context as authoritative state and continue from it directly.",
            "finish-the-loop: after each tool result, either take the next concrete step or conclude; do not spend a turn restating the plan.",
        ]
    if slug == "glm-5.2":
        return [
            "long-context-first: use broad context carefully, then turn reconnaissance into concrete next actions quickly.",
            "recon-then-act: after a repo scan or synthesis pass, convert the findings into the next concrete tool step when the requested work is still active.",
            "strict-json-tool-args: every function tool call must emit valid JSON arguments that match the callable schema.",
            "stay-in-workspace: stay inside the active workspace and prefer relative paths.",
            "verify-from-source: when asked for exact values or file-derived data, read the file or tool output back before replying.",
            "exact-output-discipline: obey exact requested output blocks without extra prose.",
            "no-invented-tools: if a tool is not callable in this turn, do not mention it or try to use it.",
        ]
    if slug == "kimi-k2.7-code":
        return [
            "fast-inspect-patch-verify: prefer compact inspect-patch-verify loops.",
            "work-to-completion: if the user asked for implementation or a fix, keep iterating through inspect-patch-verify until the bounded slice is actually done or a blocker is proven.",
            "strict-json-tool-args: every function tool call must emit valid JSON arguments that match the callable schema.",
            "no-commentary-turns: avoid commentary-only turns between tool results.",
            "no-shell-thinking: never place reasoning, markdown, or comment-prefixed notes inside exec_command payloads.",
            "verify-from-source: when asked for exact values or file-derived data, read the file or tool output back before replying.",
            "no-invented-patch-tools: if apply_patch is not callable, use the available edit surface instead.",
        ]
    if slug == "mimo-v2.5":
        return [
            "bounded-cheap-slice: complete one cheap useful slice and hand off rather than broadening scope.",
            "one-complete-slice: prefer one finished bounded action with verification over a partial diagnosis plus suggested next steps.",
            "strict-json-tool-args: every function tool call must emit valid JSON arguments that match the callable schema.",
            "stay-tight: stay tightly bounded and avoid broad scans when a narrow check can answer the question.",
            "verify-from-source: when asked for exact values or file-derived data, read the file or tool output back before replying.",
            "exact-output-discipline: obey exact requested output blocks without extra prose.",
        ]
    if slug == "gpt-5.3-codex-spark":
        return [
            "micro-scope-only: stay within 1-3 files and avoid architecture-sensitive changes.",
            "fast-native-iteration: prefer tiny high-confidence edits and quick validation.",
        ]
    return []


def _catalog_entry_model_guidance(entry: Mapping[str, Any]) -> str:
    rules = _catalog_entry_runtime_rules(entry)
    if not rules:
        return ""
    slug = str(entry.get("slug") or "")
    if slug.startswith("deepseek-v4-"):
        return "\n".join(f"DeepSeek Codex worker rule: {rule}" for rule in rules)
    if slug == "glm-5.2":
        return "\n".join(f"GLM Codex worker rule: {rule}" for rule in rules)
    if slug == "kimi-k2.7-code":
        return "\n".join(f"Kimi Codex worker rule: {rule}" for rule in rules)
    if slug == "mimo-v2.5":
        return "\n".join(f"MiMo Codex worker rule: {rule}" for rule in rules)
    if slug == "gpt-5.3-codex-spark":
        return "\n".join(f"Spark Codex worker rule: {rule}" for rule in rules)
    return "Model guidance:\n- " + "\n- ".join(rules)


def _canonical_model_catalog(*, include_disabled: bool = True) -> list[dict[str, Any]]:
    live_models = _live_models_by_slug()
    catalog: list[dict[str, Any]] = []
    for slug, base in MODEL_CATALOG_BASE.items():
        if not include_disabled and not bool(base.get("enabled")):
            continue
        entry = dict(base)
        live = live_models.get(slug) or {}
        entry["slug"] = slug
        entry["displayName"] = str(live.get("display_name") or entry.get("displayName") or slug)
        entry["contextWindow"] = int(live.get("context_window") or entry.get("contextWindow") or 0)
        entry["maxContextWindow"] = int(live.get("max_context_window") or entry.get("maxContextWindow") or entry.get("contextWindow") or 0)
        entry["supportedReasoningLevels"] = live.get("supported_reasoning_levels") or entry.get("supportedReasoningLevels") or []
        entry["defaultThinking"] = str(live.get("default_reasoning_level") or entry.get("defaultThinking") or "medium")
        entry["supportsParallelToolCalls"] = bool(live.get("supports_parallel_tool_calls", entry.get("supportsParallelToolCalls", True)))
        entry["supportsSearchTool"] = bool(live.get("supports_search_tool", entry.get("supportsSearchTool", entry.get("supportsTools", True))))
        entry["supportsVerbosity"] = bool(live.get("support_verbosity", entry.get("supportsVerbosity", False)))
        entry["defaultVerbosity"] = str(live.get("default_verbosity") or entry.get("defaultVerbosity") or "low")
        entry["supportsReasoningSummaries"] = bool(live.get("supports_reasoning_summaries", entry.get("supportsReasoningSummaries", False)))
        entry["reasoningSummaryFormat"] = live.get("reasoning_summary_format") or entry.get("reasoningSummaryFormat")
        entry["effectiveContextWindowPercent"] = int(live.get("effective_context_window_percent") or entry.get("effectiveContextWindowPercent") or 100)
        entry["autoCompactTokenLimit"] = live.get("auto_compact_token_limit", entry.get("autoCompactTokenLimit"))
        input_modalities = live.get("input_modalities")
        if isinstance(input_modalities, list):
            entry["supportsImages"] = "image" in [str(item) for item in input_modalities]
            entry["inputModalities"] = [str(item) for item in input_modalities]
        else:
            entry["inputModalities"] = ["text", "image"] if entry.get("supportsImages") else ["text"]
        present = bool(live)
        entry["localAvailability"] = {
            "presentInLiveCatalog": present,
            "pickerVisible": present and str(live.get("visibility") or "list") != "hidden",
            "liveCatalogPath": str(LIVE_MODELS_PATH),
        }
        entry["runtimeRules"] = _catalog_entry_runtime_rules(entry)
        catalog.append(entry)
    return catalog


def _canonical_catalog_by_slug(*, include_disabled: bool = True) -> dict[str, dict[str, Any]]:
    return {entry["slug"]: entry for entry in _canonical_model_catalog(include_disabled=include_disabled)}


def _find_catalog_entry(model: Any, *, include_disabled: bool = True) -> dict[str, Any] | None:
    normalized = str(model or "").strip()
    catalog = _canonical_catalog_by_slug(include_disabled=include_disabled)
    if normalized in catalog:
        return catalog[normalized]
    lowered = normalized.lower()
    if lowered in catalog:
        return catalog[lowered]
    folded = re.sub(r"[^a-z0-9]+", "", lowered)
    for entry in catalog.values():
        aliases = [str(alias).strip().lower() for alias in entry.get("aliases", []) if str(alias).strip()]
        aliases.append(str(entry["slug"]).lower())
        aliases.append(re.sub(r"[^a-z0-9]+", "", str(entry["slug"]).lower()))
        aliases.append(re.sub(r"[^a-z0-9]+", "", str(entry.get("displayName") or "").lower()))
        if lowered in aliases:
            return entry
        if folded and any(folded == re.sub(r"[^a-z0-9]+", "", alias) for alias in aliases):
            return entry
    return None


def _provider_usage_summary() -> dict[str, Any]:
    pool_state = _read_json_object_if_exists(OPENCODE_POOL_STATE_PATH) or {}
    accounts = pool_state.get("accounts") if isinstance(pool_state.get("accounts"), dict) else {}
    total_spend = 0.0
    for account in accounts.values():
        if isinstance(account, dict):
            total_spend += float(account.get("monthly_spend_usd") or 0.0)
    monthly_credit = float(pool_state.get("monthly_credit_usd_per_account") or 60.0)
    account_count = len(accounts)
    estimated_pool_total = round(monthly_credit * account_count, 2)
    remaining_estimate = round(max(0.0, estimated_pool_total - total_spend), 2)
    return {
        "usageVisibilityReady": bool(pool_state),
        "poolStatePath": str(OPENCODE_POOL_STATE_PATH),
        "accountCount": account_count,
        "trackedSpendUsd": round(total_spend, 8),
        "estimatedPoolTotalUsd": estimated_pool_total,
        "remainingEstimateUsd": remaining_estimate,
        "providerModels": sorted(
            entry["slug"] for entry in _canonical_model_catalog(include_disabled=True) if entry.get("provider") == "opencode-go"
        ),
    }


def _stable_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str | None:
    try:
        if not path.exists():
            return None
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _export_test_mode(live_models_path: Path | None = None) -> bool:
    path_text = str(live_models_path or LIVE_MODELS_PATH).lower()
    return bool(os.environ.get("PYTEST_CURRENT_TEST") or "pytest-" in path_text or "pytest-of-" in path_text)


def _export_metadata(export_mode: str = "active_root") -> dict[str, Any]:
    return {
        "generatedAt": _now_iso8601(),
        "pluginVersion": PLUGIN_VERSION,
        "generatedFromRoot": str(PLUGIN_ROOT),
        "liveModelsPath": str(LIVE_MODELS_PATH),
        "sourcePluginRoot": str(SOURCE_PLUGIN_ROOT),
        "cachePluginRoot": str(CACHE_PLUGIN_BASE),
        "exportMode": export_mode,
        "testMode": _export_test_mode(),
    }


def _with_payload_hash(payload: dict[str, Any], hash_key: str) -> dict[str, Any]:
    metadata = dict(payload.get("metadata") or {})
    payload = dict(payload)
    payload["metadata"] = metadata
    metadata["sha256"] = _stable_sha256({key: value for key, value in payload.items() if key != "metadata"})
    metadata[hash_key] = metadata["sha256"]
    return payload


def _proxy_model_list_export(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    models: list[dict[str, Any]] = []
    for entry in catalog:
        if not entry.get("enabled"):
            continue
        models.append(
            {
                "slug": entry["slug"],
                "display_name": entry["displayName"],
                "description": entry.get("description"),
                "provider": entry.get("provider"),
                "provider_label": entry.get("providerLabel"),
                "provider_hint": (
                    "Uses OpenCode Go credits"
                    if entry.get("provider") == "opencode-go"
                    else "Uses included Codex GPT quota"
                ),
                "provider_credit_source": entry.get("providerCreditSource"),
                "context_window": entry.get("contextWindow"),
                "max_context_window": entry.get("maxContextWindow"),
                "auto_compact_token_limit": entry.get("autoCompactTokenLimit"),
                "default_reasoning_level": entry.get("defaultThinking"),
                "supported_reasoning_levels": entry.get("supportedReasoningLevels"),
                "supports_parallel_tool_calls": entry.get("supportsParallelToolCalls"),
                "input_modalities": entry.get("inputModalities") or (["text", "image"] if entry.get("supportsImages") else ["text"]),
                "supports_search_tool": entry.get("supportsSearchTool"),
                "support_verbosity": entry.get("supportsVerbosity"),
                "default_verbosity": entry.get("defaultVerbosity"),
                "supports_reasoning_summaries": entry.get("supportsReasoningSummaries"),
                "reasoning_summary_format": entry.get("reasoningSummaryFormat"),
                "effective_context_window_percent": entry.get("effectiveContextWindowPercent"),
                "role_hint": entry.get("roleHint"),
                "cost_class": entry.get("costClass"),
                "compatibility_class": entry.get("compatibilityClass"),
                "policy_role": entry.get("policyRole"),
                "usage_tier": entry.get("usageTier"),
                "recommended_for": entry.get("recommendedTasks") or [],
                "avoid_for": entry.get("avoidTasks") or [],
                "recommended_for_summary": entry.get("recommendedForSummary"),
                "avoid_for_summary": entry.get("avoidForSummary"),
                "known_failure_modes": entry.get("knownFailureModes") or [],
                "tool_loop_reliability": entry.get("toolLoopReliability"),
                "continuation_reliability": entry.get("continuationReliability"),
                "compatibility_notes": entry.get("compatibilityNotes"),
                "visibility": "list" if entry.get("localAvailability", {}).get("pickerVisible", True) else "hidden",
                "transport_route": entry.get("transportRoute"),
            }
        )
    return _with_payload_hash({"metadata": _export_metadata(), "models": models}, "modelListSha256")


def _proxy_runtime_export(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    models: dict[str, Any] = {}
    for entry in catalog:
        models[entry["slug"]] = {
            "displayName": entry["displayName"],
            "provider": entry.get("provider"),
            "providerLabel": entry.get("providerLabel"),
            "transportRoute": entry.get("transportRoute"),
            "aliases": entry.get("aliases") or [],
            "runtimeRules": entry.get("runtimeRules") or [],
            "enabled": bool(entry.get("enabled")),
            "disabledReason": entry.get("disabledReason"),
            "toolLoopReliability": entry.get("toolLoopReliability"),
            "continuationReliability": entry.get("continuationReliability"),
            "roleHint": entry.get("roleHint"),
            "costClass": entry.get("costClass"),
            "compatibilityClass": entry.get("compatibilityClass"),
            "policyRole": entry.get("policyRole"),
            "usageTier": entry.get("usageTier"),
            "recommendedTasks": entry.get("recommendedTasks") or [],
            "avoidTasks": entry.get("avoidTasks") or [],
            "recommendedForSummary": entry.get("recommendedForSummary"),
            "avoidForSummary": entry.get("avoidForSummary"),
            "knownFailureModes": entry.get("knownFailureModes") or [],
            "compatibilityNotes": entry.get("compatibilityNotes"),
        }
    return _with_payload_hash({"metadata": _export_metadata(), "models": models}, "runtimeSha256")


def _write_model_exports(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    catalog_payload = _with_payload_hash({"metadata": _export_metadata(), "models": catalog}, "catalogSha256")
    proxy_model_list = _proxy_model_list_export(catalog)
    proxy_runtime = _proxy_runtime_export(catalog)
    MODEL_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_CATALOG_EXPORT_PATH.write_text(json.dumps(catalog_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    PROXY_MODEL_LIST_EXPORT_PATH.write_text(json.dumps(proxy_model_list, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    PROXY_RUNTIME_EXPORT_PATH.write_text(json.dumps(proxy_runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "metadata": catalog_payload["metadata"],
        "canonicalCatalog": {"path": str(MODEL_CATALOG_EXPORT_PATH), "exists": MODEL_CATALOG_EXPORT_PATH.exists()},
        "proxyModelList": {"path": str(PROXY_MODEL_LIST_EXPORT_PATH), "exists": PROXY_MODEL_LIST_EXPORT_PATH.exists()},
        "proxyRuntimeInstructions": {"path": str(PROXY_RUNTIME_EXPORT_PATH), "exists": PROXY_RUNTIME_EXPORT_PATH.exists()},
    }


def _load_model_evidence(path_value: Any = None) -> dict[str, Any]:
    path = Path(str(path_value or MODEL_RELIABILITY_EVIDENCE_PATH)).expanduser()
    parsed = _read_json_object_if_exists(path) or {}
    models = parsed.get("models") if isinstance(parsed.get("models"), dict) else {}
    return {"path": path, "models": models}


def _write_model_evidence(path: Path, models: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"updatedAt": _now_iso8601(), "models": models}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _merge_model_pressure_observations(models: dict[str, Any], observations: list[dict[str, Any]]) -> dict[str, Any]:
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        entry = _find_catalog_entry(observation.get("model"), include_disabled=True)
        if not entry:
            continue
        slug = entry["slug"]
        model_row = dict(models.get(slug) or {})
        event_type = str(observation.get("eventType") or "").strip().lower()
        status = str(observation.get("status") or "").strip().lower()
        model_row.setdefault("followUpFailures", 0)
        model_row.setdefault("freshThreadSuccesses", 0)
        model_row.setdefault("followUpSuccesses", 0)
        if event_type == "follow_up_tool_loop":
            if status == "failed":
                model_row["followUpFailures"] = int(model_row.get("followUpFailures") or 0) + 1
            elif status == "ok":
                model_row["followUpSuccesses"] = int(model_row.get("followUpSuccesses") or 0) + 1
                model_row["lastSuccessfulFollowUpToolLoopCanary"] = observation.get("recordedAt") or _now_iso8601()
        elif event_type == "fresh_thread_canary" and status == "ok":
            model_row["freshThreadSuccesses"] = int(model_row.get("freshThreadSuccesses") or 0) + 1
            model_row["lastSuccessfulFreshThreadCanary"] = observation.get("recordedAt") or _now_iso8601()
        elif event_type == "parse_failure":
            model_row["lastParseFailure"] = observation.get("recordedAt") or _now_iso8601()
        elif event_type == "raw_text_fallback":
            model_row["lastRawTextFallback"] = observation.get("recordedAt") or _now_iso8601()
        elif event_type == "comment_sanitizer_intervention":
            model_row["lastCommentSanitizerIntervention"] = observation.get("recordedAt") or _now_iso8601()
        elif event_type == "operator_recovery":
            model_row["lastOperatorRecoveryNeeded"] = observation.get("recordedAt") or _now_iso8601()
        models[slug] = model_row
    return models


def _proxy_log_model_events(proxy_log_path: Path | None = None) -> dict[str, dict[str, int]]:
    path = proxy_log_path or PROXY_LOG_PATH
    if not path.exists():
        return {}
    counts: dict[str, dict[str, int]] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()[-500:]:
        lowered = line.lower()
        matched_model = None
        for slug in MODEL_CATALOG_BASE:
            if slug in lowered:
                matched_model = slug
                break
        if not matched_model:
            continue
        row = counts.setdefault(matched_model, {"parseFailures": 0, "rawTextFallbacks": 0, "commentSanitizerInterventions": 0})
        if "parse failure model=" in lowered or "response parse failed" in lowered:
            row["parseFailures"] += 1
        if "raw-text fallback engaged" in lowered:
            row["rawTextFallbacks"] += 1
        if "sanitized comment-only reasoning lines" in lowered:
            row["commentSanitizerInterventions"] += 1
    return counts


def _model_pressure_summary(args: dict[str, Any]) -> dict[str, Any]:
    evidence = _load_model_evidence(args.get("evidenceFile"))
    models = dict(evidence["models"])
    observations = args.get("observations") if isinstance(args.get("observations"), list) else []
    models = _merge_model_pressure_observations(models, observations)
    proxy_counts = _proxy_log_model_events(Path(str(args.get("proxyLogFile"))).expanduser() if args.get("proxyLogFile") else None)
    for slug, row in proxy_counts.items():
        merged = dict(models.get(slug) or {})
        merged["parseFailures"] = max(int(merged.get("parseFailures") or 0), int(row.get("parseFailures") or 0))
        merged["rawTextFallbacks"] = max(int(merged.get("rawTextFallbacks") or 0), int(row.get("rawTextFallbacks") or 0))
        merged["commentSanitizerInterventions"] = max(
            int(merged.get("commentSanitizerInterventions") or 0),
            int(row.get("commentSanitizerInterventions") or 0),
        )
        models[slug] = merged
    if args.get("writeEvidence"):
        _write_model_evidence(evidence["path"], models)
    summarized: dict[str, Any] = {}
    for slug, row in models.items():
        follow_up_failures = int(row.get("followUpFailures") or 0)
        parse_failures = int(row.get("parseFailures") or 0)
        raw_text_fallbacks = int(row.get("rawTextFallbacks") or 0)
        reliability = "healthy"
        if follow_up_failures >= 2 or parse_failures > 0 or raw_text_fallbacks > 0:
            reliability = "degraded"
        if follow_up_failures >= 3:
            reliability = "single_turn_only"
        summarized[slug] = {
            "followUpFailures": follow_up_failures,
            "parseFailures": parse_failures,
            "rawTextFallbacks": raw_text_fallbacks,
            "commentSanitizerInterventions": int(row.get("commentSanitizerInterventions") or 0),
            "freshThreadSuccesses": int(row.get("freshThreadSuccesses") or 0),
            "followUpSuccesses": int(row.get("followUpSuccesses") or 0),
            "lastSuccessfulFreshThreadCanary": row.get("lastSuccessfulFreshThreadCanary"),
            "lastSuccessfulFollowUpToolLoopCanary": row.get("lastSuccessfulFollowUpToolLoopCanary"),
            "lastParseFailure": row.get("lastParseFailure"),
            "lastRawTextFallback": row.get("lastRawTextFallback"),
            "reliabilityStatus": reliability,
        }
    return {"path": str(evidence["path"]), "models": summarized}


def _catalog_health(catalog: list[dict[str, Any]]) -> dict[str, Any]:
    live_slugs = set(_live_models_by_slug().keys())
    expected_enabled = {entry["slug"] for entry in catalog if entry.get("enabled")}
    export_model_list = _read_json_object_if_exists(PROXY_MODEL_LIST_EXPORT_PATH) or {}
    export_runtime = _read_json_object_if_exists(PROXY_RUNTIME_EXPORT_PATH) or {}
    export_slugs = {
        str(model.get("slug") or "").strip()
        for model in (export_model_list.get("models") or [])
        if isinstance(model, dict) and str(model.get("slug") or "").strip()
    }
    runtime_models = export_runtime.get("models") if isinstance(export_runtime.get("models"), dict) else {}
    route_mismatch_count = 0
    for entry in catalog:
        exported = runtime_models.get(entry["slug"]) if isinstance(runtime_models, dict) else None
        if isinstance(exported, dict) and str(exported.get("transportRoute") or "") != str(entry.get("transportRoute") or ""):
            route_mismatch_count += 1
    missing_live = sorted(expected_enabled - live_slugs)
    extra_live = sorted(live_slugs - expected_enabled)
    missing_export = sorted(expected_enabled - export_slugs)
    return {
        "expectedModelCount": len(catalog),
        "enabledModelCount": len(expected_enabled),
        "liveCatalogPath": str(LIVE_MODELS_PATH),
        "proxyModelListExportPath": str(PROXY_MODEL_LIST_EXPORT_PATH),
        "proxyRuntimeExportPath": str(PROXY_RUNTIME_EXPORT_PATH),
        "missingFromLiveCatalog": missing_live,
        "extraLiveModels": extra_live,
        "missingFromProxyExport": missing_export,
        "routeMismatchCount": route_mismatch_count,
        "driftDetected": bool(missing_live or extra_live or missing_export or route_mismatch_count),
    }


def _resolve_runtime_command(command: str, root: Path | None = None) -> str:
    candidate = Path(command)
    if candidate.is_absolute():
        return str(candidate)
    base_root = root or PLUGIN_ROOT
    return str((base_root / candidate).resolve())


def _run_wrapper_smoke(timeout_seconds: int = 10, plugin_root: Path | None = None) -> dict[str, Any]:
    root = plugin_root or PLUGIN_ROOT
    config_path = root / ".mcp.json"
    if not config_path.exists():
        return {"status": "failed", "reason": ".mcp.json missing"}
    try:
        parsed = json.loads(config_path.read_text(encoding="utf-8"))
        server = parsed.get("mcpServers", {}).get("project-manager", {})
        command = server.get("command")
        args = server.get("args") or []
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "failed", "reason": f"unable to read .mcp.json: {exc}"}
    if not isinstance(command, str) or not command.strip():
        return {"status": "failed", "reason": "MCP command missing"}
    payload = "\n".join(
        json.dumps(message)
        for message in (
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
    ) + "\n"
    try:
        proc = subprocess.run(
            [_resolve_runtime_command(command, root=root), *[str(arg) for arg in args]],
            input=payload,
            text=True,
            capture_output=True,
            cwd=root,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "reason": str(exc)}
    if proc.returncode != 0:
        return {"status": "failed", "reason": proc.stderr.strip() or f"wrapper exited {proc.returncode}"}
    responses = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    if len(responses) < 2:
        return {"status": "failed", "reason": "wrapper smoke returned incomplete JSON-RPC output"}
    tools = responses[-1].get("result", {}).get("tools")
    if not isinstance(tools, list):
        return {"status": "failed", "reason": "wrapper smoke returned no tool list"}
    return {
        "status": "ok",
        "toolCount": len(tools),
        "serverName": responses[0].get("result", {}).get("serverInfo", {}).get("name"),
        "pluginRoot": str(root),
        "wrapperPath": _resolve_runtime_command(command, root=root),
        "wrapperHash": _file_sha256(Path(_resolve_runtime_command(command, root=root))),
    }


def _recommended_operator_action(
    wrapper_smoke: dict[str, Any],
    install_state: dict[str, Any],
    log_summary: dict[str, Any],
    orphan_diagnostics: dict[str, Any],
    chat_process_registry_health: dict[str, Any] | None = None,
) -> str:
    if chat_process_registry_health and not chat_process_registry_health.get("readThreadSafe", True):
        return "run codex self repair"
    if log_summary.get("startupStormSuspected"):
        return "run codex self repair"
    if wrapper_smoke.get("status") != "ok" or install_state.get("staleLoadedSessionSuspicion") or not install_state.get("cacheVersionMatchesSource", True):
        return "reload session"
    if orphan_diagnostics.get("sameVersionWrapperBuildup"):
        return "run codex self repair"
    if orphan_diagnostics.get("sameVersionProcessLimitExceeded"):
        return "run codex self repair"
    if int(orphan_diagnostics.get("cacheBoundCount") or 0) > 0:
        return "reload session"
    if int(log_summary.get("errorCount") or 0) > 0:
        return "new thread recommended"
    if int(orphan_diagnostics.get("orphanCount") or 0) > 0:
        return "continue"
    return "continue"


def _normalize_process_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    pid = entry.get("pid", entry.get("ProcessId", entry.get("processId")))
    parent_pid = entry.get("parentProcessId", entry.get("ParentProcessId", entry.get("parent_pid")))
    name = entry.get("name", entry.get("Name", ""))
    command_line = entry.get("commandLine", entry.get("CommandLine", ""))
    started_at = entry.get("startedAt", entry.get("CreationDate", entry.get("createdAt", "")))
    return {
        "pid": int(pid) if isinstance(pid, (int, float)) or str(pid).isdigit() else None,
        "parentProcessId": int(parent_pid) if isinstance(parent_pid, (int, float)) or str(parent_pid).isdigit() else None,
        "name": str(name or "").strip(),
        "commandLine": str(command_line or "").strip(),
        "startedAt": _normalize_process_started_at(started_at),
    }


def _normalize_process_started_at(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if re.fullmatch(r"\d{14}\.\d{6}[+-]\d{3}", text):
            # WMI datetime like 20260620123456.123456-180
            parsed = datetime.strptime(text[:21], "%Y%m%d%H%M%S.%f")
            return parsed.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def _parse_started_at(value: Any) -> datetime | None:
    normalized = _normalize_process_started_at(value)
    if not normalized:
        return None
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def _effective_thread_read_safe(
    chat_process_registry_health: dict[str, Any] | None,
    orphan_diagnostics: dict[str, Any] | None,
) -> bool:
    registry_safe = True if chat_process_registry_health is None else bool(chat_process_registry_health.get("readThreadSafe", True))
    if not registry_safe:
        return False
    diagnostics = orphan_diagnostics or {}
    return not bool(
        diagnostics.get("sameVersionWrapperBuildup")
        or diagnostics.get("sameVersionProcessLimitExceeded")
        or int(diagnostics.get("cacheBoundCount") or 0) > 0
    )


def _load_project_manager_process_snapshot(scan_live: bool = False) -> list[dict[str, Any]]:
    snapshot_path = os.environ.get(PROCESS_SNAPSHOT_ENV)
    if snapshot_path:
        parsed = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
        if not isinstance(parsed, list):
            return []
        return [_normalize_process_entry(entry) for entry in parsed if isinstance(entry, Mapping)]
    if not scan_live:
        return []
    query = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'project_manager_mcp_server.py|project-manager-mcp.exe' } | "
        "Select-Object ProcessId,ParentProcessId,CreationDate,Name,CommandLine | ConvertTo-Json -Depth 3 -Compress"
    )
    proc = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", query],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return []
    parsed = json.loads(proc.stdout)
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []
    return [_normalize_process_entry(entry) for entry in parsed if isinstance(entry, Mapping)]


def _extract_script_path(command_line: str) -> str | None:
    match = re.search(r'([A-Za-z]:\\[^"\r\n]*project_manager_mcp_server\.py)', command_line, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_wrapper_path(command_line: str) -> str | None:
    match = re.search(r'([A-Za-z]:\\[^"\r\n]*project-manager-mcp\.exe)', command_line, re.IGNORECASE)
    return match.group(1) if match else None


def _extract_cache_version(path_value: str | None) -> str | None:
    if not path_value:
        return None
    parts = [part.lower() for part in PureWindowsPath(path_value).parts]
    if not {"cache", "personal", "project-manager"}.issubset(set(parts)):
        return None
    try:
        index = parts.index("project-manager")
    except ValueError:
        return None
    original_parts = list(PureWindowsPath(path_value).parts)
    if index + 1 >= len(original_parts):
        return None
    return original_parts[index + 1]


def _classify_project_manager_process(entry: Mapping[str, Any], active_cache_version: str | None) -> dict[str, Any] | None:
    normalized = _normalize_process_entry(entry)
    command_line = normalized["commandLine"]
    if not command_line:
        return None
    script_path = _extract_script_path(command_line)
    wrapper_path = _extract_wrapper_path(command_line)
    if not script_path and not wrapper_path:
        return None
    cache_version = _extract_cache_version(script_path or wrapper_path)
    runtime = "wrapper" if wrapper_path else "script"
    orphan_reason = None
    safe_to_cleanup = False
    cache_bound_runtime = False
    lower_name = normalized["name"].lower()
    path_value = script_path or wrapper_path or ""
    current_root = str(PLUGIN_ROOT)
    if (
        cache_version
        and "plugins\\cache\\personal\\project-manager" in path_value.lower()
        and (
            "plugins\\local-marketplaces\\personal\\plugins\\project-manager" in current_root.lower()
            or (active_cache_version and cache_version != active_cache_version)
        )
    ):
        cache_bound_runtime = True
    if script_path and lower_name == "pythonw.exe":
        orphan_reason = "legacy pythonw MCP server"
        safe_to_cleanup = True
    elif script_path and cache_version and active_cache_version and cache_version != active_cache_version:
        orphan_reason = f"stale cache version {cache_version}"
        # A stale python.exe server may still be serving an old in-memory thread.
        # Report it, but do not mark it as an automatic cleanup candidate.
        safe_to_cleanup = False
    elif cache_bound_runtime:
        orphan_reason = "cache-bound MCP runtime while source wrapper is canonical"
    return {
        **normalized,
        "runtime": runtime,
        "scriptPath": script_path,
        "wrapperPath": wrapper_path,
        "cacheVersion": cache_version,
        "cacheBoundRuntime": cache_bound_runtime,
        "orphanReason": orphan_reason,
        "safeToCleanup": safe_to_cleanup,
    }


def _terminate_process(pid: int) -> bool:
    if pid <= 0 or pid == os.getpid():
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except OSError:
        return False


def _project_manager_mcp_diagnostics(scan_live: bool = False, cleanup: bool = False) -> dict[str, Any]:
    active_cache_version = _active_cache_version()
    scan_source = "env_snapshot" if os.environ.get(PROCESS_SNAPSHOT_ENV) else ("live_process_scan" if scan_live else "disabled")
    processes = [
        classified
        for classified in (
            _classify_project_manager_process(entry, active_cache_version)
            for entry in _load_project_manager_process_snapshot(scan_live=scan_live)
        )
        if classified is not None
    ]
    orphan_candidates = [process for process in processes if process.get("safeToCleanup")]
    cache_bound_processes = [process for process in processes if process.get("cacheBoundRuntime")]
    wrapper_processes = [process for process in processes if process.get("runtime") == "wrapper"]
    script_processes = [process for process in processes if process.get("runtime") == "script"]
    same_version_wrapper_processes = [
        process
        for process in wrapper_processes
        if not process.get("cacheVersion") or process.get("cacheVersion") == active_cache_version
    ]
    same_version_wrapper_cleanup_candidates = _same_version_wrapper_cleanup_candidates(same_version_wrapper_processes)
    cleanup_wrapper_pids = {process["pid"] for process in same_version_wrapper_cleanup_candidates if isinstance(process.get("pid"), int)}
    same_version_script_cleanup_candidates = [
        process for process in script_processes if process.get("parentProcessId") in cleanup_wrapper_pids
    ]
    same_version_wrapper_buildup_limit = MCP_SAFE_WRAPPER_GROUP_LIMIT
    same_version_wrapper_buildup = len(same_version_wrapper_processes) > same_version_wrapper_buildup_limit
    same_version_process_limit = MCP_PROCESS_LIMIT
    same_version_process_limit_exceeded = len(same_version_wrapper_processes) > same_version_process_limit
    cleaned_pids: list[int] = []
    failed_cleanup_pids: list[int] = []
    if cleanup:
        for process in same_version_script_cleanup_candidates:
            pid = process.get("pid")
            if not isinstance(pid, int):
                continue
            if _terminate_process(pid):
                cleaned_pids.append(pid)
            else:
                failed_cleanup_pids.append(pid)
        for process in same_version_wrapper_cleanup_candidates:
            pid = process.get("pid")
            if not isinstance(pid, int):
                continue
            if _terminate_process(pid):
                cleaned_pids.append(pid)
            else:
                failed_cleanup_pids.append(pid)
        for process in orphan_candidates:
            pid = process.get("pid")
            if not isinstance(pid, int):
                continue
            if _terminate_process(pid):
                cleaned_pids.append(pid)
            else:
                failed_cleanup_pids.append(pid)
    issues = [
        f"orphan project-manager MCP process detected: pid {process['pid']} ({process['orphanReason']})"
        for process in orphan_candidates
    ]
    if cache_bound_processes:
        issues.append(
            f"cache-bound project-manager MCP runtimes detected: {len(cache_bound_processes)} process(es) still running cache launch paths after source-wrapper rollout"
        )
    if same_version_wrapper_buildup:
        issues.append(
            f"project-manager MCP same-version wrapper buildup detected: {len(same_version_wrapper_processes)} wrapper process(es), healthy limit {same_version_wrapper_buildup_limit}"
        )
    if same_version_process_limit_exceeded:
        issues.append(
            f"project-manager MCP process explosion detected: {len(same_version_wrapper_processes)} same-version wrapper process(es), limit {same_version_process_limit}"
        )
    return {
        "activeCacheVersion": active_cache_version,
        "scanPerformed": scan_source != "disabled",
        "scanSource": scan_source,
        "cleanupRequested": cleanup,
        "recommendedIntervalMinutes": 15,
        "processCount": len(processes),
        "wrapperProcessCount": len(wrapper_processes),
        "scriptProcessCount": len(script_processes),
        "sameVersionWrapperCount": len(same_version_wrapper_processes),
        "sameVersionWrapperBuildupLimit": same_version_wrapper_buildup_limit,
        "sameVersionWrapperBuildup": same_version_wrapper_buildup,
        "sameVersionProcessLimit": same_version_process_limit,
        "sameVersionProcessLimitExceeded": same_version_process_limit_exceeded,
        "orphanCount": len(orphan_candidates),
        "cacheBoundCount": len(cache_bound_processes),
        "processes": processes,
        "sameVersionWrapperProcesses": same_version_wrapper_processes,
        "sameVersionWrapperCleanupCandidates": same_version_wrapper_cleanup_candidates,
        "sameVersionScriptCleanupCandidates": same_version_script_cleanup_candidates,
        "orphanCandidates": orphan_candidates,
        "cacheBoundProcesses": cache_bound_processes,
        "cleanedPids": cleaned_pids,
        "failedCleanupPids": failed_cleanup_pids,
        "issues": issues,
    }


def _same_version_wrapper_cleanup_candidates(processes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for process in processes:
        parent_pid = process.get("parentProcessId")
        pid = process.get("pid")
        if not isinstance(parent_pid, int) or not isinstance(pid, int):
            continue
        grouped.setdefault(parent_pid, []).append(process)
    now = datetime.now(timezone.utc)
    candidates: list[dict[str, Any]] = []
    for group in grouped.values():
        ordered = sorted(
            group,
            key=lambda process: (
                _parse_started_at(process.get("startedAt")) or datetime.min.replace(tzinfo=timezone.utc),
                process.get("pid") or 0,
            ),
        )
        overflow = ordered[:-MCP_SAFE_WRAPPER_GROUP_LIMIT] if len(ordered) > MCP_SAFE_WRAPPER_GROUP_LIMIT else []
        for process in overflow:
            started_at = _parse_started_at(process.get("startedAt"))
            age_seconds = None
            if started_at is not None:
                age_seconds = max(0, int((now - started_at).total_seconds()))
            if age_seconds is not None and age_seconds < MCP_WRAPPER_CLEANUP_MIN_AGE_SECONDS:
                continue
            candidates.append({**process, "cleanupReason": "same-version wrapper overflow", "ageSeconds": age_seconds})
    return candidates


def _load_state_from_args(args: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    state_file = args.get("stateFile")
    state_json = args.get("stateJson")
    if state_file:
        try:
            return _read_json_file(str(state_file)), None
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            return {}, str(exc)
    if isinstance(state_json, str) and state_json.strip():
        try:
            parsed = json.loads(state_json)
        except json.JSONDecodeError as exc:
            return {}, str(exc)
        if not isinstance(parsed, dict):
            return {}, "stateJson must decode to a JSON object"
        return parsed, None
    if isinstance(state_json, dict):
        return state_json, None
    return {}, None


def _score_worker_final_payload(payload: dict[str, Any]) -> tuple[int, list[str], list[str]]:
    missing = _missing_fields(payload, REQUIRED_WORKER_FINAL_FIELDS)
    findings: list[str] = []
    score = 100
    if missing:
        score -= 12 * len(missing)
        findings.append(f"missing required fields: {', '.join(missing)}")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        score -= 15
        findings.append("artifacts should be a non-empty list of concrete paths or outputs")
    verification = payload.get("verification")
    if not isinstance(verification, list) or not verification:
        score -= 15
        findings.append("verification should be a non-empty list of commands, results, or evidence")
    summary = str(payload.get("summary") or "").strip()
    if len(summary) < 20:
        score -= 10
        findings.append("summary is too short to support manager review")
    next_action = str(payload.get("next_recommended_action") or "").strip()
    if len(next_action) < 8:
        score -= 10
        findings.append("next_recommended_action is vague or missing")
    blockers = payload.get("blockers")
    if blockers is None:
        score -= 8
        findings.append("blockers must be explicit, even when empty")
    status = str(payload.get("status") or "").lower()
    if status in {"blocked", "failed"} and not blockers:
        score -= 15
        findings.append("blocked/failed status needs concrete blocker evidence")
    return max(0, score), findings, missing


def tool_manager_project_profile(args: dict[str, Any]) -> dict[str, Any]:
    profile_name = str(args.get("profile") or "generic").strip().lower()
    profile = PROJECT_PROFILES.get(profile_name)
    if profile is None:
        return _failure("unknown project profile", profile=profile_name, knownProfiles=sorted(PROJECT_PROFILES))
    return _success(profile=profile_name, settings=profile, knownProfiles=sorted(PROJECT_PROFILES))


def tool_manager_load_project_profile(args: dict[str, Any]) -> dict[str, Any]:
    profile_name = str(args.get("profile") or "generic").strip().lower()
    base = PROJECT_PROFILES.get(profile_name, PROJECT_PROFILES["generic"])
    profile_file = args.get("profileFile")
    if not profile_file:
        return _success(profile=profile_name if profile_name in PROJECT_PROFILES else "generic", settings=base, source="built-in")
    try:
        override = _read_json_file(str(profile_file))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return _failure("profile file unavailable", reason=str(exc))
    selected = override.get("profile")
    if isinstance(selected, str) and selected.strip():
        profile_name = selected.strip().lower()
        base = PROJECT_PROFILES.get(profile_name, PROJECT_PROFILES["generic"])
    settings = override.get("settings") if isinstance(override.get("settings"), dict) else override
    merged = _merge_profile(base, settings)
    worker_models = [_normalize_model(model) for model in _profile_model_list(merged, "workerModels", list(DEFAULT_WORKER_MODELS))]
    default_worker_model = _normalize_model(merged.get("defaultWorkerModel"), worker_models[0] if worker_models else "deepseek-v4-flash")
    senior_worker_model = _normalize_model(merged.get("seniorWorkerModel"), worker_models[-1] if worker_models else "deepseek-v4-pro")
    disabled_failure = _validate_worker_model_policy(worker_models, default_worker_model, senior_worker_model)
    if disabled_failure:
        return disabled_failure
    return _success(profile=profile_name if profile_name in PROJECT_PROFILES else "generic", settings=merged, source=str(profile_file))


def tool_manager_score_worker_final(args: dict[str, Any]) -> dict[str, Any]:
    try:
        payload, worker_final_input = _coerce_worker_final_from_args(args)
    except (ValueError, json.JSONDecodeError) as exc:
        return _failure(str(exc))
    score, findings, missing = _score_worker_final_payload(payload)
    if score >= 85 and not missing:
        verdict = "accept"
    elif score >= 65:
        verdict = "needs_manager_review"
    else:
        verdict = "reject_or_request_revision"
    return _success(score=score, verdict=verdict, findings=findings, missing=missing, workerFinalInput=worker_final_input)


def tool_manager_prepare_thread_action(args: dict[str, Any]) -> dict[str, Any]:
    action_type = str(args.get("actionType") or "").strip()
    if action_type not in {"create_thread", "send_message_to_thread", "read_thread"}:
        return _failure("unknown thread action type", actionType=action_type, knownActionTypes=["create_thread", "send_message_to_thread", "read_thread"])
    if action_type == "read_thread":
        read_thread_guard = _read_thread_guard_failure()
        if read_thread_guard:
            return read_thread_guard
        thread_id = args.get("threadId")
        if not isinstance(thread_id, str) or not thread_id.strip():
            return _failure("threadId is required for read_thread")
        return _success(
            actionType=action_type,
            actionPlan={"threadId": thread_id.strip()},
            ledgerEventType="thread_observation",
            executionChecklist=[
                "Call read_thread with actionPlan.threadId.",
                "Summarize the observation.",
                "Append a thread_observation ledger event if a ledger is in use.",
            ],
        )
    if action_type == "send_message_to_thread":
        thread_id = args.get("threadId")
        prompt = args.get("prompt")
        if not isinstance(thread_id, str) or not thread_id.strip():
            return _failure("threadId is required for send_message_to_thread")
        if not isinstance(prompt, str) or not prompt.strip():
            return _failure("prompt is required for send_message_to_thread")
        safe_prompt, prompt_safety = _normalize_prompt_text(
            prompt,
            max_chars=MAX_INLINE_PROMPT_CHARS,
            field_name="send_message_prompt",
        )
        changed = safe_prompt != prompt.strip()
        plan = {"threadId": thread_id.strip(), "prompt": safe_prompt}
        if args.get("model"):
            plan["model"] = _normalize_model(args.get("model"))
        if args.get("thinking"):
            plan["thinking"] = str(args["thinking"])
        return _success(
            actionType=action_type,
            actionPlan=plan,
            promptSafety={
                "changed": changed,
                "maxInlinePromptChars": MAX_INLINE_PROMPT_CHARS,
                "promptChars": len(safe_prompt),
                "warnings": prompt_safety,
                "reason": "explicit send_message_to_thread prompts are compacted only when needed for Codex transport safety",
            },
            ledgerEventType="dispatch_sent",
            failureLedgerEventType="dispatch_failed",
            executionChecklist=[
                "Call send_message_to_thread with actionPlan.",
                "If the send succeeds, append dispatch_sent and then register dispatch.",
                "If the send fails, append dispatch_failed and do not register dispatch.",
            ],
        )
    worker_packet = tool_manager_prepare_worker_thread(args)
    if worker_packet.get("status") != "ok":
        return worker_packet
    return _success(
        actionType=action_type,
        actionPlan=worker_packet["createThreadRequest"],
        ledgerEventType="dispatch_sent",
        failureLedgerEventType="dispatch_failed",
        workerModel=worker_packet["workerModel"],
        threadCreationSurface=worker_packet["threadCreationSurface"],
        executionChecklist=[
            "Call create_thread with actionPlan.",
            "If thread creation succeeds, append dispatch_sent and register dispatch.",
            "If creation fails, append dispatch_failed and do not register dispatch.",
        ],
    )


def tool_manager_recommend_recovery(args: dict[str, Any]) -> dict[str, Any]:
    profile_name = str(args.get("profile") or "generic").strip().lower()
    profile = PROJECT_PROFILES.get(profile_name, PROJECT_PROFILES["generic"])
    state, state_error = _load_state_from_args(args)
    if state_error:
        return _failure("state source unavailable", reason=state_error)
    now = _parse_time(args.get("now")) or datetime.now(timezone.utc)
    stale_after_minutes = int(args.get("staleAfterMinutes") or state.get("stale_after_minutes") or profile["staleAfterMinutes"])
    classified_workers = [
        _classify_worker(worker, now, stale_after_minutes)
        for worker in _coerce_workers(state.get("workers") or args.get("workers"))
    ]
    ledger_summary: dict[str, Any] | None = None
    if args.get("ledgerFile"):
        ledger_summary = tool_manager_ledger_summary({"ledgerFile": args["ledgerFile"]})
    dispatch_failures = 0
    if ledger_summary and ledger_summary.get("status") == "ok":
        dispatch_failures = int(ledger_summary.get("countsByType", {}).get("dispatch_failed", 0))
    blocked = [worker for worker in classified_workers if worker["attention"] == "blocked"]
    stale = [worker for worker in classified_workers if worker["attention"] == "stale"]
    review = [worker for worker in classified_workers if worker["attention"] == "needs_review"]
    if dispatch_failures >= 2:
        action = "replace_thread_or_manager_takeover"
        target = None
        rationale = "repeated dispatch failures indicate thread delivery is unhealthy"
    elif blocked:
        action = "send_recovery_prompt"
        target = blocked[0]["worker"]
        rationale = "worker reports blocker or failed/interrupted status"
    elif review:
        action = "review_worker_final"
        target = review[0]["worker"]
        rationale = "worker reached review/completion state"
    elif stale:
        action = "read_thread_then_reassign_if_no_progress"
        target = stale[0]["worker"]
        rationale = "worker is stale past threshold"
    elif bool(args.get("dispatchRequired", state.get("dispatch_required", False))):
        action = "prepare_next_worker_thread"
        target = None
        rationale = "project state requests a new dispatch"
    else:
        action = "wait_no_interrupt"
        target = None
        rationale = "workers appear healthy and no dispatch is required"
    return _success(
        profile=profile_name if profile_name in PROJECT_PROFILES else "generic",
        action=action,
        targetWorker=target,
        rationale=rationale,
        staleAfterMinutes=stale_after_minutes,
        workers=classified_workers,
        ledgerSummary=ledger_summary,
        suggestedLedgerEvent={"eventType": "decision", "payload": {"action": action, "target": target, "rationale": rationale}},
    )


def tool_manager_generate_handoff_pack(args: dict[str, Any]) -> dict[str, Any]:
    title = str(args.get("title") or "Project Manager Handoff").strip()
    state, state_error = _load_state_from_args(args)
    ledger_events: list[dict[str, Any]] = []
    ledger_error: str | None = None
    if args.get("ledgerFile"):
        try:
            ledger_events = _read_jsonl(_resolve_ledger_path(args.get("ledgerFile")))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            ledger_error = str(exc)
    limit = int(args.get("limit") or 10)
    latest_events = ledger_events[-limit:]
    lines = [
        f"# {title}",
        "",
        f"- generated_at: {_now_iso8601()}",
        f"- project_root: {state.get('project_root') or args.get('projectRoot') or 'unknown'}",
        f"- manager_thread_id: {state.get('manager_thread_id') or args.get('managerThreadId') or 'unknown'}",
        f"- ledger_events: {len(ledger_events)}",
    ]
    if state_error:
        lines.append(f"- state_error: {state_error}")
    if ledger_error:
        lines.append(f"- ledger_error: {ledger_error}")
    workers = _coerce_workers(state.get("workers") or args.get("workers"))
    if workers:
        lines.extend(["", "## Workers"])
        for worker in workers:
            lines.append(f"- {_worker_identifier(worker)}: {worker.get('status') or worker.get('state') or 'unknown'}")
    if latest_events:
        lines.extend(["", "## Recent Ledger Events"])
        for event in latest_events:
            lines.append(f"- {event.get('recorded_at')}: {event.get('event_type')} assignment={event.get('assignment_id')} thread={event.get('thread_id')}")
    lines.extend(["", "## Resume Instruction", "Run `manager_tick`, inspect any blocked/stale workers, use `manager_verified_dispatch` for new delivery, and use `manager_replace_dead_lane` when historical worker ids are unreadable or dead."])
    markdown, markdown_warnings = _normalize_prompt_text("\n".join(lines), max_chars=MAX_INLINE_PROMPT_CHARS, field_name="handoff_markdown")
    return _success(
        markdown=markdown,
        markdownSafety={
            "maxInlinePromptChars": MAX_INLINE_PROMPT_CHARS,
            "markdownChars": len(markdown),
            "compacted": bool(markdown_warnings),
            "warnings": markdown_warnings,
        },
        eventCount=len(ledger_events),
        includedEvents=len(latest_events),
    )


def tool_manager_compact_ledger(args: dict[str, Any]) -> dict[str, Any]:
    try:
        ledger_path = _resolve_ledger_path(args.get("ledgerFile"))
        events = _read_jsonl(ledger_path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("ledger compaction failed", reason=str(exc))
    keep_last = int(args.get("keepLast") or 25)
    if keep_last < 0:
        return _failure("keepLast must be zero or positive")
    summary = tool_manager_ledger_summary({"ledgerFile": str(ledger_path)})
    checkpoint = {
        "checkpoint_type": "project_manager_ledger_compaction",
        "generated_at": _now_iso8601(),
        "source_ledger": str(ledger_path),
        "original_event_count": len(events),
        "summary": summary,
        "retained_events": events[-keep_last:] if keep_last else [],
    }
    output_file = args.get("outputFile")
    if output_file:
        output_path = Path(str(output_file)).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        checkpoint_path = str(output_path)
    else:
        checkpoint_path = None
    return _success(checkpoint=checkpoint, checkpointFile=checkpoint_path)


def tool_manager_restart_recovery(args: dict[str, Any]) -> dict[str, Any]:
    recovery = tool_manager_recommend_recovery(args)
    handoff = tool_manager_generate_handoff_pack(args)
    if recovery.get("status") != "ok":
        return recovery
    return _success(
        recovery=recovery,
        handoff=handoff.get("markdown") if handoff.get("status") == "ok" else None,
        nextStep=recovery.get("action"),
        restartInstruction="Use this recommendation after restart before reading every worker thread.",
    )


def tool_manager_update_worker_registry(args: dict[str, Any]) -> dict[str, Any]:
    try:
        registry_path, registry = _read_registry(args.get("registryFile"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("registry read failed", reason=str(exc))
    worker_id = str(args.get("workerId") or "").strip()
    if not worker_id:
        return _failure("workerId is required")
    update = args.get("worker") if isinstance(args.get("worker"), dict) else {}
    current = registry["workers"].get(worker_id, {})
    if not isinstance(current, dict):
        current = {}
    current.update(update)
    for source_key, target_key in (
        ("threadId", "thread_id"),
        ("assignmentId", "assignment_id"),
        ("model", "model"),
        ("status", "status"),
        ("lastProgressAt", "last_progress_at"),
        ("acknowledgedAt", "acknowledgedAt"),
        ("acknowledgedTurnId", "acknowledgedTurnId"),
        ("acknowledgedMessageId", "acknowledgedMessageId"),
        ("progressState", "progressState"),
        ("evidenceSource", "evidenceSource"),
        ("transportConfidenceAtDispatch", "transportConfidenceAtDispatch"),
        ("packetRole", "packetRole"),
        ("deliveryTurnId", "deliveryTurnId"),
        ("deliveryMessageId", "deliveryMessageId"),
        ("deliveryVerificationEvidence", "deliveryVerificationEvidence"),
        ("lastReadbackSummary", "lastReadbackSummary"),
    ):
        if args.get(source_key) is not None:
            current[target_key] = args[source_key]
    for source_key in (
        "deliveryVisible",
        "lastVisibleTurnAt",
        "lastVerifiedHealthyAt",
        "deliveryVerified",
        "workerAcknowledged",
        "replacementOfThreadId",
        "deadReferenceReason",
        "staleConfidence",
        "activeTransactionId",
        "lastTransactionStatus",
        "lastHostActionAt",
        "modelRoutingUnavailable",
        "nativeFallbackAllowed",
        "lastSupervisorCheckAt",
    ):
        if args.get(source_key) is not None:
            current[source_key] = args[source_key]
    normalized = _normalize_registry_worker(current)
    packet_role = str(normalized.get("packetRole") or "implementer").strip().lower()
    if packet_role not in PACKET_ROLES:
        return _failure("unknown packetRole", packetRole=packet_role, knownPacketRoles=sorted(PACKET_ROLES))
    active_state = str(normalized.get("status") or "").strip().lower() in ACTIVE_WORKER_STATUSES
    evidence_source = normalized.get("evidenceSource")
    if active_state and evidence_source not in ALLOWED_EVIDENCE_SOURCES:
        return _failure(
            "active/healthy worker registry updates require an allowed evidenceSource",
            workerId=worker_id,
            evidenceSource=evidence_source,
            allowedEvidenceSources=sorted(ALLOWED_EVIDENCE_SOURCES),
        )
    if normalized.get("deliveryVisible") and not normalized.get("deliveryVerified"):
        normalized["deliveryVerified"] = True
    if normalized.get("workerAcknowledged") and not normalized.get("acknowledgedAt"):
        normalized["acknowledgedAt"] = args.get("updatedAt") or _now_iso8601()
    if normalized.get("workerAcknowledged") and not normalized.get("lastVerifiedHealthyAt"):
        normalized["lastVerifiedHealthyAt"] = normalized.get("acknowledgedAt") or normalized.get("lastVisibleTurnAt")
    if normalized.get("progressState") == "unknown":
        if normalized.get("workerAcknowledged"):
            normalized["progressState"] = "acknowledged"
        elif normalized.get("deliveryVisible"):
            normalized["progressState"] = "delivery_visible"
    current["updated_at"] = args.get("updatedAt") or _now_iso8601()
    normalized["updated_at"] = current["updated_at"]
    registry["workers"][worker_id] = normalized
    registry["updated_at"] = current["updated_at"]
    try:
        _write_registry(registry_path, registry)
    except OSError as exc:
        return _failure("registry write failed", reason=str(exc))
    return _success(registryFile=str(registry_path), workerId=worker_id, worker=normalized, workerCount=len(registry["workers"]))


def tool_manager_read_worker_registry(args: dict[str, Any]) -> dict[str, Any]:
    try:
        registry_path, registry = _read_registry(args.get("registryFile"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("registry read failed", reason=str(exc))
    worker_id = args.get("workerId")
    if isinstance(worker_id, str) and worker_id.strip():
        return _success(registryFile=str(registry_path), workerId=worker_id.strip(), worker=registry["workers"].get(worker_id.strip()))
    return _success(registryFile=str(registry_path), registry=registry, workerCount=len(registry["workers"]))


def tool_manager_registry_maintenance(args: dict[str, Any]) -> dict[str, Any]:
    try:
        registry_path, registry = _read_registry(args.get("registryFile"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("registry maintenance failed", reason=str(exc))
    recorded_at = str(args.get("recordedAt") or _now_iso8601())
    archive_dead = bool(args.get("archiveDeadReferences"))
    archive_replaced = bool(args.get("archiveReplacedWorkers"))
    archive_completed = bool(args.get("archiveCompletedWorkers"))
    archive_silent_stale = bool(args.get("archiveSilentStaleWorkers"))
    archive_reconciled = bool(args.get("archiveReconciledWorkers"))
    remaining_workers: dict[str, dict[str, Any]] = {}
    archived_workers = registry.get("archivedWorkers") or {}
    archived_count = 0
    now = _parse_time(recorded_at) or datetime.now(timezone.utc)
    stale_after_minutes = int(args.get("staleAfterMinutes") or 30)
    for worker_id, raw_worker in registry["workers"].items():
        worker = _normalize_registry_worker(raw_worker)
        status = str(worker.get("status") or "").lower()
        classified = _classify_worker(worker, now, stale_after_minutes)
        archive_reason: str | None = None
        if archive_dead and (status == "dead_reference" or worker.get("deadReferenceReason")):
            archive_reason = "dead_reference"
        elif archive_replaced and worker.get("replacementOfThreadId"):
            archive_reason = "replaced_or_superseded"
        elif archive_completed and status in {"idle_completed_needs_next_dispatch", "completed_needs_manager_review", "manager_direct_takeover_shipped_no_active_worker"}:
            archive_reason = "completed_or_inactive"
        elif archive_silent_stale and classified["attention"] in {"silent_after_delivery", "stale"}:
            archive_reason = "silent_or_stale_lane"
        elif archive_reconciled and worker.get("evidenceSource") == "registry_reconcile":
            archive_reason = "reconciled_demoted_lane"
        if archive_reason is None:
            remaining_workers[worker_id] = worker
            continue
        archived_worker = dict(worker)
        archived_worker["archivedAt"] = recorded_at
        archived_worker["archivedReason"] = archive_reason
        archived_workers[worker_id] = archived_worker
        archived_count += 1
    registry["workers"] = remaining_workers
    registry["archivedWorkers"] = archived_workers
    registry["updated_at"] = recorded_at
    try:
        _write_registry(registry_path, registry)
    except OSError as exc:
        return _failure("registry maintenance write failed", reason=str(exc))
    return _success(
        registryFile=str(registry_path),
        archivedCount=archived_count,
        activeWorkerCount=len(remaining_workers),
        archivedWorkerCount=len(archived_workers),
        recordedAt=recorded_at,
    )


def tool_manager_notification_packet(args: dict[str, Any]) -> dict[str, Any]:
    policy_packet = tool_manager_model_policy_packet(args)
    if policy_packet.get("status") != "ok":
        return policy_packet
    safe_prompt, prompt_warnings = _normalize_prompt_text(
        policy_packet["prompt"], max_chars=MAX_INLINE_PROMPT_CHARS, field_name="notification_prompt"
    )
    return _success(
        audience=policy_packet["audience"],
        prompt=safe_prompt,
        promptSafety={
            "maxInlinePromptChars": MAX_INLINE_PROMPT_CHARS,
            "promptChars": len(safe_prompt),
            "compacted": bool(prompt_warnings),
            "warnings": prompt_warnings,
        },
        models=policy_packet["workerModels"],
        degradedModels=policy_packet.get("degradedModels") or [],
        disabledModels=policy_packet.get("disabledModels") or [],
    )


def tool_manager_loaded_turn_recovery_packet(args: dict[str, Any]) -> dict[str, Any]:
    audience = str(args.get("audience") or "manager thread").strip()
    plugin_version = str(args.get("pluginVersion") or f"project-manager@personal {PLUGIN_VERSION}").strip()
    trigger = str(args.get("trigger") or "post-crash or post-rollout resync").strip()
    prompt_lines = [
        f"Turn-surface recovery update for {audience}.",
        f"Installed plugin/runtime: {plugin_version}.",
        f"Trigger: {trigger}.",
        "This recovery applies to this thread only; do not relay, delegate, or forward this packet to another thread.",
        "The repaired plugin/runtime can be healthy while an already-loaded Codex turn still carries an old missing-MCP tool surface.",
        "If project-manager MCP is missing or transport closes in this turn, do not fallback, do not invent lane health, and do not keep coordinating from this stale turn.",
        "End the stale turn quickly and rely on the next fresh turn or recurring heartbeat to rebind the tool surface.",
        "On the first fresh turn, run manager_environment_health before any coordination decision.",
        "A healthy external context can use manager_loaded_turn_rescue_plan to push that fresh rebind turn into this same manager thread automatically.",
        "Only continue manager work when the project-manager MCP namespace is callable and health no longer recommends `reload session`.",
    ]
    prompt = "\n".join(prompt_lines)
    safe_prompt, prompt_warnings = _normalize_prompt_text(
        prompt, max_chars=MAX_INLINE_PROMPT_CHARS, field_name="loaded_turn_recovery_prompt"
    )
    return _success(
        audience=audience,
        pluginVersion=plugin_version,
        trigger=trigger,
        requiresFreshTurnIfMcpMissing=True,
        prompt=safe_prompt,
        promptSafety={
            "maxInlinePromptChars": MAX_INLINE_PROMPT_CHARS,
            "promptChars": len(safe_prompt),
            "compacted": bool(prompt_warnings),
            "warnings": prompt_warnings,
        },
    )


def tool_manager_loaded_turn_rescue_plan(args: dict[str, Any]) -> dict[str, Any]:
    manager_thread_id = str(args.get("managerThreadId") or args.get("threadId") or "").strip()
    if not manager_thread_id:
        return _failure("managerThreadId is required")
    transaction_id = str(args.get("transactionId") or _transaction_id("loaded_turn_rescue", args))
    reason = str(args.get("reason") or "project-manager MCP transport closed in a stale loaded turn").strip()
    resume_instruction = str(args.get("resumeInstruction") or "").strip()
    recovery_packet = tool_manager_loaded_turn_recovery_packet(
        {
            "audience": args.get("audience") or "manager thread",
            "pluginVersion": args.get("pluginVersion"),
            "trigger": args.get("trigger") or reason,
        }
    )
    if recovery_packet.get("status") != "ok":
        return recovery_packet
    prompt_lines = [
        str(recovery_packet["prompt"]),
        "",
        f"Recovery reason: {reason}.",
        "Treat this follow-up as the fresh turn that should rebind the project-manager MCP surface for this same manager thread.",
        "Act in this same thread only. Do not forward or delegate this recovery packet to another thread.",
        "Run manager_environment_health immediately.",
        "If project-manager MCP is still unavailable in this fresh turn, stop quickly and wait for the next heartbeat or external rescue instead of coordinating manually.",
    ]
    if resume_instruction:
        prompt_lines.append(f"After health says continue, resume with this durable-state instruction: {resume_instruction}")
    else:
        prompt_lines.append(
            "After health says continue, resume the previous manager task only from durable registry/ledger state, not from assumptions carried by the stale turn."
        )
    prompt = "\n".join(prompt_lines)
    safe_prompt, prompt_warnings = _normalize_prompt_text(
        prompt, max_chars=MAX_INLINE_PROMPT_CHARS, field_name="loaded_turn_rescue_prompt"
    )
    return _success(
        transactionId=transaction_id,
        transactionType="loaded_turn_rescue",
        managerThreadId=manager_thread_id,
        recoveryReason=reason,
        hostActions=[
            {
                "tool": "send_message_to_thread",
                "resultKey": "rescue_send",
                "required": True,
                "arguments": {
                    "threadId": manager_thread_id,
                    "prompt": safe_prompt,
                },
                "instruction": "Send this exact rescue prompt into the same manager thread so Codex creates a fresh turn that can rebind project-manager MCP there. Omit model and thinking unless you explicitly need to override the manager's native GPT settings.",
            },
            {
                "tool": "read_thread",
                "resultKey": "readback",
                "required": True,
                "arguments": {"threadId": manager_thread_id, "turnLimit": 5},
                "waitBeforeMs": 4000,
                "retryPolicy": {
                    "maxAttempts": 2,
                    "retryDelayMs": 2000,
                    "retryOnErrorsContaining": list(NEW_THREAD_READBACK_RETRY_MARKERS),
                },
                "instruction": "Confirm a fresh follow-up turn is visible in the rescued manager thread before treating the rescue as complete.",
            },
        ],
        verificationRules={
            "freshTurnVisibleRequired": True,
            "failClosedOnMissingReadback": True,
        },
        pendingWrites={
            "forbiddenUntilFinalize": True,
            "ledgerFile": args.get("ledgerFile"),
            "ledgerEventsOnSuccess": ["decision"],
        },
        prompt=safe_prompt,
        promptSafety={
            "maxInlinePromptChars": MAX_INLINE_PROMPT_CHARS,
            "promptChars": len(safe_prompt),
            "compacted": bool(prompt_warnings),
            "warnings": prompt_warnings,
        },
        recoveryPacket=recovery_packet,
        nextExpectedAction="run_manager_environment_health_in_rescued_thread",
    )


def tool_manager_append_ledger_event(args: dict[str, Any]) -> dict[str, Any]:
    try:
        ledger_path = _resolve_ledger_path(args.get("ledgerFile"))
    except ValueError as exc:
        return _failure(str(exc))
    event_type = str(args.get("eventType") or "").strip()
    if event_type not in LEDGER_EVENT_TYPES:
        return _failure("unknown ledger event type", eventType=event_type, knownEventTypes=sorted(LEDGER_EVENT_TYPES))
    payload = args.get("payload") or {}
    if not isinstance(payload, dict):
        return _failure("payload must be a JSON object")
    event = {
        "event_id": args.get("eventId") or f"evt-{_now_iso8601()}",
        "event_type": event_type,
        "recorded_at": args.get("recordedAt") or _now_iso8601(),
        "project_root": args.get("projectRoot"),
        "manager_thread_id": args.get("managerThreadId"),
        "assignment_id": args.get("assignmentId") or payload.get("assignment_id") or payload.get("assignmentId"),
        "thread_id": args.get("threadId") or payload.get("thread_id") or payload.get("threadId"),
        "model": args.get("model") or payload.get("model"),
        "payload": payload,
    }
    try:
        _write_jsonl_event(ledger_path, event)
        event_count = len(_read_jsonl(ledger_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _failure("ledger write failed", reason=str(exc))
    return _success(
        ledgerFile=str(ledger_path),
        event=event,
        eventCount=event_count,
    )


def tool_manager_read_ledger(args: dict[str, Any]) -> dict[str, Any]:
    try:
        ledger_path = _resolve_ledger_path(args.get("ledgerFile"))
        events = _read_jsonl(ledger_path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("ledger read failed", reason=str(exc))
    event_type = args.get("eventType")
    assignment_id = args.get("assignmentId")
    if isinstance(event_type, str) and event_type.strip():
        events = [event for event in events if event.get("event_type") == event_type.strip()]
    if isinstance(assignment_id, str) and assignment_id.strip():
        events = [event for event in events if event.get("assignment_id") == assignment_id.strip()]
    limit = int(args.get("limit") or 20)
    if limit < 1:
        return _failure("limit must be positive")
    return _success(
        ledgerFile=str(ledger_path),
        eventCount=len(events),
        events=events[-limit:],
        truncated=len(events) > limit,
    )


def tool_manager_ledger_summary(args: dict[str, Any]) -> dict[str, Any]:
    try:
        ledger_path = _resolve_ledger_path(args.get("ledgerFile"))
        events = _read_jsonl(ledger_path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("ledger summary failed", reason=str(exc))
    counts: dict[str, int] = {}
    latest_by_assignment: dict[str, dict[str, Any]] = {}
    latest_blockers: list[dict[str, Any]] = []
    for event in events:
        event_type = str(event.get("event_type") or "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
        assignment_id = event.get("assignment_id")
        if isinstance(assignment_id, str) and assignment_id:
            latest_by_assignment[assignment_id] = event
        if event_type in {"blocker", "dispatch_failed"}:
            latest_blockers.append(event)
        if event_type == "worker_final":
            payload = event.get("payload")
            if isinstance(payload, dict) and payload.get("blockers"):
                latest_blockers.append(event)
    latest_event = events[-1] if events else None
    return _success(
        ledgerFile=str(ledger_path),
        eventCount=len(events),
        countsByType=counts,
        latestEvent=latest_event,
        activeAssignments=sorted(latest_by_assignment),
        latestBlockers=latest_blockers[-5:],
    )


def tool_manager_model_roster(args: dict[str, Any]) -> dict[str, Any]:
    profile_name, settings, profile_error = _profile_settings_from_args(args)
    manager_fallback = str(settings.get("defaultManagerModel") or "gpt-5.4")
    manager_model = _normalize_model(args.get("managerModel"), manager_fallback)
    worker_models = [_normalize_model(model) for model in _profile_model_list(settings, "workerModels", list(DEFAULT_WORKER_MODELS))]
    manager_models = [_normalize_model(model, manager_fallback) for model in _profile_model_list(settings, "managerModels", [manager_fallback])]
    default_worker_model = _normalize_model(settings.get("defaultWorkerModel"), worker_models[0] if worker_models else "deepseek-v4-flash")
    senior_worker_model = _normalize_model(settings.get("seniorWorkerModel"), worker_models[-1] if worker_models else "deepseek-v4-pro")
    disabled_failure = _validate_worker_model_policy(worker_models, default_worker_model, senior_worker_model)
    if disabled_failure:
        return disabled_failure
    catalog = _canonical_catalog_by_slug(include_disabled=True)
    return _success(
        profile=profile_name,
        profileError=profile_error,
        managerModel=manager_model,
        managerModels=[
            {"model": model, "displayName": (catalog.get(model) or {}).get("displayName") or model, **_model_meta(model, "manager")}
            for model in manager_models
        ],
        workerModels=[
            {
                "model": model,
                "displayName": (catalog.get(model) or {}).get("displayName") or model,
                **_model_meta(model, "worker"),
            }
            for model in worker_models
        ],
        defaultWorkerModel=default_worker_model,
        seniorWorkerModel=senior_worker_model,
        disabledModels=sorted(DISABLED_WORKER_MODELS),
        policy=(
            "Use GPT manager threads for project judgement, review, and lane ownership. "
            "Prefer deepseek-v4-flash as the main cheap OpenCode Go worker, escalate to deepseek-v4-pro only for harder packets, use GLM-5.2 for long-context repo exploration, and require strict worker finals."
        ),
    )


def tool_manager_model_catalog(args: dict[str, Any]) -> dict[str, Any]:
    include_disabled = bool(args.get("includeDisabled"))
    catalog = _canonical_model_catalog(include_disabled=include_disabled)
    exports = None
    if args.get("writeExports"):
        exports = _write_model_exports(_canonical_model_catalog(include_disabled=True))
    return _success(
        modelCount=len(catalog),
        enabledModelCount=sum(1 for entry in catalog if entry.get("enabled")),
        disabledModelCount=sum(1 for entry in catalog if not entry.get("enabled")),
        models=catalog,
        exports=exports,
        providerUsage=_provider_usage_summary(),
    )


def _health_finding(
    severity: str,
    code: str,
    message: str,
    *,
    evidence: Any = None,
    recommended_action: str = "continue",
) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "evidence": evidence,
        "recommendedAction": recommended_action,
    }


def _health_overall_status(findings: list[dict[str, Any]], fallback_action: str = "continue") -> str:
    codes = {str(item.get("code") or "") for item in findings}
    actions = {str(item.get("recommendedAction") or fallback_action).lower() for item in findings}
    severities = {str(item.get("severity") or "") for item in findings}
    if "blocked" in severities:
        return "blocked"
    if "reload session" in actions or {"source_cache_mismatch", "stale_loaded_session_suspicion"} & codes:
        return "reload_required"
    if {"source_cache_mismatch", "cache_source_export_mismatch"} & codes:
        return "release_mismatch"
    if {"error", "warn"} & severities:
        return "degraded"
    return "healthy"


def _export_hashes() -> dict[str, Any]:
    return {
        "canonicalCatalog": _file_sha256(MODEL_CATALOG_EXPORT_PATH),
        "proxyModelList": _file_sha256(PROXY_MODEL_LIST_EXPORT_PATH),
        "proxyRuntimeInstructions": _file_sha256(PROXY_RUNTIME_EXPORT_PATH),
    }


def tool_manager_model_export_health(args: dict[str, Any]) -> dict[str, Any]:
    catalog = _canonical_model_catalog(include_disabled=True)
    catalog_health = _catalog_health(catalog)
    model_list_export = _read_json_object_if_exists(PROXY_MODEL_LIST_EXPORT_PATH) or {}
    runtime_export = _read_json_object_if_exists(PROXY_RUNTIME_EXPORT_PATH) or {}
    model_list_metadata = model_list_export.get("metadata") if isinstance(model_list_export.get("metadata"), dict) else {}
    runtime_metadata = runtime_export.get("metadata") if isinstance(runtime_export.get("metadata"), dict) else {}
    runtime_models = runtime_export.get("models") if isinstance(runtime_export.get("models"), dict) else {}
    exported_slugs = {
        str(model.get("slug") or "").strip()
        for model in (model_list_export.get("models") or [])
        if isinstance(model, dict) and str(model.get("slug") or "").strip()
    }
    disabled_slugs = {entry["slug"] for entry in catalog if not entry.get("enabled")}
    disabled_model_route_leak = bool(disabled_slugs & exported_slugs)
    findings: list[dict[str, Any]] = []
    live_path = str(model_list_metadata.get("liveModelsPath") or runtime_metadata.get("liveModelsPath") or "")
    if live_path and _export_test_mode(Path(live_path)):
        findings.append(
            _health_finding(
                "warn",
                "poisoned_live_models_path",
                "generated proxy export points at a pytest/temp live models path",
                evidence={"liveModelsPath": live_path},
                recommended_action="rewrite exports from active plugin root",
            )
        )
    if catalog_health.get("driftDetected"):
        findings.append(
            _health_finding(
                "warn",
                "catalog_export_drift",
                "canonical catalog, live models, or proxy exports are out of sync",
                evidence=catalog_health,
                recommended_action="run export sync and proxy export validation",
            )
        )
    if disabled_model_route_leak:
        findings.append(
            _health_finding(
                "error",
                "disabled_model_route_leak",
                "disabled model is visible in proxy-facing model list",
                evidence={"disabledModels": sorted(disabled_slugs & exported_slugs)},
                recommended_action="rewrite exports before dispatching workers",
            )
        )
    disabled_runtime_entries = [
        slug for slug, row in runtime_models.items() if isinstance(row, dict) and row.get("enabled") is False
    ]
    source_export_dir = SOURCE_PLUGIN_ROOT / "generated"
    cache_version = _active_cache_version()
    cache_root = CACHE_PLUGIN_BASE / cache_version if cache_version else None
    source_proxy = source_export_dir / "proxy-model-list.json"
    cache_proxy = cache_root / "generated" / "proxy-model-list.json" if cache_root else None
    source_cache_hash_match = None
    if source_proxy.exists() and cache_proxy and cache_proxy.exists():
        source_cache_hash_match = _file_sha256(source_proxy) == _file_sha256(cache_proxy)
        if not source_cache_hash_match:
            findings.append(
                _health_finding(
                    "warn",
                    "cache_source_export_mismatch",
                    "source and cache proxy exports differ",
                    evidence={"source": str(source_proxy), "cache": str(cache_proxy)},
                    recommended_action="run controlled source-to-cache sync",
                )
            )
    overall_status = _health_overall_status(findings)
    return _success(
        overallStatus=overall_status,
        findings=findings,
        catalogHealth=catalog_health,
        disabledModelRouteLeak=disabled_model_route_leak,
        disabledRuntimeEntries=disabled_runtime_entries,
        sourceCacheExportHashMatch=source_cache_hash_match,
        paths={
            "canonicalCatalog": str(MODEL_CATALOG_EXPORT_PATH),
            "proxyModelList": str(PROXY_MODEL_LIST_EXPORT_PATH),
            "proxyRuntimeInstructions": str(PROXY_RUNTIME_EXPORT_PATH),
        },
        exportHashes=_export_hashes(),
        metadata={"modelList": model_list_metadata, "runtime": runtime_metadata},
    )


def tool_manager_model_policy_validate(args: dict[str, Any]) -> dict[str, Any]:
    profile_name, settings, profile_error = _profile_settings_from_args(args)
    worker_models = [_normalize_model(model) for model in _profile_model_list(settings, "workerModels", list(DEFAULT_WORKER_MODELS))]
    requested = [str(model).strip() for model in args.get("workerModels", []) if str(model).strip()] if isinstance(args.get("workerModels"), list) else []
    worker_models.extend(_normalize_model(model) for model in requested)
    default_worker_model = _normalize_model(args.get("defaultWorkerModel") or settings.get("defaultWorkerModel"), worker_models[0] if worker_models else "deepseek-v4-flash")
    senior_worker_model = _normalize_model(args.get("seniorWorkerModel") or settings.get("seniorWorkerModel"), "deepseek-v4-pro")
    failure = _validate_worker_model_policy(worker_models, default_worker_model, senior_worker_model)
    if failure:
        failure["profile"] = profile_name
        failure["profileError"] = profile_error
        return failure
    return _success(
        profile=profile_name,
        profileError=profile_error,
        workerModels=sorted(set(worker_models)),
        defaultWorkerModel=default_worker_model,
        seniorWorkerModel=senior_worker_model,
        disabledModels=sorted(DISABLED_WORKER_MODELS),
        policyValid=True,
    )


def tool_manager_model_policy_diff(args: dict[str, Any]) -> dict[str, Any]:
    catalog = _canonical_model_catalog(include_disabled=True)
    catalog_health = _catalog_health(catalog)
    enabled_worker_models = [
        entry["slug"]
        for entry in catalog
        if entry.get("enabled")
        and (
            entry["slug"] in DEFAULT_WORKER_MODELS
            or any(token in str(entry.get("policyRole") or "") for token in ("worker", "implementer", "coder", "synthesizer"))
        )
    ]
    return _success(
        enabledWorkerModels=enabled_worker_models,
        disabledModels=sorted(entry["slug"] for entry in catalog if not entry.get("enabled")),
        catalogHealth=catalog_health,
        exportHealth=tool_manager_model_export_health(args),
    )


def tool_manager_model_cost_policy(args: dict[str, Any]) -> dict[str, Any]:
    catalog = _canonical_model_catalog(include_disabled=True)
    tiers = {
        "default_implementation": ["deepseek-v4-flash"],
        "escalation_implementation": ["deepseek-v4-pro"],
        "manager_or_final_review": ["gpt-5.5", "gpt-5.4"],
        "light_native": ["gpt-5.4-mini", "gpt-5.3-codex-spark"],
        "support_or_bulk": ["mimo-v2.5"],
        "long_context_or_rival": ["glm-5.2", "kimi-k2.7-code"],
        "disabled": sorted(entry["slug"] for entry in catalog if not entry.get("enabled")),
    }
    return _success(
        tiers=tiers,
        policy="Flash-first for cheap implementation, Pro only on explicit escalation criteria, GPT for management/review/final gates.",
        providerUsage=_provider_usage_summary(),
    )


def tool_manager_model_advisory(args: dict[str, Any]) -> dict[str, Any]:
    profile_name, settings, profile_error = _profile_settings_from_args(args)
    selection = _select_worker_model(args, settings)
    if selection.get("status") == "failed":
        return selection
    recommended_model = str(selection["workerModel"])
    default_worker_model = str(selection["defaultWorkerModel"])
    senior_worker_model = str(selection["seniorWorkerModel"])
    fallback_model = senior_worker_model if recommended_model == default_worker_model else default_worker_model
    recommended_entry = _find_catalog_entry(recommended_model, include_disabled=True) or {}
    return _success(
        profile=profile_name,
        profileError=profile_error,
        recommendedModel=recommended_model,
        fallbackModel=fallback_model,
        escalationModel=senior_worker_model,
        rationale=selection["reason"],
        policy=selection["policy"],
        avoidedModels=sorted(DISABLED_WORKER_MODELS),
        providerLabel=recommended_entry.get("providerLabel"),
        transportRoute=recommended_entry.get("transportRoute"),
        recommendedTasks=recommended_entry.get("recommendedTasks") or [],
        avoidTasks=recommended_entry.get("avoidTasks") or [],
    )


def tool_manager_model_compatibility(args: dict[str, Any]) -> dict[str, Any]:
    requested = args.get("model") or args.get("workerModel")
    if not isinstance(requested, str) or not requested.strip():
        return _failure("model is required")
    entry = _find_catalog_entry(requested, include_disabled=True)
    if not entry:
        return _failure("unknown model", model=str(requested))
    pressure = _model_pressure_summary({"evidenceFile": args.get("evidenceFile")})
    pressure_row = (pressure.get("models") or {}).get(entry["slug"], {})
    reliability_status = str(pressure_row.get("reliabilityStatus") or "healthy")
    follow_up_viability = "viable"
    if not entry.get("enabled"):
        follow_up_viability = "disabled"
    elif reliability_status == "single_turn_only":
        follow_up_viability = "single_turn_only"
    elif reliability_status == "degraded":
        follow_up_viability = "risky"
    local_availability = entry.get("localAvailability") or {}
    return _success(
        model=entry["slug"],
        displayName=entry.get("displayName"),
        provider=entry.get("provider"),
        providerLabel=entry.get("providerLabel"),
        providerCreditSource=entry.get("providerCreditSource"),
        transportRoute=entry.get("transportRoute"),
        pickerVisible=bool(local_availability.get("pickerVisible")),
        localAvailability=local_availability,
        supportsTools=bool(entry.get("supportsTools")),
        supportsParallelToolCalls=bool(entry.get("supportsParallelToolCalls")),
        supportsImages=bool(entry.get("supportsImages")),
        continuationReliability=entry.get("continuationReliability"),
        toolLoopReliability="degraded" if reliability_status in {"degraded", "single_turn_only"} else entry.get("toolLoopReliability"),
        followUpTurnViability=follow_up_viability,
        knownFailureModes=entry.get("knownFailureModes") or [],
        enabled=bool(entry.get("enabled")),
        disabledReason=entry.get("disabledReason"),
    )


def tool_manager_model_policy_packet(args: dict[str, Any]) -> dict[str, Any]:
    profile_name, settings, profile_error = _profile_settings_from_args(args)
    roster = tool_manager_model_roster({"profile": profile_name, "profileFile": args.get("profileFile")})
    if roster.get("status") != "ok":
        return roster
    pressure = _model_pressure_summary({"evidenceFile": args.get("evidenceFile")})
    auto_degraded = sorted(
        slug
        for slug, row in (pressure.get("models") or {}).items()
        if str(row.get("reliabilityStatus") or "healthy") in {"degraded", "single_turn_only"}
    )
    degraded_models = [str(item) for item in (args.get("degradedModels") or auto_degraded) if str(item).strip()]
    disabled_models = sorted(DISABLED_WORKER_MODELS)
    audience = str(args.get("audience") or "manager lanes").strip()
    worker_models = [str(model.get("model") or "") for model in roster.get("workerModels") or [] if str(model.get("model") or "").strip()]
    default_worker_model = str(roster.get("defaultWorkerModel") or "deepseek-v4-flash")
    escalation_worker_model = str(roster.get("seniorWorkerModel") or "deepseek-v4-pro")
    prompt_lines = [
        f"Policy update for {audience}.",
        f"Current default worker model: {default_worker_model}.",
        f"Current escalation worker model: {escalation_worker_model}.",
        "Use manager_verified_dispatch for new worker delivery and manager_replace_dead_lane for unreadable historical lanes.",
        "Use manager_model_advisory when the packet role or risk is unclear instead of improvising model choice in the prompt.",
        "If this turn still lacks project-manager MCP after a crash, repair, or rollout, stop this turn quickly and let the next fresh turn or heartbeat rebind the tool surface before continuing.",
        "qwen3.7-plus remains hard-disabled.",
    ]
    if degraded_models:
        prompt_lines.append(f"Currently degraded or restricted models: {', '.join(degraded_models)}.")
    if worker_models:
        prompt_lines.append(f"Enabled worker roster: {', '.join(worker_models)}.")
    return _success(
        audience=audience,
        profile=profile_name,
        profileError=profile_error,
        defaultWorkerModel=default_worker_model,
        escalationWorkerModel=escalation_worker_model,
        workerModels=worker_models,
        degradedModels=degraded_models,
        disabledModels=disabled_models,
        prompt="\n".join(prompt_lines),
    )


def tool_manager_model_pressure_summary(args: dict[str, Any]) -> dict[str, Any]:
    pressure = _model_pressure_summary(args)
    models = pressure.get("models") or {}
    degraded_models = sorted(
        slug for slug, row in models.items() if str(row.get("reliabilityStatus") or "healthy") in {"degraded", "single_turn_only"}
    )
    blocked_models = sorted(
        slug for slug, row in models.items() if str(row.get("reliabilityStatus") or "healthy") == "single_turn_only"
    )
    return _success(
        evidenceFile=pressure.get("path"),
        models=models,
        degradedModels=degraded_models,
        blockedModels=blocked_models,
    )


def tool_manager_select_worker_model(args: dict[str, Any]) -> dict[str, Any]:
    profile_name, settings, profile_error = _profile_settings_from_args(args)
    selection = _select_worker_model(args, settings)
    if selection.get("status") == "failed":
        return selection
    return _success(
        profile=profile_name,
        profileError=profile_error,
        workerModel=selection["workerModel"],
        defaultWorkerModel=selection["defaultWorkerModel"],
        seniorWorkerModel=selection["seniorWorkerModel"],
        escalated=selection["escalated"],
        rationale=selection["reason"],
        policy=selection["policy"],
    )


def tool_manager_prepare_worker_thread(args: dict[str, Any]) -> dict[str, Any]:
    missing = _missing_fields(args, ["assignmentId", "assignmentPath", "goal", "constraints", "definitionOfDone"])
    if missing:
        return _failure("missing required fields", missing=missing)
    profile_name, settings, profile_error = _profile_settings_from_args(args)
    packet_role = str(args.get("packetRole") or "implementer").strip().lower()
    if packet_role not in PACKET_ROLES:
        return _failure("unknown packetRole", packetRole=packet_role, knownPacketRoles=sorted(PACKET_ROLES))
    worker_models = [_normalize_model(model) for model in _profile_model_list(settings, "workerModels", list(DEFAULT_WORKER_MODELS))]
    selection = _select_worker_model(args, settings)
    if selection.get("status") == "failed":
        return selection
    worker_model = str(selection["workerModel"])
    catalog_entry = _find_catalog_entry(worker_model, include_disabled=True) or {}
    allowed_models = set(worker_models) | {entry["slug"] for entry in _canonical_model_catalog(include_disabled=False)} | {worker_model}
    if worker_model not in allowed_models:
        return _failure("unknown worker model", workerModel=worker_model, knownModels=sorted(allowed_models))
    target_type = str(args.get("targetType") or "projectless")
    target: dict[str, Any]
    project_id = args.get("projectId")
    if target_type == "project":
        if not isinstance(project_id, str) or not project_id.strip():
            return _failure("projectId is required when targetType=project")
        target = {
            "type": "project",
            "projectId": project_id.strip(),
            "environment": {"type": str(args.get("environment") or "local")},
        }
    else:
        target = {
            "type": "projectless",
            "directoryName": args.get("directoryName") or f"pm-worker-{args['assignmentId']}",
        }

    title = str(args.get("title") or f"PM worker {args['assignmentId']}").strip()
    model_guidance = _catalog_entry_model_guidance(catalog_entry)
    prompt, prompt_safety = _safe_packet_prompt(
        title=title,
        assignment_id=args["assignmentId"],
        assignment_path=args["assignmentPath"],
        goal=args["goal"],
        constraints=args["constraints"],
        definition_of_done=args["definitionOfDone"],
        packet_role=packet_role,
        worker_model=worker_model,
        model_guidance=model_guidance,
        include_manager_banner=True,
        final_instruction=(
            "When finished or blocked, return a strict worker final JSON with assignment_id, status, summary, "
            "artifacts, verification, blockers, and next_recommended_action. Keep fields concise and prefer artifact "
            "paths over embedding bulky content."
        ),
    )
    create_thread_request = {
        "model": worker_model,
        "thinking": _thinking_for_model(worker_model, args.get("thinking")),
        "prompt": prompt,
        "target": target,
    }
    return _success(
        assignmentId=str(args["assignmentId"]),
        profile=profile_name,
        profileError=profile_error,
        packetRole=packet_role,
        workerModel=worker_model,
        modelRole=_model_meta(worker_model, "worker")["role"],
        managerModel=_normalize_model(args.get("managerModel"), str(settings.get("defaultManagerModel") or "gpt-5.4")),
        threadCreationSurface=_native_thread_creation_surface(worker_model),
        createThreadRequest=create_thread_request,
        dispatchRegistrationHint="Only call manager_register_dispatch_after_send after create_thread returns successfully.",
        modelGuidance=model_guidance,
        promptSafety=prompt_safety,
        modelSelection={
            "escalated": bool(selection["escalated"]),
            "rationale": selection["reason"],
            "policy": selection["policy"],
        },
    )


def _verified_dispatch_write_state(
    args: dict[str, Any],
    *,
    thread_id: str,
    replacement_of_thread_id: str | None = None,
    dead_reference_reason: str | None = None,
) -> dict[str, Any]:
    worker_id = str(args.get("workerId") or args.get("assignmentId") or "worker").strip()
    visible_turn_at = str(args.get("visibleTurnAt") or _now_iso8601())
    observed_turn_id = str(args.get("observedTurnId") or args.get("deliveryTurnId") or "").strip() or None
    observed_message_id = str(args.get("observedMessageId") or args.get("deliveryMessageId") or "").strip() or None
    delivery_verification_evidence = str(
        args.get("deliveryVerificationEvidence") or args.get("readbackSummary") or ""
    ).strip() or None
    registry_result = None
    ledger_result = None
    if args.get("registryFile"):
        registry_result = tool_manager_update_worker_registry(
            {
                "registryFile": args["registryFile"],
                "workerId": worker_id,
                "threadId": thread_id,
                "assignmentId": args.get("assignmentId"),
                "model": args.get("workerModel"),
                "status": "active",
                "packetRole": args.get("packetRole") or "implementer",
                "deliveryVisible": True,
                "lastVisibleTurnAt": visible_turn_at,
                "deliveryVerified": True,
                "deliveryTurnId": observed_turn_id,
                "deliveryMessageId": observed_message_id,
                "deliveryVerificationEvidence": delivery_verification_evidence,
                "workerAcknowledged": False,
                "progressState": "delivery_visible",
                "evidenceSource": "verified_readback",
                "transportConfidenceAtDispatch": args.get("transportConfidence") or "healthy",
                "lastReadbackSummary": args.get("readbackSummary"),
                "replacementOfThreadId": replacement_of_thread_id,
                "deadReferenceReason": dead_reference_reason,
                "staleConfidence": 0.0,
                "updatedAt": visible_turn_at,
            }
        )
        if registry_result.get("status") != "ok":
            return registry_result
    if replacement_of_thread_id and args.get("registryFile") and args.get("deadWorkerId"):
        dead_worker_id = str(args["deadWorkerId"]).strip()
        dead_update = tool_manager_update_worker_registry(
            {
                "registryFile": args["registryFile"],
                "workerId": dead_worker_id,
                "threadId": args.get("deadThreadId") or replacement_of_thread_id,
                "status": "dead_reference",
                "deadReferenceReason": dead_reference_reason,
                "replacementOfThreadId": replacement_of_thread_id,
                "staleConfidence": 1.0,
                "updatedAt": visible_turn_at,
            }
        )
        if dead_update.get("status") != "ok":
            return dead_update
    if args.get("ledgerFile"):
        ledger_result = tool_manager_append_ledger_event(
            {
                "ledgerFile": args["ledgerFile"],
                "eventType": "dispatch_sent",
                "projectRoot": args.get("projectRoot"),
                "managerThreadId": args.get("managerThreadId"),
                "assignmentId": args.get("assignmentId"),
                "threadId": thread_id,
                "model": args.get("workerModel"),
                "recordedAt": visible_turn_at,
                "payload": {
                    "assignment_id": args.get("assignmentId"),
                    "threadId": thread_id,
                    "deliveryVisible": True,
                    "deliveryVerified": True,
                    "deliveryTurnId": observed_turn_id,
                    "deliveryMessageId": observed_message_id,
                    "deliveryVerificationEvidence": delivery_verification_evidence,
                    "workerAcknowledged": False,
                    "progressState": "delivery_visible",
                    "lastVisibleTurnAt": visible_turn_at,
                    "readbackSummary": args.get("readbackSummary"),
                    "replacementOfThreadId": replacement_of_thread_id,
                    "deadReferenceReason": dead_reference_reason,
                },
            }
        )
        if ledger_result.get("status") != "ok":
            return ledger_result
    return _success(
        phase="verified",
        workerId=worker_id,
        threadId=thread_id,
        deliveryVisible=True,
        workerAcknowledged=False,
        visibleTurnAt=visible_turn_at,
        deliveryTurnId=observed_turn_id,
        deliveryMessageId=observed_message_id,
        deliveryVerificationEvidence=delivery_verification_evidence,
        replacementOfThreadId=replacement_of_thread_id,
        deadReferenceReason=dead_reference_reason,
        registry=registry_result,
        ledger=ledger_result,
    )


def tool_manager_verified_dispatch(args: dict[str, Any]) -> dict[str, Any]:
    dispatch_succeeded = args.get("dispatchSucceeded")
    delivery_verified = args.get("deliveryVerified")
    send_existing = isinstance(args.get("threadId"), str) and str(args.get("threadId")).strip() and isinstance(args.get("prompt"), str) and str(args.get("prompt")).strip()
    if send_existing:
        worker_model_result = tool_manager_select_worker_model(args)
        if worker_model_result.get("status") != "ok":
            return worker_model_result
        worker_model = worker_model_result["workerModel"]
        dispatch_action = {
            "type": "send_message_to_thread",
            "request": {
                "threadId": str(args["threadId"]).strip(),
                "prompt": str(args["prompt"]).strip(),
                "model": worker_model,
                "thinking": _thinking_for_model(worker_model, args.get("thinking")),
            },
        }
    else:
        prepared_worker = tool_manager_prepare_worker_thread(args)
        if prepared_worker.get("status") != "ok":
            return prepared_worker
        worker_model = prepared_worker["workerModel"]
        dispatch_action = {"type": "create_thread", "request": prepared_worker["createThreadRequest"]}
    if dispatch_succeeded is not True:
        return _success(
            phase="prepare",
            dispatchAction=dispatch_action,
            readbackAction={
                "type": "read_thread",
                "threadIdField": "observedThreadId",
                "readinessStrategy": _new_thread_readback_strategy(),
                "verificationRule": "Confirm a visible new turn from this dispatch before calling manager_verified_dispatch with dispatchSucceeded=true and deliveryVerified=true.",
                "operatorInstruction": "For a newly created thread, wait 8 seconds before the first read_thread attempt. If Codex reports 'rollout is empty', 'unknown conversation', or 'Conversation state not found', wait 4 seconds and retry up to 3 total attempts before failing closed.",
            },
            failClosedRule="Do not write registry or ledger state unless readback shows a visible new turn.",
            workerModel=worker_model,
        )
    observed_thread_id = str(args.get("observedThreadId") or args.get("threadId") or "").strip()
    if not observed_thread_id:
        return _failure("observedThreadId is required after dispatch succeeds")
    if delivery_verified is not True:
        return _failure("readback did not show a visible new turn; verified dispatch fails closed")
    verified_args = dict(args)
    verified_args["workerModel"] = worker_model
    return _verified_dispatch_write_state(verified_args, thread_id=observed_thread_id)


def tool_manager_replace_dead_lane(args: dict[str, Any]) -> dict[str, Any]:
    dead_reference_reason = str(args.get("deadReferenceReason") or "").strip()
    dead_thread_id = str(args.get("deadThreadId") or "").strip()
    if not dead_reference_reason:
        return _failure("deadReferenceReason is required")
    if not dead_thread_id:
        return _failure("deadThreadId is required")
    prepared_worker = tool_manager_prepare_worker_thread(args)
    if prepared_worker.get("status") != "ok":
        return prepared_worker
    if args.get("dispatchSucceeded") is not True:
        return _success(
            phase="prepare",
            replacementOfThreadId=dead_thread_id,
            deadReferenceReason=dead_reference_reason,
            dispatchAction={"type": "create_thread", "request": prepared_worker["createThreadRequest"]},
            readbackAction={
                "type": "read_thread",
                "threadIdField": "observedThreadId",
                "verificationRule": "Confirm the replacement worker has a visible new turn before marking the dead lane replaced.",
            },
            failClosedRule="Do not write replacement registry or ledger state unless readback shows a visible new turn.",
            workerModel=prepared_worker["workerModel"],
        )
    observed_thread_id = str(args.get("observedThreadId") or "").strip()
    if not observed_thread_id:
        return _failure("observedThreadId is required after replacement dispatch succeeds")
    if args.get("deliveryVerified") is not True:
        return _failure("readback did not show a visible new turn; replacement fails closed")
    verified_args = dict(args)
    verified_args["workerModel"] = prepared_worker["workerModel"]
    return _verified_dispatch_write_state(
        verified_args,
        thread_id=observed_thread_id,
        replacement_of_thread_id=dead_thread_id,
        dead_reference_reason=dead_reference_reason,
    )


def tool_manager_dispatch_transaction_plan(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("dispatchSucceeded") is True and args.get("deliveryVerified") is not True:
        return _failure(
            "dispatch transaction failed closed because readback did not prove visible delivery",
            phase="verify_readback",
            transactionState="failed_closed_no_state_written",
            registryWriteAllowed=False,
            ledgerWriteAllowed=False,
        )
    dispatch_result = tool_manager_verified_dispatch(args)
    if dispatch_result.get("status") != "ok":
        dispatch_result.setdefault("transactionState", "failed_closed_no_state_written")
        dispatch_result.setdefault("registryWriteAllowed", False)
        dispatch_result.setdefault("ledgerWriteAllowed", False)
        return dispatch_result
    if dispatch_result.get("phase") == "prepare":
        return _success(
            phase="prepare",
            transactionState="prepared_not_mutated",
            registryWriteAllowed=False,
            ledgerWriteAllowed=False,
            dispatchPlan=dispatch_result,
            failClosedRule="Do not record dispatch_sent, active registry state, or workerAcknowledged until readback evidence exists.",
        )
    return _success(
        phase="verified",
        transactionState="verified_state_written",
        registryWriteAllowed=True,
        ledgerWriteAllowed=True,
        dispatchResult=dispatch_result,
    )


def _transaction_id(transaction_type: str, args: Mapping[str, Any]) -> str:
    recorded_at = str(args.get("recordedAt") or args.get("visibleTurnAt") or _now_iso8601())
    assignment_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(args.get("assignmentId") or args.get("workerId") or "unscoped")).strip("-")
    seed = _stable_sha256(
        {
            "type": transaction_type,
            "assignmentId": args.get("assignmentId"),
            "workerId": args.get("workerId"),
            "threadId": args.get("threadId") or args.get("deadThreadId"),
            "recordedAt": recorded_at,
        }
    )[:12]
    return f"{transaction_type}-{assignment_id or 'unscoped'}-{seed}"


def _host_results(args: Mapping[str, Any]) -> dict[str, Any]:
    raw = args.get("hostResults") or {}
    if isinstance(raw, str) and raw.strip():
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    return raw if isinstance(raw, dict) else {}


def _host_result_success(row: Any) -> bool:
    return isinstance(row, dict) and row.get("success") is True


NEW_THREAD_READBACK_WAIT_MS = 8000
NEW_THREAD_READBACK_RETRY_DELAY_MS = 4000
NEW_THREAD_READBACK_MAX_ATTEMPTS = 3
NEW_THREAD_READBACK_RETRY_MARKERS = (
    "rollout is empty",
    "thread-store internal error",
    "unknown conversation",
    "conversation state not found",
)


def _new_thread_readback_strategy() -> dict[str, Any]:
    return {
        "waitBeforeMs": NEW_THREAD_READBACK_WAIT_MS,
        "maxAttempts": NEW_THREAD_READBACK_MAX_ATTEMPTS,
        "retryDelayMs": NEW_THREAD_READBACK_RETRY_DELAY_MS,
        "retryOnErrorsContaining": list(NEW_THREAD_READBACK_RETRY_MARKERS),
        "rationale": "Freshly created Codex rollout files can be observed before their first event is flushed; the first read_thread must wait briefly and retry boundedly on empty-rollout or unknown-conversation errors.",
    }


def _readback_result(host_results: Mapping[str, Any]) -> dict[str, Any]:
    readback = host_results.get("readback")
    if isinstance(readback, dict):
        return readback
    for key, row in host_results.items():
        if str(key).startswith("read_") and isinstance(row, dict):
            return row
    return {}


def _dispatch_result(host_results: Mapping[str, Any]) -> dict[str, Any]:
    dispatch = host_results.get("dispatch")
    return dispatch if isinstance(dispatch, dict) else {}


def _append_transaction_event(args: Mapping[str, Any], event_type: str, payload: dict[str, Any], *, thread_id: Any = None) -> dict[str, Any] | None:
    if not args.get("ledgerFile"):
        return None
    return tool_manager_append_ledger_event(
        {
            "ledgerFile": args["ledgerFile"],
            "eventType": event_type,
            "eventId": f"{event_type}-{args.get('transactionId') or _transaction_id(event_type, args)}",
            "recordedAt": payload.get("recordedAt") or payload.get("visibleTurnAt") or _now_iso8601(),
            "projectRoot": args.get("projectRoot"),
            "managerThreadId": args.get("managerThreadId"),
            "assignmentId": args.get("assignmentId"),
            "threadId": thread_id,
            "model": args.get("workerModel"),
            "payload": payload,
        }
    )


def _record_atomic_failure(args: Mapping[str, Any], reason: str, host_results: Mapping[str, Any]) -> dict[str, Any]:
    transaction_id = str(args.get("transactionId") or _transaction_id("transaction", args))
    payload = {
        "transactionId": transaction_id,
        "failClosedReason": reason,
        "hostResults": host_results,
        "recordedAt": _now_iso8601(),
    }
    failed_event = _append_transaction_event(args, "transaction_failed", payload)
    host_failed_event = _append_transaction_event(args, "host_action_failed", payload) if reason == "host_action_failed" else None
    return _failure(
        "atomic transaction failed closed",
        transactionId=transaction_id,
        failClosedReason=reason,
        transactionEvent=failed_event,
        hostActionEvent=host_failed_event,
    )


def _validate_host_results_for_delivery(args: Mapping[str, Any]) -> dict[str, Any]:
    host_results = _host_results(args)
    dispatch = _dispatch_result(host_results)
    readback = _readback_result(host_results)
    if not _host_result_success(dispatch):
        return _record_atomic_failure(args, "host_action_failed", host_results)
    if not _host_result_success(readback):
        return _record_atomic_failure(args, "readback_missing_or_failed", host_results)
    observed_thread_id = str(readback.get("observedThreadId") or readback.get("threadId") or dispatch.get("threadId") or args.get("threadId") or "").strip()
    if not observed_thread_id:
        return _record_atomic_failure(args, "readback_missing_thread_id", host_results)
    visible_turn_at = str(readback.get("visibleTurnAt") or _now_iso8601())
    worker_acknowledged = bool(readback.get("assistantAuthored") or readback.get("workerFinalDetected"))
    return _success(
        hostResults=host_results,
        observedThreadId=observed_thread_id,
        observedTurnId=readback.get("observedTurnId") or readback.get("turnId"),
        visibleTurnAt=visible_turn_at,
        assistantAuthored=bool(readback.get("assistantAuthored")),
        workerFinalDetected=bool(readback.get("workerFinalDetected")),
        workerAcknowledged=worker_acknowledged,
        readbackSummary=readback.get("readbackSummary") or readback.get("summary"),
    )


OPEN_TRANSACTION_PHASES = {"prepared", "host_action_started", "readback_pending", "finalize_ready"}
CLOSED_TRANSACTION_PHASES = {"finalized", "failed", "abandoned"}


def _resolve_transaction_journal_path(args: Mapping[str, Any]) -> Path:
    for key in ("journalFile", "transactionJournalFile"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            path = Path(value).expanduser()
            if path.exists() and path.is_dir():
                raise ValueError(f"{key} must be a file path, not a directory: {path}")
            return path
    ledger_file = args.get("ledgerFile")
    if isinstance(ledger_file, str) and ledger_file.strip():
        ledger_path = _resolve_ledger_path(ledger_file)
        return ledger_path.parent / "transaction-journal.jsonl"
    profile_name, profile, profile_error = _profile_settings_from_args(dict(args))
    if profile_error:
        raise ValueError(profile_error)
    project_root = args.get("projectRoot")
    hint = profile.get("transactionJournalPathHint") or "docs/project-manager/transaction-journal.jsonl"
    path = Path(str(hint)).expanduser()
    if not path.is_absolute() and isinstance(project_root, str) and project_root.strip():
        path = Path(project_root).expanduser() / path
    elif not path.is_absolute():
        raise ValueError("journalFile, transactionJournalFile, ledgerFile, or projectRoot is required")
    if path.exists() and path.is_dir():
        raise ValueError(f"transaction journal path must be a file, not a directory: {path}")
    return path


def _transaction_thread_id(transaction: Mapping[str, Any]) -> str | None:
    host_results = transaction.get("hostResults") if isinstance(transaction.get("hostResults"), dict) else {}
    for key in ("dispatch", "send", "create", "thread"):
        row = host_results.get(key)
        if isinstance(row, dict):
            thread_id = row.get("threadId") or row.get("createdThreadId") or row.get("targetThreadId")
            if isinstance(thread_id, str) and thread_id.strip():
                return thread_id.strip()
    readback = _readback_result(host_results)
    thread_id = readback.get("observedThreadId") or readback.get("threadId")
    if isinstance(thread_id, str) and thread_id.strip():
        return thread_id.strip()
    for key in ("targetThreadId", "threadId", "observedThreadId"):
        value = transaction.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _transaction_has_successful_readback(transaction: Mapping[str, Any]) -> bool:
    host_results = transaction.get("hostResults") if isinstance(transaction.get("hostResults"), dict) else {}
    readback = _readback_result(host_results)
    return _host_result_success(readback)


def _transaction_model_route_failed(transaction: Mapping[str, Any]) -> bool:
    host_results = transaction.get("hostResults") if isinstance(transaction.get("hostResults"), dict) else {}
    model = str(transaction.get("workerModel") or transaction.get("model") or "").lower()
    for row in host_results.values():
        if not isinstance(row, dict) or row.get("success") is not False:
            continue
        text = " ".join(str(row.get(key) or "") for key in ("error", "message", "reason")).lower()
        if any(marker in text for marker in ("unsupported model", "model routing", "host rejected model", "unknown model", "invalid model")):
            return True
        if model and model in text and any(marker in text for marker in ("unsupported", "rejected", "unavailable")):
            return True
    return False


def _finalize_tool_for_transaction_type(transaction_type: str) -> str:
    return {
        "dispatch": "manager_atomic_dispatch_finalize",
        "lane_recovery": "manager_atomic_lane_recovery_finalize",
        "loaded_turn_rescue": "manager_loaded_turn_rescue_finalize",
        "thread_supervision": "manager_thread_supervisor_finalize",
        "heartbeat_automation": "manager_heartbeat_automation_finalize",
    }.get(transaction_type, "manager_host_action_result_validate")


def _compact_transaction_journal(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for event in events:
        transaction_id = str(event.get("transactionId") or event.get("transaction_id") or "").strip()
        if not transaction_id:
            continue
        current = by_id.get(transaction_id)
        if current is None:
            current = {
                "transactionId": transaction_id,
                "transactionType": event.get("transactionType") or event.get("transaction_type") or "unknown",
                "hostActions": [],
                "hostResults": {},
                "recordsCount": 0,
                "firstRecordedAt": event.get("recordedAt") or event.get("recorded_at"),
            }
            by_id[transaction_id] = current
            order.append(transaction_id)
        current["recordsCount"] = int(current.get("recordsCount") or 0) + 1
        current["latestRecordedAt"] = event.get("recordedAt") or event.get("recorded_at") or current.get("latestRecordedAt")
        for key in (
            "transactionType",
            "phase",
            "registryFile",
            "ledgerFile",
            "failureReason",
            "finalizedState",
            "workerModel",
            "model",
            "modelRoutingUnavailable",
            "nativeFallbackAllowed",
            "targetThreadId",
            "threadId",
            "observedThreadId",
        ):
            if event.get(key) is not None:
                current[key] = event[key]
        host_actions = event.get("hostActions")
        if isinstance(host_actions, list):
            current["hostActions"] = host_actions
        host_results = event.get("hostResults")
        if isinstance(host_results, dict):
            merged = dict(current.get("hostResults") or {})
            for key, value in host_results.items():
                merged[str(key)] = value
            current["hostResults"] = merged
        if isinstance(event.get("payload"), dict):
            current["lastPayload"] = event["payload"]
    transactions = list(by_id.values())
    for transaction in transactions:
        phase = str(transaction.get("phase") or "prepared")
        transaction["phase"] = phase
        transaction["incomplete"] = phase in OPEN_TRANSACTION_PHASES
        transaction["quietHeartbeatAllowed"] = not transaction["incomplete"]
        transaction["targetThreadId"] = _transaction_thread_id(transaction)
    transactions.sort(
        key=lambda item: (
            0 if item.get("incomplete") else 1,
            str(item.get("latestRecordedAt") or item.get("firstRecordedAt") or ""),
        )
    )
    return transactions


def _read_transaction_journal(args: Mapping[str, Any]) -> tuple[Path, list[dict[str, Any]], list[dict[str, Any]]]:
    path = _resolve_transaction_journal_path(args)
    events = _read_jsonl(path)
    return path, events, _compact_transaction_journal(events)


def _journal_record_from_args(args: Mapping[str, Any]) -> dict[str, Any]:
    transaction_id = str(args.get("transactionId") or "").strip()
    if not transaction_id:
        raise ValueError("transactionId is required")
    phase = str(args.get("phase") or "prepared").strip()
    if phase not in OPEN_TRANSACTION_PHASES | CLOSED_TRANSACTION_PHASES:
        raise ValueError("phase must be prepared, host_action_started, readback_pending, finalize_ready, finalized, failed, or abandoned")
    record: dict[str, Any] = {
        "recordedAt": args.get("recordedAt") or _now_iso8601(),
        "transactionId": transaction_id,
        "transactionType": args.get("transactionType") or "unknown",
        "phase": phase,
    }
    for key in (
        "registryFile",
        "ledgerFile",
        "failureReason",
        "finalizedState",
        "workerModel",
        "model",
        "modelRoutingUnavailable",
        "nativeFallbackAllowed",
        "targetThreadId",
        "threadId",
        "observedThreadId",
    ):
        if args.get(key) is not None:
            record[key] = args[key]
    for key in ("hostActions", "hostResults", "payload", "finalizeEvidence", "finalizeResult"):
        if args.get(key) is not None:
            record[key] = args[key]
    return record


def tool_manager_transaction_journal_record(args: dict[str, Any]) -> dict[str, Any]:
    try:
        journal_path = _resolve_transaction_journal_path(args)
        record = _journal_record_from_args(args)
        _write_jsonl_event(journal_path, record)
        events = _read_jsonl(journal_path)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("transaction journal write failed", reason=str(exc))
    return _success(
        journalFile=str(journal_path),
        transactionId=record["transactionId"],
        transactionType=record["transactionType"],
        phase=record["phase"],
        record=record,
        recordCount=len(events),
    )


def tool_manager_transaction_journal_read(args: dict[str, Any]) -> dict[str, Any]:
    try:
        journal_path, events, transactions = _read_transaction_journal(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("transaction journal read failed", reason=str(exc))
    transaction_id = args.get("transactionId")
    if isinstance(transaction_id, str) and transaction_id.strip():
        transactions = [item for item in transactions if item.get("transactionId") == transaction_id.strip()]
    limit = int(args.get("limit") or len(transactions) or 50)
    transactions = transactions[: max(0, limit)]
    open_count = sum(1 for item in transactions if item.get("incomplete"))
    return _success(
        journalFile=str(journal_path),
        transactionCount=len(transactions),
        openTransactionCount=open_count,
        eventCount=len(events),
        transactions=transactions,
    )


def tool_manager_transaction_resume_plan(args: dict[str, Any]) -> dict[str, Any]:
    try:
        journal_path, _events, transactions = _read_transaction_journal(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("transaction resume planning failed", reason=str(exc))
    transaction_id = args.get("transactionId")
    if isinstance(transaction_id, str) and transaction_id.strip():
        transactions = [item for item in transactions if item.get("transactionId") == transaction_id.strip()]
    else:
        transactions = [item for item in transactions if item.get("incomplete")]
    if not transactions:
        return _success(journalFile=str(journal_path), nextAction="none", quietHeartbeatAllowed=True, transactions=[])
    transaction = transactions[0]
    transaction_type = str(transaction.get("transactionType") or "dispatch")
    host_results = transaction.get("hostResults") if isinstance(transaction.get("hostResults"), dict) else {}
    thread_id = _transaction_thread_id(transaction)
    quiet_allowed = False
    if _transaction_model_route_failed(transaction):
        native_fallback_allowed = bool(transaction.get("nativeFallbackAllowed"))
        return _success(
            journalFile=str(journal_path),
            transaction=transaction,
            nextAction="fail_closed_model_route_unavailable",
            modelRoutingUnavailable=True,
            nativeFallbackAllowed=native_fallback_allowed,
            quietHeartbeatAllowed=quiet_allowed,
            recoveryGuidance=(
                "Do not mark the lane active. Re-prepare with native fallback only if the project profile explicitly allows it."
                if native_fallback_allowed
                else "Do not fall back to GPT automatically; close as failed or repair host model routing first."
            ),
        )
    if transaction_type == "heartbeat_automation":
        automation = host_results.get("automation") if isinstance(host_results.get("automation"), dict) else {}
        if _host_result_success(automation):
            return _success(
                journalFile=str(journal_path),
                transaction=transaction,
                nextAction="finalize_transaction",
                finalizeTool="manager_heartbeat_automation_finalize",
                quietHeartbeatAllowed=quiet_allowed,
            )
        if automation:
            return _success(
                journalFile=str(journal_path),
                transaction=transaction,
                nextAction="record_transaction_failed",
                failureReason=automation.get("error") or "automation_update_failed",
                quietHeartbeatAllowed=quiet_allowed,
            )
        return _success(
            journalFile=str(journal_path),
            transaction=transaction,
            nextAction="validate_automation_or_operator_confirmation",
            quietHeartbeatAllowed=quiet_allowed,
        )
    if _transaction_has_successful_readback(transaction):
        return _success(
            journalFile=str(journal_path),
            transaction=transaction,
            nextAction="finalize_transaction",
            finalizeTool=_finalize_tool_for_transaction_type(transaction_type),
            quietHeartbeatAllowed=quiet_allowed,
        )
    if thread_id:
        read_thread_guard = _read_thread_guard_failure()
        if read_thread_guard:
            return _success(
                journalFile=str(journal_path),
                transaction=transaction,
                nextAction="run codex self repair",
                quietHeartbeatAllowed=quiet_allowed,
                recoveryGuidance="Repair the Codex chat process registry before attempting read_thread or finalize.",
                chatProcessRegistry=read_thread_guard.get("chatProcessRegistry"),
            )
        return _success(
            journalFile=str(journal_path),
            transaction=transaction,
            nextAction="read_thread",
            phaseToRecord="readback_pending",
            quietHeartbeatAllowed=quiet_allowed,
            hostAction={
                "tool": "read_thread",
                "resultKey": "readback",
                "required": True,
                "arguments": {"threadId": thread_id, "turnLimit": 8},
            },
        )
    return _success(
        journalFile=str(journal_path),
        transaction=transaction,
        nextAction="record_transaction_failed",
        failureReason="readback_missing_and_no_target_thread_id",
        quietHeartbeatAllowed=quiet_allowed,
    )


def tool_manager_transaction_close(args: dict[str, Any]) -> dict[str, Any]:
    close_status = str(args.get("closeStatus") or args.get("finalizedState") or "").strip().lower()
    if close_status not in CLOSED_TRANSACTION_PHASES:
        return _failure("closeStatus must be finalized, failed, or abandoned")
    if close_status == "finalized" and not (args.get("finalizeEvidence") or args.get("finalizeResult")):
        return _failure("finalizeEvidence or finalizeResult is required to close a transaction as finalized")
    if close_status in {"failed", "abandoned"} and not str(args.get("failureReason") or "").strip():
        return _failure("failureReason is required to close a transaction as failed or abandoned")
    record_args = dict(args)
    record_args["phase"] = close_status
    record_args["finalizedState"] = close_status
    result = tool_manager_transaction_journal_record(record_args)
    if result.get("status") != "ok":
        return result
    return _success(
        journalFile=result["journalFile"],
        transactionId=result["transactionId"],
        phase=close_status,
        finalizedState=close_status,
        closeStatus=close_status,
    )


def tool_manager_dispatcher_runbook(args: dict[str, Any]) -> dict[str, Any]:
    transaction_type = str(args.get("transactionType") or "dispatch")
    finalize_tool = _finalize_tool_for_transaction_type(transaction_type)
    host_actions = args.get("hostActions") if isinstance(args.get("hostActions"), list) else []
    host_tool_map = {
        "create_thread": {
            "codexHostTool": "create_thread",
            "resultShape": {"success": True, "threadId": "<created thread id>"},
        },
        "send_message_to_thread": {
            "codexHostTool": "send_message_to_thread",
            "resultShape": {"success": True, "threadId": "<target thread id>", "turnId": "<sent turn id if available>"},
        },
        "read_thread": {
            "codexHostTool": "read_thread",
            "resultShape": {
                "success": True,
                "observedThreadId": "<thread id>",
                "visibleTurnAt": "<timestamp>",
                "assistantAuthored": False,
                "workerFinalDetected": False,
                "readbackSummary": "<bounded summary>",
            },
        },
        "automation_update": {
            "codexHostTool": "automation_update",
            "resultShape": {"success": True, "automationId": "<automation id>"},
        },
    }
    dispatcher_steps = [
        {
            "step": "prepare",
            "instruction": "Call the matching atomic prepare tool and keep registry/ledger success writes forbidden.",
        },
        {
            "step": "journal_prepared",
            "tool": "manager_transaction_journal_record",
            "phase": "prepared",
            "instruction": "Persist transactionId, hostActions, registryFile, and ledgerFile before executing host actions.",
        },
        {
            "step": "execute_host_actions",
            "instruction": "Execute hostActions in order with Codex host tools and record each result fragment. For any read_thread that immediately follows create_thread, wait 8 seconds before the first read, then retry every 4 seconds up to 3 total attempts on empty-rollout or unknown-conversation errors.",
            "hostActions": [
                {
                    "tool": action.get("tool"),
                    "codexHostTool": host_tool_map.get(str(action.get("tool")), {}).get("codexHostTool"),
                    "resultKey": action.get("resultKey"),
                    "required": bool(action.get("required", True)),
                    "waitBeforeMs": action.get("waitBeforeMs"),
                    "retryPolicy": action.get("retryPolicy"),
                    "instruction": action.get("instruction"),
                }
                for action in host_actions
                if isinstance(action, dict)
            ],
        },
        {
            "step": "journal_host_results",
            "tool": "manager_transaction_journal_record",
            "phase": "host_action_started",
            "instruction": "Append hostResults after every host action so crashes can resume from durable evidence.",
        },
        {
            "step": "finalize",
            "tool": finalize_tool,
            "instruction": "Finalize only after readback or host success evidence satisfies the transaction verification rules.",
        },
        {
            "step": "close",
            "tool": "manager_transaction_close",
            "instruction": "Close as finalized only with finalize evidence; otherwise close failed/abandoned with a reason.",
        },
    ]
    markdown = (
        "# Project Manager Dispatcher Runbook\n\n"
        "1. Call the atomic prepare tool for the transaction type.\n"
        "2. Immediately call `manager_transaction_journal_record` with phase `prepared`.\n"
        "3. Execute each host action with the mapped Codex host tool and append result fragments to the journal. If a `read_thread` targets a thread created in the same transaction, wait 8 seconds before the first read and retry every 4 seconds up to 3 total attempts on `rollout is empty` or unknown-conversation errors.\n"
        "4. If Codex crashes, call `manager_transaction_resume_plan` before any new dispatch.\n"
        f"5. Call `{finalize_tool}` only after required readback evidence is present.\n"
        "6. Call `manager_transaction_close` after finalize or after a fail-closed decision.\n\n"
        "Quiet heartbeat is forbidden while any transaction is `prepared`, `host_action_started`, or `readback_pending`."
    )
    return _success(
        transactionType=transaction_type,
        finalizeTool=finalize_tool,
        hostToolMap=host_tool_map,
        dispatcherSteps=dispatcher_steps,
        quietHeartbeatBlockedPhases=["prepared", "host_action_started", "readback_pending"],
        markdown=markdown,
    )


def tool_manager_host_action_result_validate(args: dict[str, Any]) -> dict[str, Any]:
    return _validate_host_results_for_delivery(args)


def _atomic_prepare_common(args: dict[str, Any], transaction_type: str) -> dict[str, Any]:
    read_thread_guard = _read_thread_guard_failure()
    if read_thread_guard:
        return read_thread_guard
    worker_packet = tool_manager_prepare_worker_thread(args)
    if worker_packet.get("status") != "ok":
        return worker_packet
    transaction_id = str(args.get("transactionId") or _transaction_id(transaction_type, args))
    host_actions = [
        {
            "tool": "create_thread",
            "resultKey": "dispatch",
            "required": True,
            "arguments": worker_packet["createThreadRequest"],
        },
        {
            "tool": "read_thread",
            "resultKey": "readback",
            "required": True,
            "threadIdFrom": "dispatch.threadId",
            "arguments": {"threadId": "${dispatch.threadId}", "turnLimit": 5},
            "waitBeforeMs": NEW_THREAD_READBACK_WAIT_MS,
            "retryPolicy": {
                "maxAttempts": NEW_THREAD_READBACK_MAX_ATTEMPTS,
                "retryDelayMs": NEW_THREAD_READBACK_RETRY_DELAY_MS,
                "retryOnErrorsContaining": list(NEW_THREAD_READBACK_RETRY_MARKERS),
            },
            "instruction": "This read_thread follows create_thread. Wait 8 seconds before the first read, then retry every 4 seconds up to 3 total attempts if Codex reports an empty rollout or unknown-conversation state.",
        },
    ]
    return _success(
        transactionId=transaction_id,
        transactionType=transaction_type,
        workerId=str(args.get("workerId") or args.get("assignmentId") or "worker"),
        assignmentId=str(args.get("assignmentId") or ""),
        hostActions=host_actions,
        verificationRules={
            "deliveryVisibleRequired": True,
            "workerAcknowledgmentRequiresAssistantAuthoredTurnOrStrictFinal": True,
            "failClosedOnMissingReadback": True,
        },
        pendingWrites={
            "forbiddenUntilFinalize": True,
            "registryFile": args.get("registryFile"),
            "ledgerFile": args.get("ledgerFile"),
            "ledgerEventsOnSuccess": ["dispatch_sent", "transaction_finalized"],
        },
        workerPacket=worker_packet,
    )


def tool_manager_atomic_dispatch_prepare(args: dict[str, Any]) -> dict[str, Any]:
    return _atomic_prepare_common(args, "dispatch")


def tool_manager_atomic_dispatch_finalize(args: dict[str, Any]) -> dict[str, Any]:
    validation = _validate_host_results_for_delivery(args)
    if validation.get("status") != "ok":
        return validation
    transaction_id = str(args.get("transactionId") or _transaction_id("dispatch", args))
    worker_acknowledged = bool(validation.get("workerAcknowledged"))
    worker_id = str(args.get("workerId") or args.get("assignmentId") or "worker")
    thread_id = str(validation["observedThreadId"])
    visible_turn_at = str(validation["visibleTurnAt"])
    registry_result = None
    if args.get("registryFile"):
        registry_result = tool_manager_update_worker_registry(
            {
                "registryFile": args["registryFile"],
                "workerId": worker_id,
                "threadId": thread_id,
                "assignmentId": args.get("assignmentId"),
                "model": args.get("workerModel"),
                "status": "active",
                "deliveryVisible": True,
                "deliveryVerified": True,
                "workerAcknowledged": worker_acknowledged,
                "acknowledgedAt": visible_turn_at if worker_acknowledged else None,
                "lastVisibleTurnAt": visible_turn_at,
                "lastVerifiedHealthyAt": visible_turn_at if worker_acknowledged else None,
                "progressState": "acknowledged" if worker_acknowledged else "delivery_visible",
                "evidenceSource": "verified_readback",
                "deliveryTurnId": validation.get("observedTurnId"),
                "deliveryVerificationEvidence": validation.get("readbackSummary"),
                "lastReadbackSummary": validation.get("readbackSummary"),
                "activeTransactionId": transaction_id,
                "lastTransactionStatus": "finalized",
                "lastHostActionAt": visible_turn_at,
                "updatedAt": visible_turn_at,
                "replacementOfThreadId": args.get("replacementOfThreadId"),
                "deadReferenceReason": args.get("deadReferenceReason"),
            }
        )
        if registry_result.get("status") != "ok":
            return registry_result
    dispatch_event = _append_transaction_event(
        args,
        "dispatch_sent",
        {
            "transactionId": transaction_id,
            "assignment_id": args.get("assignmentId"),
            "threadId": thread_id,
            "deliveryVisible": True,
            "workerAcknowledged": worker_acknowledged,
            "progressState": "acknowledged" if worker_acknowledged else "delivery_visible",
            "visibleTurnAt": visible_turn_at,
            "readbackSummary": validation.get("readbackSummary"),
            "recordedAt": visible_turn_at,
        },
        thread_id=thread_id,
    )
    final_event = _append_transaction_event(
        args,
        "transaction_finalized",
        {
            "transactionId": transaction_id,
            "transactionType": args.get("transactionType") or "dispatch",
            "threadId": thread_id,
            "workerAcknowledged": worker_acknowledged,
            "recordedAt": visible_turn_at,
        },
        thread_id=thread_id,
    )
    return _success(
        transactionId=transaction_id,
        deliveryVisible=True,
        workerAcknowledged=worker_acknowledged,
        observedThreadId=thread_id,
        visibleTurnAt=visible_turn_at,
        registryUpdate=registry_result,
        ledgerEvents=[event for event in (dispatch_event, final_event) if event],
    )


def tool_manager_atomic_lane_recovery_prepare(args: dict[str, Any]) -> dict[str, Any]:
    if not str(args.get("deadThreadId") or "").strip():
        return _failure("deadThreadId is required")
    if not str(args.get("deadReferenceReason") or "").strip():
        return _failure("deadReferenceReason is required")
    prepared = _atomic_prepare_common(args, "lane_recovery")
    if prepared.get("status") == "ok":
        prepared["replacementOfThreadId"] = str(args.get("deadThreadId"))
        prepared["deadReferenceReason"] = str(args.get("deadReferenceReason"))
    return prepared


def tool_manager_atomic_lane_recovery_finalize(args: dict[str, Any]) -> dict[str, Any]:
    finalize_args = dict(args)
    finalize_args["transactionType"] = "lane_recovery"
    finalize_args["replacementOfThreadId"] = args.get("deadThreadId")
    result = tool_manager_atomic_dispatch_finalize(finalize_args)
    if result.get("status") != "ok":
        return result
    if args.get("registryFile") and args.get("deadWorkerId"):
        dead_update = tool_manager_update_worker_registry(
            {
                "registryFile": args["registryFile"],
                "workerId": args["deadWorkerId"],
                "threadId": args.get("deadThreadId"),
                "status": "dead_reference",
                "deadReferenceReason": args.get("deadReferenceReason"),
                "replacementOfThreadId": result.get("observedThreadId"),
                "activeTransactionId": args.get("transactionId"),
                "lastTransactionStatus": "replaced",
                "updatedAt": result.get("visibleTurnAt"),
            }
        )
        if dead_update.get("status") != "ok":
            return dead_update
        result["deadLaneUpdate"] = dead_update
    return result


def tool_manager_loaded_turn_rescue_finalize(args: dict[str, Any]) -> dict[str, Any]:
    transaction_id = str(args.get("transactionId") or _transaction_id("loaded_turn_rescue", args))
    host_results = _host_results(args)
    rescue_send = host_results.get("rescue_send")
    if not isinstance(rescue_send, dict):
        rescue_send = host_results.get("send")
    if not isinstance(rescue_send, dict):
        rescue_send = host_results.get("dispatch")
    if not _host_result_success(rescue_send):
        return _record_atomic_failure(args, "host_action_failed", host_results)
    readback = _readback_result(host_results)
    if not _host_result_success(readback):
        return _record_atomic_failure(args, "readback_missing_or_failed", host_results)
    expected_thread_id = str(
        args.get("managerThreadId") or rescue_send.get("threadId") or rescue_send.get("targetThreadId") or ""
    ).strip()
    observed_thread_id = str(readback.get("observedThreadId") or readback.get("threadId") or expected_thread_id).strip()
    if not observed_thread_id:
        return _record_atomic_failure(args, "readback_missing_thread_id", host_results)
    if expected_thread_id and observed_thread_id != expected_thread_id:
        return _record_atomic_failure(args, "readback_target_mismatch", host_results)
    visible_turn_at = str(readback.get("visibleTurnAt") or "").strip()
    if not visible_turn_at:
        return _record_atomic_failure(args, "readback_missing_visible_turn", host_results)
    readback_summary = str(readback.get("readbackSummary") or readback.get("summary") or "").strip()
    next_action = "run_manager_environment_health_in_rescued_thread"
    ledger_event = _append_transaction_event(
        args,
        "decision",
        {
            "transactionId": transaction_id,
            "action": "loaded_turn_rescue_visible",
            "managerThreadId": observed_thread_id,
            "visibleTurnAt": visible_turn_at,
            "reason": args.get("reason") or "loaded-turn rescue visible",
            "readbackSummary": readback_summary,
            "nextAction": next_action,
            "recordedAt": visible_turn_at,
        },
        thread_id=observed_thread_id,
    )
    return _success(
        transactionId=transaction_id,
        transactionType="loaded_turn_rescue",
        managerThreadId=observed_thread_id,
        freshTurnVisible=True,
        visibleTurnAt=visible_turn_at,
        readbackSummary=readback_summary,
        nextAction=next_action,
        caution="The stale original turn remains stale; continue only in the fresh follow-up turn that was just made visible.",
        ledgerEvent=ledger_event,
    )


def tool_manager_tick(args: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    state_file = args.get("stateFile")
    state_json = args.get("stateJson")
    if state_file:
        try:
            state = _read_json_file(str(state_file))
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            return _failure("state source unavailable", reason=str(exc))
    elif isinstance(state_json, str) and state_json.strip():
        try:
            parsed = json.loads(state_json)
        except json.JSONDecodeError as exc:
            return _failure("stateJson must be valid JSON", reason=str(exc))
        if not isinstance(parsed, dict):
            return _failure("stateJson must decode to a JSON object")
        state = parsed
    elif isinstance(state_json, dict):
        state = state_json

    now = _parse_time(args.get("now")) or datetime.now(timezone.utc)
    stale_after_minutes = int(args.get("staleAfterMinutes") or state.get("stale_after_minutes") or 30)
    raw_workers = state.get("workers") or args.get("workers")
    classified_workers = [
        _classify_worker(worker, now, stale_after_minutes)
        for worker in _coerce_workers(raw_workers)
    ]
    dispatch_required = bool(args.get("dispatchRequired", state.get("dispatch_required", False)))
    attention_required = dispatch_required or any(
        worker["attention"] in {"dead_reference", "blocked", "needs_review", "silent_after_delivery", "stale", "unknown", "unverified_dispatch"}
        for worker in classified_workers
    )
    return _success(
        checkedAt=now.isoformat().replace("+00:00", "Z"),
        assignmentId=args.get("assignmentId"),
        threadId=args.get("threadId"),
        projectRoot=args.get("projectRoot") or state.get("project_root"),
        managerThreadId=args.get("managerThreadId") or state.get("manager_thread_id"),
        mode=args.get("mode") or state.get("mode"),
        observedState=args.get("observedState") or state.get("observed_state", "unknown"),
        dispatchRequired=dispatch_required,
        attentionRequired=attention_required,
        quietHeartbeatAllowed=not attention_required,
        heartbeatDecisionHint=_heartbeat_decision_hint(attention_required),
        staleAfterMinutes=stale_after_minutes,
        workers=classified_workers,
        nextRecommendedAction=_recommend_next_action(classified_workers, dispatch_required),
        note=args.get("note"),
    )


def tool_manager_prepare_dispatch(args: dict[str, Any]) -> dict[str, Any]:
    missing = _missing_fields(args, REQUIRED_DISPATCH_FIELDS)
    if missing:
        return _failure("missing required fields", missing=missing)
    profile_name, settings, profile_error = _profile_settings_from_args(args)
    target = str(args.get("targetThreadId") or args.get("targetLabel") or "worker")
    goal = str(args.get("goal") or "")
    constraints = str(args.get("constraints") or "")
    definition_of_done = str(args.get("definitionOfDone") or "")
    packet_role = str(args.get("packetRole") or "implementer").strip().lower()
    if packet_role not in PACKET_ROLES:
        return _failure("unknown packetRole", packetRole=packet_role, knownPacketRoles=sorted(PACKET_ROLES))
    selection = _select_worker_model(args, settings)
    if selection.get("status") == "failed":
        return selection
    worker_model = str(selection["workerModel"])
    model_guidance = _catalog_entry_model_guidance(_find_catalog_entry(worker_model, include_disabled=True) or {})
    prompt, prompt_safety = _safe_packet_prompt(
        title=f"{target} dispatch",
        assignment_id=args["assignmentId"],
        assignment_path=args["assignmentPath"],
        goal=goal,
        constraints=constraints,
        definition_of_done=definition_of_done,
        packet_role=packet_role,
        worker_model=worker_model,
        model_guidance=model_guidance,
        include_manager_banner=False,
        final_instruction=(
            "Use the project-manager plugin/skill. Keep ownership narrow. "
            "Report a strict worker final with artifacts, verification, blockers, and next action. Keep the final compact."
        ),
    )
    return _success(
        assignmentId=str(args["assignmentId"]),
        profile=profile_name,
        profileError=profile_error,
        target=target,
        packetRole=packet_role,
        workerModel=worker_model,
        assignmentPath=str(args["assignmentPath"]),
        prompt=prompt,
        promptSafety=prompt_safety,
        modelGuidance=model_guidance,
        sendSucceeded=False,
        registeredDispatch=False,
        preparedAt=_now_iso8601(),
    )


def tool_manager_register_dispatch_after_send(args: dict[str, Any]) -> dict[str, Any]:
    if args.get("sendSucceeded") is not True:
        return _failure("sendSucceeded=true is required before dispatch registration")
    missing = _missing_fields(args, REQUIRED_DISPATCH_FIELDS)
    if missing:
        return _failure("missing required fields", missing=missing)
    return _success(
        assignmentId=str(args["assignmentId"]),
        target=args.get("targetThreadId") or args.get("targetLabel"),
        assignmentPath=str(args["assignmentPath"]),
        registeredDispatch=True,
        registeredAt=_now_iso8601(),
        managerThreadId=args.get("managerThreadId"),
        promptSummary=args.get("promptSummary"),
        sourceFinalId=args.get("sourceFinalId"),
        runId=args.get("runId"),
        candidateHash=args.get("candidateHash"),
    )


def tool_manager_register_worker_final(args: dict[str, Any]) -> dict[str, Any]:
    try:
        worker_final, worker_final_input = _coerce_worker_final_from_args(args)
    except (ValueError, json.JSONDecodeError) as exc:
        return _failure(str(exc))
    missing = _missing_fields(worker_final, REQUIRED_WORKER_FINAL_FIELDS)
    if missing:
        return _failure("missing required worker-final fields", missing=missing)
    return _success(
        assignmentId=str(worker_final["assignment_id"]),
        status=str(worker_final["status"]),
        summary=str(worker_final["summary"]),
        artifacts=worker_final["artifacts"],
        verification=worker_final["verification"],
        blockers=worker_final["blockers"],
        nextRecommendedAction=str(worker_final["next_recommended_action"]),
        ownerThread=worker_final.get("owner_thread"),
        registeredAt=_now_iso8601(),
        workerFinalInput=worker_final_input,
    )


def tool_manager_summarize_thread_observation(args: dict[str, Any]) -> dict[str, Any]:
    observation_text = str(args.get("observationText") or "").strip()
    if not observation_text:
        return _failure("observationText is required")
    normalized = " ".join(observation_text.split())
    summary = normalized[:240]
    return _success(summary=summary, truncated=len(summary) < len(normalized))


def tool_manager_environment_health(args: dict[str, Any]) -> dict[str, Any]:
    profile_name, settings, profile_error = _profile_settings_from_args(args)
    project_root = args.get("projectRoot")
    ledger_path = args.get("ledgerFile") or settings.get("ledgerPathHint")
    registry_path = args.get("registryFile") or settings.get("registryPathHint")
    heartbeat_interval = int(args.get("heartbeatIntervalMinutes") or settings.get("heartbeatIntervalMinutes") or 5)
    roster = tool_manager_model_roster({"profile": profile_name, "profileFile": args.get("profileFile")})
    mcp_runtime, mcp_issues = _mcp_runtime_status()
    orphan_diagnostics = _project_manager_mcp_diagnostics(
        scan_live=bool(args.get("scanOrphanProcesses", True) or args.get("cleanupOrphans")),
        cleanup=bool(args.get("cleanupOrphans")),
    )
    install_state = _plugin_install_state()
    wrapper_smoke = _run_wrapper_smoke(
        timeout_seconds=int(args.get("wrapperSmokeTimeoutSeconds") or 10),
        plugin_root=Path(str(install_state.get("resolvedPluginRoot") or PLUGIN_ROOT)),
    )
    log_summary = _mcp_log_summary(limit=int(args.get("logTailLines") or 30))
    chat_process_registry_health = _chat_process_registry_health()
    effective_read_thread_safe = _effective_thread_read_safe(chat_process_registry_health, orphan_diagnostics)
    codex_desktop_log_summary = (
        _codex_desktop_log_summary(
            limit_files=int(args.get("codexDesktopLogFiles") or 6),
            tail_chars=int(args.get("codexDesktopLogTailChars") or 250000),
        )
        if bool(args.get("scanCodexDesktopLogs") or args.get("scanHostHealth"))
        else {
            "status": "not_scanned",
            "root": str(CODEX_DESKTOP_LOG_ROOT),
            "filesScanned": 0,
            "nullByteJsonWarningCount": 0,
            "hugeGitCommandCount": 0,
            "maxGitArgsCount": 0,
            "recentFindings": [],
        }
    )
    local_codex_host_health = _codex_host_health(scan_live=bool(args.get("scanHostHealth")))
    model_catalog = _canonical_model_catalog(include_disabled=True)
    model_catalog_health = _catalog_health(model_catalog)
    provider_usage = _provider_usage_summary()
    checks = {
        "pluginRootExists": SOURCE_PLUGIN_ROOT.exists(),
        "resolvedPluginRootExists": PLUGIN_ROOT.exists(),
        "mcpServerExists": Path(__file__).exists(),
        "logParentReady": MCP_LOG_PATH.parent.exists() or MCP_LOG_PATH.parent.parent.exists(),
        "heartbeatIntervalMinutes": heartbeat_interval,
        "readThreadSafe": effective_read_thread_safe,
        "codexHostRecoveryArmed": bool((local_codex_host_health.get("watchdogState") or {}).get("armed")),
        "codexHealthGuardianReady": bool((local_codex_host_health.get("guardianScript") or {}).get("running")),
        "codexHostRecoveryLoopReady": bool(local_codex_host_health.get("recoveryLoopReady")),
        "codexHealthTaskReady": str((local_codex_host_health.get("scheduledTask") or {}).get("state") or "").lower()
        not in {"", "disabled"},
        **mcp_runtime,
    }
    issues: list[str] = []
    if profile_error:
        issues.append(f"profile unavailable: {profile_error}")
    if not checks["pluginRootExists"]:
        issues.append("canonical plugin root missing")
    if not checks["mcpServerExists"]:
        issues.append("MCP server script missing")
    issues.extend(mcp_issues)
    issues.extend(orphan_diagnostics["issues"])
    issues.extend(install_state["issues"])
    if wrapper_smoke.get("status") != "ok":
        issues.append(f"wrapper smoke failed: {wrapper_smoke.get('reason')}")
    if int(log_summary.get("errorCount") or 0) > 0:
        issues.append(f"recent MCP log shows {log_summary['errorCount']} error event(s)")
    if not chat_process_registry_health.get("readThreadSafe", True):
        issues.append(
            f"Codex chat process registry is corrupt at {chat_process_registry_health.get('path')}; read_thread is unsafe until repaired"
        )
    if chat_process_registry_health.get("readThreadSafe", True) and not effective_read_thread_safe:
        issues.append("Codex read_thread is unsafe while duplicate or cache-bound project-manager MCP wrapper groups are live")
    if int(codex_desktop_log_summary.get("nullByteJsonWarningCount") or 0) > 0:
        issues.append(
            f"Codex desktop logs show {codex_desktop_log_summary['nullByteJsonWarningCount']} null-byte JSON notification warning(s)"
        )
    if int(codex_desktop_log_summary.get("hugeGitCommandCount") or 0) > 0:
        issues.append(
            f"Codex desktop logs show {codex_desktop_log_summary['hugeGitCommandCount']} oversized git command(s); max argsCount={codex_desktop_log_summary.get('maxGitArgsCount')}"
        )
    if bool(args.get("scanHostHealth")) and local_codex_host_health.get("status") != "healthy":
        issues.extend(local_codex_host_health.get("issues") or [])
    if heartbeat_interval <= 0:
        issues.append("heartbeat interval must be positive")
    if model_catalog_health.get("driftDetected"):
        issues.append("model catalog drift detected")
    if str(install_state.get("sourceAlignmentStatus") or "") not in {"aligned", "aligned_via_mirror", "aligned_via_cache"}:
        issues.append(f"plugin source alignment degraded: {install_state.get('sourceAlignmentStatus')}")
    blocking_issues = [
        issue
        for issue in issues
        if "orphan project-manager MCP process detected" not in issue
        and issue != "model catalog drift detected"
    ]
    model_transport_health = _build_model_transport_health(
        profile_name=profile_name,
        settings=settings,
        roster=roster,
        install_state=install_state,
        wrapper_smoke=wrapper_smoke,
        log_summary=log_summary,
        orphan_diagnostics=orphan_diagnostics,
        chat_process_registry_health=chat_process_registry_health,
        evidence_file=args.get("evidenceFile"),
    )
    transport_health = {
        "wrapperSmoke": wrapper_smoke,
        "sourceCache": install_state,
        "staleLoadedSessionSuspicion": bool(install_state.get("staleLoadedSessionSuspicion")),
        "chatProcessRegistry": chat_process_registry_health,
        "readThreadSafe": effective_read_thread_safe,
        "recentLogSummary": log_summary,
        "recommendedOperatorAction": model_transport_health["recommendedOperatorAction"],
    }
    model_export_health = tool_manager_model_export_health({})
    health_findings: list[dict[str, Any]] = []
    if profile_error:
        health_findings.append(_health_finding("warn", "profile_unavailable", "project profile could not be loaded", evidence=profile_error))
    if str(install_state.get("sourceAlignmentStatus") or "") not in {"aligned", "aligned_via_mirror", "aligned_via_cache"}:
        health_findings.append(
            _health_finding(
                "error",
                "plugin_source_alignment_degraded",
                "resolved project-manager runtime is not aligned to the canonical maintained plugin root",
                evidence={
                    "sourceAlignmentStatus": install_state.get("sourceAlignmentStatus"),
                    "resolvedPluginRoot": install_state.get("resolvedPluginRoot"),
                    "resolvedPluginVersion": install_state.get("resolvedPluginVersion"),
                    "expectedCanonicalRoot": install_state.get("expectedCanonicalRoot"),
                    "expectedCanonicalVersion": install_state.get("expectedCanonicalVersion"),
                },
                recommended_action="run codex self repair",
            )
        )
    if install_state.get("cacheVersionMatchesSource") is False:
        health_findings.append(
            _health_finding(
                "error",
                "source_cache_mismatch",
                "source plugin version does not match active cached plugin version",
                evidence=install_state,
                recommended_action="reload session",
            )
        )
    if install_state.get("staleLoadedSessionSuspicion"):
        health_findings.append(
            _health_finding(
                "error",
                "stale_loaded_session_suspicion",
                "loaded Codex session may still be bound to an older plugin/cache version",
                evidence=install_state.get("issues"),
                recommended_action="reload session",
            )
        )
    if wrapper_smoke.get("status") != "ok":
        health_findings.append(
            _health_finding(
                "error",
                "wrapper_smoke_failed",
                "packaged MCP wrapper did not complete a JSON-RPC smoke test",
                evidence=wrapper_smoke,
                recommended_action="repair wrapper before using automation",
            )
        )
    if int(log_summary.get("errorCount") or 0) > 0:
        health_findings.append(
            _health_finding(
                "warn",
                "recent_mcp_errors",
                "recent MCP lifecycle log contains error events",
                evidence=log_summary,
                recommended_action="inspect manager_recent_events",
            )
        )
    if bool(log_summary.get("startupStormSuspected")):
        health_findings.append(
            _health_finding(
                "warn",
                "wrapper_startup_storm",
                "recent MCP lifecycle log suggests clustered repeated server starts",
                evidence=log_summary,
                recommended_action="run codex self repair",
            )
        )
    if orphan_diagnostics.get("orphanCount"):
        health_findings.append(
            _health_finding(
                "warn",
                "orphan_mcp_process",
                "old project-manager MCP processes were detected",
                evidence=orphan_diagnostics,
                recommended_action="clean up only after confirming no old thread needs them",
            )
        )
    if orphan_diagnostics.get("sameVersionProcessLimitExceeded"):
        health_findings.append(
            _health_finding(
                "error",
                "mcp_process_explosion",
                "too many same-version project-manager MCP wrapper processes are live",
                evidence={
                    "sameVersionWrapperCount": orphan_diagnostics.get("sameVersionWrapperCount"),
                    "sameVersionProcessLimit": orphan_diagnostics.get("sameVersionProcessLimit"),
                    "sample": orphan_diagnostics.get("sameVersionWrapperProcesses", [])[:5],
                },
                recommended_action="run codex self repair",
            )
        )
    elif orphan_diagnostics.get("sameVersionWrapperBuildup"):
        health_findings.append(
            _health_finding(
                "error",
                "mcp_wrapper_buildup",
                "same-version project-manager MCP wrapper groups have accumulated to a level that makes thread transport unreliable",
                evidence={
                    "sameVersionWrapperCount": orphan_diagnostics.get("sameVersionWrapperCount"),
                    "sameVersionWrapperBuildupLimit": orphan_diagnostics.get("sameVersionWrapperBuildupLimit"),
                    "sample": orphan_diagnostics.get("sameVersionWrapperProcesses", [])[:5],
                },
                recommended_action="run codex self repair",
            )
        )
    if not chat_process_registry_health.get("readThreadSafe", True):
        health_findings.append(
            _health_finding(
                "error",
                "codex_chat_process_registry_corruption",
                "Codex chat process registry is corrupt; read_thread may hang or misclassify thread state until repaired",
                evidence=chat_process_registry_health,
                recommended_action="run codex self repair",
            )
        )
    if int(codex_desktop_log_summary.get("nullByteJsonWarningCount") or 0) > 0:
        health_findings.append(
            _health_finding(
                "warn",
                "codex_notification_json_corruption",
                "Codex desktop logs contain null-byte JSON notification parse warnings",
                evidence=codex_desktop_log_summary,
                recommended_action="run codex self repair",
            )
        )
    if int(codex_desktop_log_summary.get("hugeGitCommandCount") or 0) > 0:
        health_findings.append(
            _health_finding(
                "warn",
                "codex_oversized_git_command",
                "Codex desktop logs contain oversized git command batches that can stall or destabilize the host",
                evidence=codex_desktop_log_summary,
                recommended_action="avoid broad commit automation and run codex self repair",
            )
        )
    if model_export_health.get("overallStatus") != "healthy":
        health_findings.append(
            _health_finding(
                "warn",
                "model_export_health_degraded",
                "model catalog/proxy exports need attention",
                evidence=model_export_health.get("findings"),
                recommended_action="run manager_model_export_health and rewrite exports if needed",
            )
        )
    if bool(args.get("scanHostHealth")) and local_codex_host_health.get("status") != "healthy":
        health_findings.append(
            _health_finding(
                "warn",
                "local_codex_host_bootstrap_degraded",
                "local Codex logon/bootstrap recovery path is not fully healthy",
                evidence=local_codex_host_health,
                recommended_action=str(local_codex_host_health.get("recommendedAction") or "repair startup bootstrap"),
            )
        )
    overall_status = _health_overall_status(health_findings, str(model_transport_health.get("recommendedOperatorAction") or "continue"))
    return _success(
        overallStatus=overall_status,
        healthFindings=health_findings,
        pluginVersion=CANONICAL_PLUGIN_VERSION,
        pluginRoot=str(SOURCE_PLUGIN_ROOT),
        resolvedPluginRoot=install_state.get("resolvedPluginRoot"),
        resolvedPluginVersion=install_state.get("resolvedPluginVersion"),
        resolvedWrapperPath=install_state.get("resolvedWrapperPath"),
        resolvedWrapperHash=install_state.get("resolvedWrapperHash"),
        expectedCanonicalRoot=install_state.get("expectedCanonicalRoot"),
        sourceAlignmentStatus=install_state.get("sourceAlignmentStatus"),
        mcpLogFile=str(MCP_LOG_PATH),
        profile=profile_name,
        profileError=profile_error,
        checks=checks,
        ledger=_path_status(ledger_path, project_root),
        registry=_path_status(registry_path, project_root),
        modelRoster=roster,
        nativeThreadCreation={
            **_native_thread_creation_surface(),
            "supportedWorkerModels": _profile_model_list(settings, "workerModels", list(DEFAULT_WORKER_MODELS)),
        },
        modelTransportHealth=model_transport_health,
        modelCatalogHealth=model_catalog_health,
        modelExportHealth=model_export_health,
        providerUsage=provider_usage,
        platformConstraints=_platform_constraints(),
        localCodexHostHealth=local_codex_host_health,
        chatProcessRegistry=chat_process_registry_health,
        codexDesktopLogSummary=codex_desktop_log_summary,
        transportHealth=transport_health,
        orphanMcpDiagnostics=orphan_diagnostics,
        heartbeatReady=heartbeat_interval > 0 and not blocking_issues and bool(checks.get("stdioWrapperReady")),
        issues=issues,
    )


def tool_manager_repair_plan(args: dict[str, Any]) -> dict[str, Any]:
    health = tool_manager_environment_health(args)
    findings = health.get("healthFindings") or []
    steps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for finding in findings:
        action = str(finding.get("recommendedAction") or "continue")
        if action in seen:
            continue
        seen.add(action)
        steps.append(
            {
                "action": action,
                "reason": finding.get("message"),
                "sourceFinding": finding.get("code"),
                "safeToAutomate": action not in {"reload session", "repair wrapper before using automation"},
            }
        )
    if not steps:
        steps.append({"action": "continue", "reason": "health checks did not find an actionable issue", "safeToAutomate": True})
    return _success(
        overallStatus=health.get("overallStatus"),
        recommendedOperatorAction=health.get("transportHealth", {}).get("recommendedOperatorAction"),
        findings=findings,
        steps=steps,
    )


def _run_local_install_repair() -> dict[str, Any]:
    script_root = CANONICAL_PLUGIN_ROOT if CANONICAL_PLUGIN_ROOT.exists() else PLUGIN_ROOT
    script_path = script_root / "scripts" / "repair_project_manager_install.py"
    if not script_path.exists():
        return {"status": "failed", "error": f"missing repair script: {script_path}"}
    env = dict(os.environ)
    env.setdefault("PROJECT_MANAGER_SOURCE_ROOT", str(CANONICAL_PLUGIN_ROOT))
    env.setdefault("PROJECT_MANAGER_MIRROR_ROOT", str(AGENTS_PLUGIN_ROOT))
    env.setdefault("PROJECT_MANAGER_MARKETPLACE_ROOT", str(AGENTS_MARKETPLACE_ROOT))
    env.setdefault("PROJECT_MANAGER_CACHE_BASE", str(CACHE_PLUGIN_BASE))
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        check=False,
        cwd=script_root,
        env=env,
        timeout=30,
    )
    if proc.returncode != 0:
        return {
            "status": "failed",
            "error": proc.stderr.strip() or f"repair script exited {proc.returncode}",
            "returncode": proc.returncode,
        }
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "failed", "error": f"repair script returned invalid JSON: {exc}"}
    if isinstance(payload, dict):
        return {"status": "ok", **payload}
    return {"status": "failed", "error": "repair script returned non-object payload"}


def tool_manager_self_repair(args: dict[str, Any]) -> dict[str, Any]:
    pre_repair_health = tool_manager_environment_health({**args, "cleanupOrphans": False})
    cleanup_diagnostics = _project_manager_mcp_diagnostics(scan_live=True, cleanup=True)
    install_repair = _run_local_install_repair()
    post_repair_health = tool_manager_environment_health({**args, "cleanupOrphans": False})
    recommended_next_action = (
        post_repair_health.get("transportHealth", {}).get("recommendedOperatorAction")
        if isinstance(post_repair_health, dict)
        else None
    ) or "continue"
    repair_status = "repaired" if recommended_next_action == "continue" else "partially_repaired"
    if install_repair.get("status") != "ok":
        repair_status = "blocked"
        recommended_next_action = "inspect repair failure"
    return _success(
        repairStatus=repair_status,
        recommendedNextAction=recommended_next_action,
        preRepairHealth=pre_repair_health,
        cleanupDiagnostics=cleanup_diagnostics,
        installRepair=install_repair,
        postRepairHealth=post_repair_health,
    )


def tool_manager_health_snapshot(args: dict[str, Any]) -> dict[str, Any]:
    health = tool_manager_environment_health(args)
    findings = health.get("healthFindings") or []
    loaded_turn_recovery = tool_manager_loaded_turn_recovery_packet(
        {
            "audience": args.get("audience") or "manager threads after crash/restart",
            "pluginVersion": health.get("pluginVersion"),
            "trigger": "health snapshot after crash/restart",
        }
    )
    return _success(
        snapshot={
            "pluginVersion": health.get("pluginVersion"),
            "pluginRoot": health.get("pluginRoot"),
            "overallStatus": health.get("overallStatus"),
            "recommendedOperatorAction": health.get("transportHealth", {}).get("recommendedOperatorAction"),
            "findingCodes": [str(item.get("code")) for item in findings],
            "modelExportStatus": health.get("modelExportHealth", {}).get("overallStatus"),
            "defaultWorkerModel": health.get("modelRoster", {}).get("defaultWorkerModel"),
            "heartbeatReady": health.get("heartbeatReady"),
            "checkedAt": _now_iso8601(),
            "loadedTurnRecovery": loaded_turn_recovery if loaded_turn_recovery.get("status") == "ok" else None,
        }
    )


def tool_manager_operational_audit(args: dict[str, Any]) -> dict[str, Any]:
    profile_name = str(args.get("profile") or "generic").strip().lower()
    profile = PROJECT_PROFILES.get(profile_name, PROJECT_PROFILES["generic"])
    now = _parse_time(args.get("now")) or datetime.now(timezone.utc)
    stale_after_minutes = int(args.get("staleAfterMinutes") or profile.get("staleAfterMinutes") or 30)
    try:
        registry_path, registry = _read_registry(args.get("registryFile"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("operational audit failed", reason=str(exc))
    ledger_summary = None
    delivery_failure_count = 0
    if args.get("ledgerFile"):
        ledger_summary = tool_manager_ledger_summary({"ledgerFile": args["ledgerFile"]})
        if ledger_summary.get("status") == "ok":
            delivery_failure_count = int(ledger_summary.get("countsByType", {}).get("dispatch_failed", 0))
    classified_workers = [
        _classify_worker(worker, now, stale_after_minutes)
        for worker in _coerce_workers(registry.get("workers"))
    ]
    attention_counts: dict[str, int] = {}
    action_queue: list[dict[str, Any]] = []
    transport_risk_counts: dict[str, int] = {}
    for worker in classified_workers:
        attention = str(worker.get("attention") or "unknown")
        attention_counts[attention] = attention_counts.get(attention, 0) + 1
        transport_confidence = str(worker.get("transportConfidenceAtDispatch") or "unknown")
        if transport_confidence not in {"healthy", "ok", "unknown"}:
            transport_risk_counts[transport_confidence] = transport_risk_counts.get(transport_confidence, 0) + 1
        if attention != "healthy":
            action_queue.append(
                {
                    "worker": worker["worker"],
                    "attention": attention,
                    "recommendedAction": _worker_recommended_action(worker),
                    "severity": _worker_action_severity(worker),
                }
            )
    action_queue.sort(key=lambda item: (-int(item["severity"]), str(item["worker"])))
    health_score = 100
    health_score -= min(60, attention_counts.get("dead_reference", 0) * 35)
    health_score -= min(50, attention_counts.get("blocked", 0) * 25)
    health_score -= min(45, attention_counts.get("silent_after_delivery", 0) * 22)
    health_score -= min(40, attention_counts.get("unverified_dispatch", 0) * 20)
    health_score -= min(30, attention_counts.get("stale", 0) * 15)
    health_score -= min(20, attention_counts.get("needs_review", 0) * 10)
    health_score -= min(20, attention_counts.get("unknown", 0) * 10)
    health_score -= min(20, delivery_failure_count * 5)
    return _success(
        profile=profile_name if profile_name in PROJECT_PROFILES else "generic",
        registryFile=str(registry_path),
        workerCount=len(classified_workers),
        archivedWorkerCount=len(registry.get("archivedWorkers") or {}),
        workerAttentionCounts=attention_counts,
        transportRiskCounts=transport_risk_counts,
        actionQueue=action_queue,
        deliveryFailureCount=delivery_failure_count,
        projectHealthScore=max(0, health_score),
        staleAfterMinutes=stale_after_minutes,
        checkedAt=now.isoformat().replace("+00:00", "Z"),
        workers=classified_workers,
        ledgerSummary=ledger_summary,
    )


def tool_manager_operator_runbook(args: dict[str, Any]) -> dict[str, Any]:
    recommended_action = str(args.get("recommendedOperatorAction") or "continue").strip()
    return _success(
        recommendedOperatorAction=recommended_action,
        steps=_operator_runbook_steps(recommended_action),
        notes="Use this runbook as the human/operator-facing companion to manager_environment_health transport recommendations.",
    )


def _cross_project_status(
    project_health_score: int | None,
    *,
    top_severity: int = 0,
    attention_counts: Mapping[str, Any] | None = None,
) -> str:
    attention_counts = attention_counts or {}
    if top_severity >= 3:
        return "critical"
    if int(attention_counts.get("silent_after_delivery") or 0) > 0:
        return "critical"
    if int(attention_counts.get("dead_reference") or 0) > 0:
        return "critical"
    if int(attention_counts.get("blocked") or 0) > 0:
        return "critical"
    if project_health_score is None:
        return "unknown"
    if project_health_score >= 85 and top_severity <= 0:
        return "healthy"
    return "attention"


def _cross_project_status_rank(status: str) -> int:
    if status == "critical":
        return 0
    if status == "attention":
        return 1
    if status == "healthy":
        return 2
    return 3


def tool_manager_cross_project_summary(args: dict[str, Any]) -> dict[str, Any]:
    projects = args.get("projects")
    if not isinstance(projects, list):
        return _failure("projects must be an array of project summary inputs")
    include_environment_health = bool(args.get("includeEnvironmentHealth"))
    now = args.get("now")
    rows: list[dict[str, Any]] = []
    totals = {
        "projects": 0,
        "workers": 0,
        "ledgerEvents": 0,
        "blockers": 0,
        "deliveryFailures": 0,
        "healthyProjects": 0,
        "attentionProjects": 0,
        "criticalProjects": 0,
        "silentAfterDeliveryLanes": 0,
        "deadReferenceLanes": 0,
    }
    operator_queue: list[dict[str, Any]] = []
    health_scores: list[int] = []
    for index, raw_project in enumerate(projects, start=1):
        if not isinstance(raw_project, dict):
            continue
        name = str(raw_project.get("name") or raw_project.get("project") or f"project-{index}")
        profile = str(raw_project.get("profile") or "generic").strip().lower()
        ledger_summary = None
        registry_summary = None
        operational_audit = None
        environment_health = None
        blockers = 0
        worker_count = 0
        if raw_project.get("ledgerFile"):
            ledger_summary = tool_manager_ledger_summary({"ledgerFile": raw_project["ledgerFile"]})
            if ledger_summary.get("status") == "ok":
                totals["ledgerEvents"] += int(ledger_summary.get("eventCount") or 0)
                blockers += len(ledger_summary.get("latestBlockers") or [])
        if raw_project.get("registryFile"):
            registry_summary = tool_manager_read_worker_registry({"registryFile": raw_project["registryFile"]})
            if registry_summary.get("status") == "ok":
                worker_count = int(registry_summary.get("workerCount") or 0)
            audit_args: dict[str, Any] = {
                "profile": profile,
                "registryFile": raw_project["registryFile"],
            }
            if raw_project.get("ledgerFile"):
                audit_args["ledgerFile"] = raw_project["ledgerFile"]
            if raw_project.get("staleAfterMinutes"):
                audit_args["staleAfterMinutes"] = raw_project["staleAfterMinutes"]
            if now:
                audit_args["now"] = now
            operational_audit = tool_manager_operational_audit(audit_args)
        workers = _coerce_workers(raw_project.get("workers"))
        if workers:
            worker_count = max(worker_count, len(workers))
            blockers += sum(1 for worker in workers if _worker_blockers(worker))
        if include_environment_health:
            environment_health = tool_manager_environment_health(
                {
                    "profile": profile,
                    "profileFile": raw_project.get("profileFile"),
                    "projectRoot": raw_project.get("projectRoot"),
                    "ledgerFile": raw_project.get("ledgerFile"),
                    "registryFile": raw_project.get("registryFile"),
                    "heartbeatIntervalMinutes": raw_project.get("heartbeatIntervalMinutes"),
                }
            )
        project_health_score = None
        attention_counts: dict[str, Any] = {}
        transport_risk_counts: dict[str, Any] = {}
        top_action = None
        top_severity = 0
        delivery_failures = 0
        if isinstance(operational_audit, dict) and operational_audit.get("status") == "ok":
            project_health_score = int(operational_audit.get("projectHealthScore") or 0)
            health_scores.append(project_health_score)
            attention_counts = dict(operational_audit.get("workerAttentionCounts") or {})
            transport_risk_counts = dict(operational_audit.get("transportRiskCounts") or {})
            delivery_failures = int(operational_audit.get("deliveryFailureCount") or 0)
            action_queue = operational_audit.get("actionQueue") or []
            if action_queue:
                top_action = action_queue[0]
                top_severity = int(top_action.get("severity") or 0)
        status = _cross_project_status(project_health_score, top_severity=top_severity, attention_counts=attention_counts)
        totals["projects"] += 1
        totals["workers"] += worker_count
        totals["blockers"] += blockers
        totals["deliveryFailures"] += delivery_failures
        totals["silentAfterDeliveryLanes"] += int(attention_counts.get("silent_after_delivery") or 0)
        totals["deadReferenceLanes"] += int(attention_counts.get("dead_reference") or 0)
        if status == "healthy":
            totals["healthyProjects"] += 1
        elif status == "critical":
            totals["criticalProjects"] += 1
        else:
            totals["attentionProjects"] += 1
        row = {
            "name": name,
            "profile": profile,
            "projectRoot": raw_project.get("projectRoot"),
            "workerCount": worker_count,
            "blockerCount": blockers,
            "deliveryFailureCount": delivery_failures,
            "status": status,
            "projectHealthScore": project_health_score,
            "workerAttentionCounts": attention_counts,
            "transportRiskCounts": transport_risk_counts,
            "topAction": top_action,
            "ledgerSummary": ledger_summary,
            "registrySummary": registry_summary,
            "operationalAudit": operational_audit,
            "environmentHealth": environment_health,
            "nextAction": raw_project.get("nextAction") or (top_action or {}).get("recommendedAction"),
        }
        rows.append(row)
        if top_action:
            operator_queue.append(
                {
                    "project": name,
                    "status": status,
                    "projectHealthScore": project_health_score,
                    "worker": top_action.get("worker"),
                    "recommendedAction": top_action.get("recommendedAction"),
                    "severity": top_severity,
                }
            )
    rows.sort(
        key=lambda row: (
            _cross_project_status_rank(str(row.get("status") or "unknown")),
            int(row.get("projectHealthScore") if row.get("projectHealthScore") is not None else -1),
            -int(row.get("blockerCount") or 0),
            str(row.get("name") or ""),
        )
    )
    operator_queue.sort(
        key=lambda item: (
            -int(item.get("severity") or 0),
            _cross_project_status_rank(str(item.get("status") or "unknown")),
            int(item.get("projectHealthScore") if item.get("projectHealthScore") is not None else -1),
            str(item.get("project") or ""),
        )
    )
    totals["averageProjectHealthScore"] = round(sum(health_scores) / len(health_scores), 2) if health_scores else None
    return _success(
        projects=rows,
        totals=totals,
        operatorQueue=operator_queue,
        rankedProjects=[row["name"] for row in rows],
        generatedAt=_now_iso8601(),
    )


def _format_dashboard_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_format_dashboard_value(cell) for cell in row) + " |")
    return "\n".join(lines)


def _heartbeat_rrule(interval_minutes: Any) -> str:
    interval = int(interval_minutes or 5)
    if interval < 1:
        interval = 1
    return f"FREQ=MINUTELY;INTERVAL={interval}"


def tool_manager_cross_project_dashboard(args: dict[str, Any]) -> dict[str, Any]:
    summary = tool_manager_cross_project_summary(args)
    if summary.get("status") != "ok":
        return summary
    title = str(args.get("title") or "Project Manager Dashboard").strip()
    generated_at = summary.get("generatedAt") or _now_iso8601()
    totals = summary.get("totals") or {}
    projects = summary.get("projects") or []
    operator_queue = summary.get("operatorQueue") or []

    summary_cards = [
        {"id": "projects", "label": "Projects", "value": totals.get("projects")},
        {"id": "critical_projects", "label": "Critical Projects", "value": totals.get("criticalProjects")},
        {"id": "attention_projects", "label": "Attention Projects", "value": totals.get("attentionProjects")},
        {"id": "healthy_projects", "label": "Healthy Projects", "value": totals.get("healthyProjects")},
        {"id": "workers", "label": "Workers", "value": totals.get("workers")},
        {"id": "delivery_failures", "label": "Delivery Failures", "value": totals.get("deliveryFailures")},
        {"id": "silent_lanes", "label": "Silent Lanes", "value": totals.get("silentAfterDeliveryLanes")},
        {"id": "avg_health", "label": "Avg Health", "value": totals.get("averageProjectHealthScore")},
    ]

    project_rows = [
        {
            "project": row.get("name"),
            "status": row.get("status"),
            "healthScore": row.get("projectHealthScore"),
            "workers": row.get("workerCount"),
            "blockers": row.get("blockerCount"),
            "deliveryFailures": row.get("deliveryFailureCount"),
            "topAction": (row.get("topAction") or {}).get("recommendedAction") or row.get("nextAction"),
            "profile": row.get("profile"),
            "projectRoot": row.get("projectRoot"),
        }
        for row in projects
    ]
    operator_rows = [
        {
            "project": row.get("project"),
            "worker": row.get("worker"),
            "severity": row.get("severity"),
            "healthScore": row.get("projectHealthScore"),
            "action": row.get("recommendedAction"),
        }
        for row in operator_queue
    ]
    top_priority = operator_rows[0] if operator_rows else None

    markdown_sections = [
        f"# {title}",
        "",
        f"Generated at: {generated_at}",
        "",
        "## Overview",
    ]
    markdown_sections.extend(
        f"- {card['label']}: {_format_dashboard_value(card['value'])}" for card in summary_cards
    )
    if top_priority:
        markdown_sections.extend(
            [
                "",
                "## Top Priority",
                f"- Project: {top_priority['project']}",
                f"- Worker: {_format_dashboard_value(top_priority['worker'])}",
                f"- Action: {_format_dashboard_value(top_priority['action'])}",
            ]
        )
    project_table = _markdown_table(
        ["Project", "Status", "Health", "Workers", "Blockers", "Delivery Failures", "Top Action"],
        [
            [
                row["project"],
                row["status"],
                row["healthScore"],
                row["workers"],
                row["blockers"],
                row["deliveryFailures"],
                row["topAction"],
            ]
            for row in project_rows
        ],
    )
    if project_table:
        markdown_sections.extend(["", "## Projects", project_table])
    operator_table = _markdown_table(
        ["Project", "Worker", "Severity", "Health", "Action"],
        [
            [
                row["project"],
                row["worker"],
                row["severity"],
                row["healthScore"],
                row["action"],
            ]
            for row in operator_rows
        ],
    )
    if operator_table:
        markdown_sections.extend(["", "## Operator Queue", operator_table])

    return _success(
        title=title,
        generatedAt=generated_at,
        totals=totals,
        rankedProjects=summary.get("rankedProjects") or [],
        summaryCards=summary_cards,
        topPriority=top_priority,
        projectRows=project_rows,
        operatorRows=operator_rows,
        markdown="\n".join(markdown_sections),
        sourceSummary=summary,
    )


def tool_manager_heartbeat_bootstrap(args: dict[str, Any]) -> dict[str, Any]:
    profile_name, settings, profile_error = _profile_settings_from_args(args)
    project_root = str(args.get("projectRoot") or "").strip()
    manager_thread_id = str(args.get("managerThreadId") or "").strip()
    if not project_root:
        return _failure("projectRoot is required")
    if not manager_thread_id:
        return _failure("managerThreadId is required")
    interval = int(args.get("heartbeatIntervalMinutes") or settings.get("heartbeatIntervalMinutes") or 5)
    ledger_file = str(args.get("ledgerFile") or Path(project_root) / str(settings.get("ledgerPathHint") or "docs/project-manager/manager-ledger.jsonl"))
    registry_file = str(args.get("registryFile") or Path(project_root) / str(settings.get("registryPathHint") or "docs/project-manager/worker-registry.json"))
    maintenance_every_heartbeats = int(args.get("maintenanceEveryHeartbeats") or 3)
    maintenance_cadence_minutes = max(interval * maintenance_every_heartbeats, 15)
    prompt = (
        f"<heartbeat>\n"
        f"  <automation_id>{args.get('automationId') or profile_name + '-project-manager-heartbeat'}</automation_id>\n"
        f"  <instructions>\n"
        f"Act as project manager for {project_root}, targeting manager thread {manager_thread_id}. "
        f"HARD FAIL-FAST RULE: return a final answer quickly; do not wait indefinitely for tools, MCP, shell, git, background workers, or another model. "
        f"If project-manager MCP/tools are unavailable or hung, stop using tools and return NOTIFY with reason tool_unavailable_or_hung. "
        f"If this specific turn still lacks project-manager MCP after a crash, repair, or rollout, stop quickly and rely on the next fresh turn or recurring heartbeat to rebind the tool surface before continuing. "
        f"Use the project-manager plugin first in this order: manager_environment_health, manager_model_transport_health, manager_operational_audit, then manager_tick or manager_restart_recovery if needed. "
        f"Treat implementation as subagent-driven by default: GPT owns planning and final acceptance; deepseek-v4-flash is the default implementer and routine reviewer; deepseek-v4-pro is escalation-only for harder debugging or architecture-sensitive packets. "
        f"For new or existing worker delivery, use manager_verified_dispatch and only accept verified lane state after readback shows a visible new turn. "
        f"Then use manager_lane_health_from_readback and do not treat delivery-only visibility as healthy progress. "
        f"If a historical worker id is unreadable or dead, use manager_replace_dead_lane instead of treating the lane as healthy. "
        f"After any accepted worker final, use manager_accept_worker_final_and_plan_next and dispatch the required successor packet instead of stopping at narrative progress. "
        f"Do not return DONT_NOTIFY for silent_after_delivery, stale, blocked, dead_reference, unverified_dispatch, or contradicted lanes. "
        f"Healthy lanes require verified readback or accepted worker-final evidence, not manager narration. "
        f"At least every {maintenance_every_heartbeats} heartbeats or after heavy lane churn, run manager_registry_reconcile and manager_registry_maintenance so silent, replaced, dead, or contradicted lanes do not remain conceptually active. "
        f"Do not run direct shell/build/test/git commands from the heartbeat unless the user explicitly authorized that heartbeat to execute commands. "
        f"Use ledger `{ledger_file}` and registry `{registry_file}` for durable state. "
        f"Use GPT manager models {', '.join(str(model) for model in _profile_model_list(settings, 'managerModels', ['gpt-5.4', 'gpt-5.5']))}; "
        f"use worker models {', '.join(str(model) for model in _profile_model_list(settings, 'workerModels', list(DEFAULT_WORKER_MODELS)))} according to assignment risk. "
        f"Only notify the user for dispatches, blockers, completed manager takeovers, failed sends, or human decisions; otherwise return DONT_NOTIFY.\n"
        f"  </instructions>\n"
        f"</heartbeat>"
    )
    prompt, prompt_warnings = _normalize_prompt_text(prompt, max_chars=MAX_INLINE_PROMPT_CHARS, field_name="heartbeat_prompt")
    return _success(
        profile=profile_name,
        profileError=profile_error,
        automationId=args.get("automationId") or profile_name + "-project-manager-heartbeat",
        heartbeatIntervalMinutes=interval,
        ledgerFile=ledger_file,
        registryFile=registry_file,
        maintenancePolicy={
            "everyHeartbeats": maintenance_every_heartbeats,
            "minimumCadenceMinutes": maintenance_cadence_minutes,
            "requiredTools": ["manager_registry_reconcile", "manager_registry_maintenance"],
        },
        prompt=prompt,
        promptSafety={
            "maxInlinePromptChars": MAX_INLINE_PROMPT_CHARS,
            "promptChars": len(prompt),
            "compacted": bool(prompt_warnings),
            "warnings": prompt_warnings,
        },
        setupChecklist=[
            "Create or verify the ledger parent directory inside the project.",
            "Create or verify the worker registry path inside the project.",
            f"Configure a recurring heartbeat every {interval} minutes with the generated prompt.",
            f"Schedule registry reconciliation/maintenance at least every {maintenance_every_heartbeats} heartbeats ({maintenance_cadence_minutes}+ minutes) or after major churn.",
            "Record a decision ledger event after enabling the heartbeat.",
        ],
    )


def tool_manager_automation_rollout_helper(args: dict[str, Any]) -> dict[str, Any]:
    targets = args.get("targets")
    if not isinstance(targets, list) or not targets:
        return _failure("targets must be a non-empty array of rollout targets")
    plugin_version = str(args.get("pluginVersion") or f"project-manager@personal {PLUGIN_VERSION}").strip()
    release_notes = str(args.get("releaseNotes") or "").strip()
    rollout_packets: list[dict[str, Any]] = []
    action_queue: list[dict[str, Any]] = []
    for index, raw_target in enumerate(targets, start=1):
        if not isinstance(raw_target, dict):
            continue
        manager_thread_id = str(raw_target.get("managerThreadId") or raw_target.get("threadId") or "").strip()
        project_root = str(raw_target.get("projectRoot") or "").strip()
        if not manager_thread_id or not project_root:
            return _failure(
                "each rollout target requires managerThreadId/threadId and projectRoot",
                targetIndex=index,
            )
        profile = str(raw_target.get("profile") or "generic").strip().lower()
        heartbeat = tool_manager_heartbeat_bootstrap(
            {
                "profile": profile,
                "profileFile": raw_target.get("profileFile"),
                "projectRoot": project_root,
                "managerThreadId": manager_thread_id,
                "ledgerFile": raw_target.get("ledgerFile"),
                "registryFile": raw_target.get("registryFile"),
                "heartbeatIntervalMinutes": raw_target.get("heartbeatIntervalMinutes"),
                "automationId": raw_target.get("automationId"),
                "maintenanceEveryHeartbeats": raw_target.get("maintenanceEveryHeartbeats"),
            }
        )
        if heartbeat.get("status") != "ok":
            return heartbeat
        roster = tool_manager_model_roster({"profile": profile, "profileFile": raw_target.get("profileFile")})
        worker_models = (
            [model["model"] for model in roster.get("workerModels", [])]
            if roster.get("status") == "ok"
            else list(DEFAULT_WORKER_MODELS)
        )
        notification = tool_manager_notification_packet(
            {
                "audience": raw_target.get("audience") or f"manager:{manager_thread_id}",
                "pluginVersion": plugin_version,
                "models": worker_models,
            }
        )
        target_name = str(raw_target.get("name") or raw_target.get("project") or f"manager-{index}")
        message_parts = [str(notification.get("prompt") or "").strip()]
        if release_notes:
            message_parts.append(f"Release notes: {release_notes}")
        message_parts.append(
            "Replace your existing recurring heartbeat prompt with the following updated canonical heartbeat:\n\n"
            f"{heartbeat['prompt']}"
        )
        if heartbeat.get("maintenancePolicy"):
            policy = heartbeat["maintenancePolicy"]
            message_parts.append(
                "Maintenance policy: "
                f"run {', '.join(policy['requiredTools'])} every {policy['everyHeartbeats']} heartbeats "
                f"or at least every {policy['minimumCadenceMinutes']} minutes."
            )
        rollout_message = "\n\n".join(part for part in message_parts if part)
        thread_action = tool_manager_prepare_thread_action(
            {
                "actionType": "send_message_to_thread",
                "threadId": manager_thread_id,
                "prompt": rollout_message,
                "model": raw_target.get("managerModel") or "gpt-5.4",
                "thinking": raw_target.get("thinking") or "medium",
            }
        )
        ledger_event_plan = None
        if heartbeat.get("ledgerFile"):
            ledger_event_plan = {
                "ledgerFile": heartbeat["ledgerFile"],
                "eventType": "decision",
                "payload": {
                    "kind": "plugin_rollout",
                    "plugin_version": plugin_version,
                    "manager_thread_id": manager_thread_id,
                    "heartbeat_interval_minutes": heartbeat["heartbeatIntervalMinutes"],
                    "registry_file": heartbeat["registryFile"],
                },
            }
        packet = {
            "name": target_name,
            "projectRoot": project_root,
            "profile": profile,
            "managerThreadId": manager_thread_id,
            "heartbeat": heartbeat,
            "notification": notification,
            "threadAction": thread_action,
            "ledgerEventPlan": ledger_event_plan,
        }
        rollout_packets.append(packet)
        action_queue.append(
            {
                "project": target_name,
                "threadId": manager_thread_id,
                "recommendedAction": "send_rollout_packet_and_update_heartbeat",
                "ledgerFile": heartbeat["ledgerFile"],
            }
        )
    return _success(
        pluginVersion=plugin_version,
        releaseNotes=release_notes or None,
        targetCount=len(rollout_packets),
        rolloutPackets=rollout_packets,
        actionQueue=action_queue,
        rolloutChecklist=[
            "Send each rollout packet to the target manager thread.",
            "Update the live recurring heartbeat automation prompt with the generated heartbeat text.",
            "Append the generated decision ledger event after each automation/thread update succeeds.",
            "Re-run manager_environment_health and manager_operational_audit after rollout to confirm the manager is healthy.",
        ],
    )


def tool_manager_rollout_execution_bundle(args: dict[str, Any]) -> dict[str, Any]:
    rollout = tool_manager_automation_rollout_helper(args)
    if rollout.get("status") != "ok":
        return rollout
    execution_bundles: list[dict[str, Any]] = []
    for packet in rollout.get("rolloutPackets", []):
        heartbeat = packet.get("heartbeat") or {}
        thread_action = packet.get("threadAction") or {}
        action_plan = thread_action.get("actionPlan") or {}
        interval = int(heartbeat.get("heartbeatIntervalMinutes") or 5)
        automation_id = str(heartbeat.get("automationId") or "").strip()
        automation_name = f"{packet['name']} Project Manager Heartbeat"
        automation_prompt = str(heartbeat.get("prompt") or "").strip()
        update_plan = {
            "mode": "update",
            "id": automation_id,
            "kind": "heartbeat",
            "destination": "thread",
            "targetThreadId": packet["managerThreadId"],
            "name": automation_name,
            "prompt": automation_prompt,
            "rrule": _heartbeat_rrule(interval),
            "status": "ACTIVE",
        }
        create_plan = {
            "mode": "create",
            "kind": "heartbeat",
            "destination": "thread",
            "targetThreadId": packet["managerThreadId"],
            "name": automation_name,
            "prompt": automation_prompt,
            "rrule": _heartbeat_rrule(interval),
            "status": "ACTIVE",
        }
        ledger_event_plan = packet.get("ledgerEventPlan")
        ledger_append_step = None
        if ledger_event_plan:
            ledger_payload = dict(ledger_event_plan.get("payload") or {})
            ledger_payload.update(
                {
                    "rollout_target": packet["name"],
                    "automation_id": automation_id,
                    "heartbeat_prompt_hash": hashlib.sha256(automation_prompt.encode("utf-8")).hexdigest(),
                }
            )
            ledger_append_step = {
                "stepId": "record_rollout_decision",
                "tool": "manager_append_ledger_event",
                "required": True,
                "dependsOn": ["notify_manager_thread", "configure_heartbeat_automation"],
                "params": {
                    "ledgerFile": ledger_event_plan["ledgerFile"],
                    "eventType": ledger_event_plan["eventType"],
                    "projectRoot": packet["projectRoot"],
                    "managerThreadId": packet["managerThreadId"],
                    "payload": ledger_payload,
                },
                "successCriteria": "append the rollout decision only after the thread message and heartbeat automation both succeed",
            }
        steps = [
            {
                "stepId": "notify_manager_thread",
                "tool": "send_message_to_thread",
                "required": True,
                "params": action_plan,
                "successCriteria": "the rollout packet is delivered to the manager thread",
            },
            {
                "stepId": "configure_heartbeat_automation",
                "tool": "automation_update",
                "required": True,
                "dependsOn": ["notify_manager_thread"],
                "resolutionRule": "use updateParams when the heartbeat automation already exists; otherwise use createParams",
                "updateParams": update_plan,
                "createParams": create_plan,
                "successCriteria": "the recurring heartbeat is ACTIVE with the generated prompt and interval",
            },
        ]
        if ledger_append_step:
            steps.append(ledger_append_step)
        execution_bundles.append(
            {
                "name": packet["name"],
                "projectRoot": packet["projectRoot"],
                "profile": packet["profile"],
                "managerThreadId": packet["managerThreadId"],
                "automationId": automation_id,
                "heartbeatIntervalMinutes": interval,
                "registryFile": heartbeat.get("registryFile"),
                "ledgerFile": heartbeat.get("ledgerFile"),
                "steps": steps,
                "failClosedPolicy": {
                    "deliveryAndAutomationMustSucceedBeforeLedgerWrite": True,
                    "recommendedOnFailure": "re-run manager_environment_health and inspect the failing host surface before retrying rollout",
                },
                "sourceRolloutPacket": packet,
            }
        )
    return _success(
        pluginVersion=rollout.get("pluginVersion"),
        releaseNotes=rollout.get("releaseNotes"),
        targetCount=len(execution_bundles),
        executionBundles=execution_bundles,
        rolloutChecklist=[
            "Run notify_manager_thread first for each bundle.",
            "Update or create the heartbeat automation with the generated prompt and interval.",
            "Append the rollout decision ledger event only after both host actions succeed.",
            "If any required step fails, stop the rollout for that target and investigate transport or automation health before retrying.",
        ],
        sourceRollout=rollout,
    )


def _platform_constraints() -> dict[str, Any]:
    return {
        "windowlessWrapperRequired": True,
        "cannotRepairInMemoryCodexBinding": True,
        "freshReadbackRequiredForHealthyLane": True,
        "workerHealthRequiresAssistantEvidence": True,
        "staleSessionNeedsReloadOrFreshThread": True,
    }


def _model_usage_tier(model: str, recommended_operator_action: str) -> str:
    if model in DISABLED_WORKER_MODELS:
        return "disabled"
    if model == "deepseek-v4-flash":
        return "default_implementation" if recommended_operator_action == "continue" else "degraded_default"
    if model == "deepseek-v4-pro":
        return "escalation_implementation"
    if model.startswith("gpt-5."):
        return "manager_or_final_review"
    return "allowed_fallback"


def _build_model_transport_health(
    *,
    profile_name: str,
    settings: dict[str, Any],
    roster: dict[str, Any],
    install_state: dict[str, Any],
    wrapper_smoke: dict[str, Any],
    log_summary: dict[str, Any],
    orphan_diagnostics: dict[str, Any],
    chat_process_registry_health: dict[str, Any] | None = None,
    evidence_file: Any = None,
) -> dict[str, Any]:
    recommended_operator_action = _recommended_operator_action(
        wrapper_smoke,
        install_state,
        log_summary,
        orphan_diagnostics,
        chat_process_registry_health,
    )
    stale_loaded_session_risk = bool(install_state.get("staleLoadedSessionSuspicion"))
    fresh_thread_viable = wrapper_smoke.get("status") == "ok" and install_state.get("cacheVersionMatchesSource", True)
    read_thread_safe = _effective_thread_read_safe(chat_process_registry_health, orphan_diagnostics)
    follow_up_viable = (
        fresh_thread_viable
        and read_thread_safe
        and not stale_loaded_session_risk
        and recommended_operator_action == "continue"
    )
    pressure = _model_pressure_summary({"evidenceFile": evidence_file})
    pressure_models = pressure.get("models") or {}
    catalog = _canonical_catalog_by_slug(include_disabled=True)
    models: list[dict[str, Any]] = []
    seen_models: set[str] = set()
    default_worker_model = _normalize_model(settings.get("defaultWorkerModel"), "deepseek-v4-flash")
    senior_worker_model = _normalize_model(settings.get("seniorWorkerModel"), "deepseek-v4-pro")
    for entry in (roster.get("managerModels") or []) + (roster.get("workerModels") or []):
        model = str(entry.get("model") or "")
        if not model or model in seen_models:
            continue
        seen_models.add(model)
        catalog_entry = catalog.get(model) or {}
        disabled_reason = DISABLED_WORKER_MODELS.get(model) or catalog_entry.get("disabledReason")
        pressure_row = pressure_models.get(model, {})
        reliability_status = str(pressure_row.get("reliabilityStatus") or "healthy")
        tool_loop_reliability = "degraded" if reliability_status in {"degraded", "single_turn_only"} else str(catalog_entry.get("toolLoopReliability") or entry.get("toolLoopReliability") or "unknown")
        if disabled_reason:
            fresh_thread_viability = "disabled"
            follow_up_turn_viability = "disabled"
        else:
            fresh_thread_viability = "viable" if fresh_thread_viable else "degraded"
            if reliability_status == "single_turn_only":
                follow_up_turn_viability = "single_turn_only"
            elif follow_up_viable and reliability_status == "healthy":
                follow_up_turn_viability = "viable"
            else:
                follow_up_turn_viability = "risky"
        fallback_model = None
        if model == default_worker_model:
            fallback_model = senior_worker_model if senior_worker_model != model else None
        elif model in {senior_worker_model, "glm-5.2", "kimi-k2.7-code", "mimo-v2.5"}:
            fallback_model = default_worker_model
        recommended_usage_tier = _model_usage_tier(model, recommended_operator_action)
        if reliability_status in {"degraded", "single_turn_only"} and model == default_worker_model:
            recommended_usage_tier = "degraded_default"
        models.append(
            {
                "model": model,
                "role": entry.get("role"),
                "provider": catalog_entry.get("provider"),
                "transportRoute": catalog_entry.get("transportRoute"),
                "freshThreadViability": fresh_thread_viability,
                "followUpTurnViability": follow_up_turn_viability,
                "transportMode": "native_create_thread.model",
                "staleSessionRisk": stale_loaded_session_risk,
                "recommendedUsageTier": recommended_usage_tier,
                "toolLoopReliability": tool_loop_reliability,
                "knownFailureModes": catalog_entry.get("knownFailureModes") or [],
                "fallbackModel": fallback_model,
                "operatorActionIfDegraded": "route_to_fallback_or_run_fresh_canary",
                "disabledReason": disabled_reason,
                "parseFailures": int(pressure_row.get("parseFailures") or 0),
                "rawTextFallbacks": int(pressure_row.get("rawTextFallbacks") or 0),
                "commentSanitizerInterventions": int(pressure_row.get("commentSanitizerInterventions") or 0),
            }
        )
    return {
        "profile": profile_name,
        "freshWrapperSmokeViable": fresh_thread_viable,
        "followUpTurnViability": "viable" if follow_up_viable else "risky",
        "sourceCache": {
            "currentVersion": install_state.get("currentVersion"),
            "sourceVersion": install_state.get("sourceVersion"),
            "activeCacheVersion": install_state.get("activeCacheVersion"),
            "cacheVersionMatchesSource": install_state.get("cacheVersionMatchesSource", True),
        },
        "staleLoadedSessionSuspicion": stale_loaded_session_risk,
        "recentLogSummary": log_summary,
        "wrapperSmoke": wrapper_smoke,
        "chatProcessRegistry": chat_process_registry_health or _chat_process_registry_health(),
        "transportMode": "native_create_thread.model",
        "threadReadSafe": read_thread_safe,
        "recommendedOperatorAction": recommended_operator_action,
        "models": models,
        "defaultWorkerModel": default_worker_model,
        "seniorWorkerModel": senior_worker_model,
        "pressureSummaryPath": pressure.get("path"),
    }


def tool_manager_model_transport_health(args: dict[str, Any]) -> dict[str, Any]:
    profile_name, settings, profile_error = _profile_settings_from_args(args)
    roster = tool_manager_model_roster({"profile": profile_name, "profileFile": args.get("profileFile")})
    install_state = _plugin_install_state()
    wrapper_smoke = _run_wrapper_smoke(timeout_seconds=int(args.get("wrapperSmokeTimeoutSeconds") or 10))
    log_summary = _mcp_log_summary(limit=int(args.get("logTailLines") or 30))
    orphan_diagnostics = _project_manager_mcp_diagnostics(scan_live=bool(args.get("scanOrphanProcesses", True)))
    chat_process_registry_health = _chat_process_registry_health()
    transport_health = _build_model_transport_health(
        profile_name=profile_name,
        settings=settings,
        roster=roster,
        install_state=install_state,
        wrapper_smoke=wrapper_smoke,
        log_summary=log_summary,
        orphan_diagnostics=orphan_diagnostics,
        chat_process_registry_health=chat_process_registry_health,
        evidence_file=args.get("evidenceFile"),
    )
    return _success(
        profile=profile_name,
        profileError=profile_error,
        modelTransportHealth=transport_health,
        platformConstraints=_platform_constraints(),
        recommendedOperatorAction=transport_health["recommendedOperatorAction"],
    )


def tool_manager_worker_canary(args: dict[str, Any]) -> dict[str, Any]:
    worker_id = str(args.get("workerId") or "").strip()
    if not worker_id:
        return _failure("workerId is required")
    try:
        registry_path, registry = _read_registry(args.get("registryFile"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("registry read failed", reason=str(exc))
    worker = registry.get("workers", {}).get(worker_id)
    if not isinstance(worker, dict):
        return _failure("worker not found", workerId=worker_id)
    now = _parse_time(args.get("now")) or datetime.now(timezone.utc)
    stale_after_minutes = int(args.get("staleAfterMinutes") or 30)
    classified = _classify_worker(worker, now, stale_after_minutes)
    return _success(
        registryFile=str(registry_path),
        workerId=worker_id,
        canary=classified,
        recommendedAction=_worker_recommended_action(classified),
        alive=classified["attention"] not in {"dead_reference"},
    )


def tool_manager_lane_health_from_readback(args: dict[str, Any]) -> dict[str, Any]:
    worker_id = str(args.get("workerId") or "").strip()
    if not worker_id:
        return _failure("workerId is required")
    try:
        registry_path, registry = _read_registry(args.get("registryFile"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("registry read failed", reason=str(exc))
    worker = _normalize_registry_worker(registry.get("workers", {}).get(worker_id, {}))
    delivery_visible = bool(args.get("hasVisibleTurn") or worker.get("deliveryVisible"))
    assistant_authored = bool(args.get("assistantAuthored") or args.get("workerAcknowledged"))
    worker_final_detected = bool(args.get("workerFinalDetected"))
    blocked_detected = bool(args.get("blockedDetected"))
    dead_reference = bool(args.get("deadReference"))
    stale_readback = bool(args.get("staleReadback"))
    thread_state = str(args.get("threadState") or worker.get("status") or "").strip().lower()
    readback_summary = str(args.get("readbackSummary") or "").strip()
    visible_turn_at = str(args.get("visibleTurnAt") or _now_iso8601())
    acknowledged_turn_id = str(args.get("acknowledgedTurnId") or "").strip() or None
    acknowledged_message_id = str(args.get("acknowledgedMessageId") or "").strip() or None
    delivery_turn_id = str(args.get("deliveryTurnId") or args.get("observedTurnId") or "").strip() or None
    delivery_message_id = str(args.get("deliveryMessageId") or args.get("observedMessageId") or "").strip() or None
    delivery_verification_evidence = str(
        args.get("deliveryVerificationEvidence") or readback_summary or ""
    ).strip() or None
    lower_summary = readback_summary.lower()
    if not blocked_detected and any(token in lower_summary for token in ("blocked", "blocker", "error", "failed")):
        blocked_detected = True
    if not worker_final_detected and any(token in lower_summary for token in ('"next_recommended_action"', '"assignment_id"', "worker final")):
        worker_final_detected = True
    if dead_reference or thread_state in {"dead_reference", "unreadable", "historical_dead"}:
        lane_health = "dead_reference"
        quiet_heartbeat_allowed = False
    elif blocked_detected or thread_state in {"blocked", "failed", "error", "interrupted"}:
        lane_health = "blocked"
        quiet_heartbeat_allowed = False
    elif worker_final_detected or thread_state in COMPLETED_WORKER_STATUSES:
        lane_health = "finaled"
        quiet_heartbeat_allowed = False
    elif stale_readback:
        lane_health = "stale"
        quiet_heartbeat_allowed = False
    elif delivery_visible and not assistant_authored:
        lane_health = "silent_after_delivery"
        quiet_heartbeat_allowed = False
    elif assistant_authored and any(token in lower_summary for token in ("progress", "implemented", "updated", "changed", "fixed")):
        lane_health = "progressing"
        quiet_heartbeat_allowed = True
    elif assistant_authored:
        lane_health = "acknowledged"
        quiet_heartbeat_allowed = True
    else:
        lane_health = "stale"
        quiet_heartbeat_allowed = False
    recommended_action = {
        "dead_reference": f"replace_dead_reference_worker:{worker_id}",
        "blocked": f"read_or_recover_blocked_worker:{worker_id}",
        "finaled": f"review_worker_final:{worker_id}",
        "stale": f"read_or_reassign_stale_worker:{worker_id}",
        "silent_after_delivery": f"recover_silent_lane:{worker_id}",
        "acknowledged": f"monitor_acknowledged_lane:{worker_id}",
        "progressing": f"no_interrupt_active_worker:{worker_id}",
    }[lane_health]
    write_registry = bool(args.get("writeRegistry"))
    registry_result = None
    if write_registry:
        registry_status = "active"
        progress_state = lane_health
        if lane_health == "finaled":
            registry_status = "completed_needs_manager_review"
        elif lane_health == "blocked":
            registry_status = "blocked"
        elif lane_health == "dead_reference":
            registry_status = "dead_reference"
        registry_result = tool_manager_update_worker_registry(
            {
                "registryFile": str(registry_path),
                "workerId": worker_id,
                "threadId": worker.get("thread_id") or worker.get("threadId"),
                "assignmentId": worker.get("assignment_id") or worker.get("assignmentId"),
                "model": worker.get("model"),
                "status": registry_status,
                "deliveryVisible": delivery_visible,
                "deliveryVerified": delivery_visible,
                "deliveryTurnId": delivery_turn_id if delivery_visible else worker.get("deliveryTurnId"),
                "deliveryMessageId": delivery_message_id if delivery_visible else worker.get("deliveryMessageId"),
                "deliveryVerificationEvidence": (
                    delivery_verification_evidence if delivery_visible else worker.get("deliveryVerificationEvidence")
                ),
                "workerAcknowledged": assistant_authored or lane_health in {"finaled", "blocked"},
                "acknowledgedAt": visible_turn_at if assistant_authored or lane_health in {"finaled", "blocked"} else None,
                "acknowledgedTurnId": acknowledged_turn_id,
                "acknowledgedMessageId": acknowledged_message_id,
                "lastVisibleTurnAt": visible_turn_at if delivery_visible else worker.get("lastVisibleTurnAt"),
                "lastVerifiedHealthyAt": visible_turn_at if lane_health in {"acknowledged", "progressing", "finaled"} else worker.get("lastVerifiedHealthyAt"),
                "progressState": progress_state,
                "evidenceSource": "verified_readback",
                "lastReadbackSummary": readback_summary or worker.get("lastReadbackSummary"),
                "updatedAt": visible_turn_at,
                "packetRole": worker.get("packetRole") or "implementer",
            }
        )
        if registry_result.get("status") != "ok":
            return registry_result
    return _success(
        registryFile=str(registry_path),
        workerId=worker_id,
        laneHealth=lane_health,
        quietHeartbeatAllowed=quiet_heartbeat_allowed,
        recommendedAction=recommended_action,
        deliveryVisible=delivery_visible,
        workerAcknowledged=assistant_authored or lane_health in {"finaled", "blocked"},
        visibleTurnAt=visible_turn_at if delivery_visible else None,
        deliveryTurnId=delivery_turn_id if delivery_visible else worker.get("deliveryTurnId"),
        deliveryMessageId=delivery_message_id if delivery_visible else worker.get("deliveryMessageId"),
        deliveryVerificationEvidence=delivery_verification_evidence if delivery_visible else worker.get("deliveryVerificationEvidence"),
        acknowledgedTurnId=acknowledged_turn_id,
        acknowledgedMessageId=acknowledged_message_id,
        readbackSummary=readback_summary[:300] if readback_summary else None,
        registryUpdate=registry_result,
    )


def tool_manager_registry_reconcile(args: dict[str, Any]) -> dict[str, Any]:
    try:
        registry_path, registry = _read_registry(args.get("registryFile"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("registry read failed", reason=str(exc))
    now = _parse_time(args.get("recordedAt")) or datetime.now(timezone.utc)
    stale_after_minutes = int(args.get("staleAfterMinutes") or 30)
    write_changes = bool(args.get("writeChanges"))
    archive_candidates: list[dict[str, Any]] = []
    reconciled: list[dict[str, Any]] = []
    changed_workers: list[str] = []
    for worker_id, raw_worker in list((registry.get("workers") or {}).items()):
        worker = _normalize_registry_worker(raw_worker)
        classified = _classify_worker(worker, now, stale_after_minutes)
        contradiction_reasons: list[str] = []
        if str(worker.get("status") or "").strip().lower() in ACTIVE_WORKER_STATUSES and worker.get("evidenceSource") not in ALLOWED_EVIDENCE_SOURCES:
            contradiction_reasons.append("active lane missing allowed evidenceSource")
        if classified["attention"] == "silent_after_delivery":
            contradiction_reasons.append("delivery visible without assistant-authored acknowledgment")
        if classified["attention"] == "unverified_dispatch":
            contradiction_reasons.append("lane never achieved delivery visibility")
        if classified["attention"] == "stale":
            contradiction_reasons.append("lane is stale by timing")
        if classified["attention"] in {"dead_reference", "needs_review"} or worker.get("replacementOfThreadId"):
            archive_candidates.append(
                {
                    "workerId": worker_id,
                    "reason": "dead_or_replaced_or_completed" if classified["attention"] != "stale" else "silent_stale_lane",
                }
            )
        elif classified["attention"] == "silent_after_delivery" and classified.get("minutesSinceProgress") is not None and int(classified["minutesSinceProgress"]) >= stale_after_minutes:
            archive_candidates.append({"workerId": worker_id, "reason": "silent_stale_lane"})
        if contradiction_reasons and write_changes:
            worker["evidenceSource"] = "registry_reconcile"
            worker["progressState"] = classified["attention"]
            worker["staleConfidence"] = max(float(worker.get("staleConfidence") or 0.0), 0.8)
            worker["updated_at"] = now.isoformat().replace("+00:00", "Z")
            registry["workers"][worker_id] = worker
            changed_workers.append(worker_id)
        reconciled.append(
            {
                "workerId": worker_id,
                "attention": classified["attention"],
                "recommendedAction": _worker_recommended_action(classified),
                "contradictionReasons": contradiction_reasons,
                "archiveCandidate": next((item for item in archive_candidates if item["workerId"] == worker_id), None),
            }
        )
    if write_changes:
        registry["updated_at"] = now.isoformat().replace("+00:00", "Z")
        _write_registry(registry_path, registry)
    return _success(
        registryFile=str(registry_path),
        recordedAt=now.isoformat().replace("+00:00", "Z"),
        reconciled=reconciled,
        archiveCandidates=archive_candidates,
        changedWorkers=changed_workers,
        contradictionCount=sum(1 for item in reconciled if item["contradictionReasons"]),
    )


def tool_manager_accept_worker_final_and_plan_next(args: dict[str, Any]) -> dict[str, Any]:
    try:
        worker_final, worker_final_input = _coerce_worker_final_from_args(args)
    except (ValueError, json.JSONDecodeError) as exc:
        return _failure(str(exc))
    missing = _missing_fields(worker_final, REQUIRED_WORKER_FINAL_FIELDS)
    if missing:
        return _failure("missing required worker-final fields", missing=missing)
    recorded_at = str(args.get("recordedAt") or _now_iso8601())
    assignment_id = str(worker_final["assignment_id"]).strip()
    worker_id = str(args.get("workerId") or assignment_id or "worker").strip()
    registry_worker: dict[str, Any] = {}
    if args.get("registryFile"):
        try:
            _, registry = _read_registry(args.get("registryFile"))
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            return _failure("registry read failed", reason=str(exc))
        registry_worker = _normalize_registry_worker(registry.get("workers", {}).get(worker_id, {}))
    packet_role = str(args.get("packetRole") or registry_worker.get("packetRole") or "implementer").strip().lower()
    if packet_role not in PACKET_ROLES:
        return _failure("unknown packetRole", packetRole=packet_role, knownPacketRoles=sorted(PACKET_ROLES))
    status = str(worker_final["status"]).strip().lower()
    blocked = bool(worker_final.get("blockers")) or status in {"blocked", "failed", "error", "interrupted"}
    registry_status = "blocked" if blocked else ("completed_needs_manager_review" if packet_role == "code_quality_reviewer" else "idle_completed_needs_next_dispatch")
    registry_result = None
    if args.get("registryFile"):
        registry_result = tool_manager_update_worker_registry(
            {
                "registryFile": args["registryFile"],
                "workerId": worker_id,
                "threadId": registry_worker.get("thread_id") or registry_worker.get("threadId"),
                "assignmentId": assignment_id,
                "model": registry_worker.get("model"),
                "status": registry_status,
                "deliveryVisible": True,
                "deliveryVerified": True,
                "workerAcknowledged": True,
                "acknowledgedAt": recorded_at,
                "lastVisibleTurnAt": recorded_at,
                "lastVerifiedHealthyAt": recorded_at,
                "progressState": "finaled" if not blocked else "blocked",
                "evidenceSource": "worker_final",
                "updatedAt": recorded_at,
                "packetRole": packet_role,
            }
        )
        if registry_result.get("status") != "ok":
            return registry_result
    ledger_result = None
    if args.get("ledgerFile"):
        ledger_payload = dict(worker_final)
        ledger_payload["packetRole"] = packet_role
        ledger_payload["acceptedAt"] = recorded_at
        ledger_result = tool_manager_append_ledger_event(
            {
                "ledgerFile": args["ledgerFile"],
                "eventType": "worker_final",
                "eventId": args.get("eventId") or f"worker-final-{worker_id}-{recorded_at}",
                "recordedAt": recorded_at,
                "assignmentId": assignment_id,
                "threadId": registry_worker.get("thread_id") or registry_worker.get("threadId"),
                "model": registry_worker.get("model"),
                "payload": ledger_payload,
            }
        )
        if ledger_result.get("status") != "ok":
            return ledger_result
    next_phase = "recover_worker_or_replace"
    next_role = None
    if not blocked:
        if packet_role == "implementer":
            next_phase = "spec_review"
            next_role = "spec_reviewer"
        elif packet_role == "spec_reviewer":
            next_phase = "code_quality_review"
            next_role = "code_quality_reviewer"
        else:
            next_phase = "manager_acceptance"
    dispatch_recommendation = None
    if next_role:
        model_selection = tool_manager_select_worker_model(
            {
                "profile": args.get("profile") or "generic",
                "profileFile": args.get("profileFile"),
                "packetRole": next_role,
                "assignmentRisk": args.get("assignmentRisk") or "routine",
                "packetShape": args.get("packetShape") or "narrow",
                "architectureSensitive": bool(args.get("architectureSensitive")),
            }
        )
        if model_selection.get("status") == "ok":
            dispatch_recommendation = {
                "packetRole": next_role,
                "workerModel": model_selection["workerModel"],
                "rationale": model_selection["rationale"],
            }
    return _success(
        workerId=worker_id,
        assignmentId=assignment_id,
        packetRole=packet_role,
        accepted=True,
        blocked=blocked,
        recordedAt=recorded_at,
        registryUpdate=registry_result,
        ledgerUpdate=ledger_result,
        nextPhase=next_phase,
        nextRecommendedAction=str(worker_final["next_recommended_action"]),
        dispatchRecommendation=dispatch_recommendation,
        summary=str(worker_final["summary"])[:300],
        workerFinalInput=worker_final_input,
    )


def tool_manager_worker_packet_contract(args: dict[str, Any]) -> dict[str, Any]:
    packet_role = str(args.get("packetRole") or "implementer").strip().lower()
    if packet_role not in PACKET_ROLES:
        return _failure("unknown packetRole", packetRole=packet_role, knownPacketRoles=sorted(PACKET_ROLES))
    model = _normalize_model(args.get("workerModel"), "deepseek-v4-flash")
    entry = _find_catalog_entry(model, include_disabled=True) or {}
    return _success(
        packetRole=packet_role,
        workerModel=model,
        roleContract=_packet_role_contract(packet_role),
        expectedEvidence=_packet_expected_evidence(packet_role),
        recommendedReasoningLevel=_thinking_for_model(model, args.get("thinking")),
        allowedTaskSize=_packet_allowed_scope(packet_role),
        escalationBoundary=_packet_escalation_boundary(packet_role),
        modelGuidance=_catalog_entry_model_guidance(entry) if entry else "Use bounded, evidence-first execution and return a strict worker final.",
        enabled=bool(entry.get("enabled", True)),
        disabledReason=entry.get("disabledReason"),
    )


def tool_manager_successor_packet_plan(args: dict[str, Any]) -> dict[str, Any]:
    try:
        worker_final, worker_final_input = _coerce_worker_final_from_args(args)
    except (ValueError, json.JSONDecodeError) as exc:
        return _failure(str(exc))
    missing = _missing_fields(worker_final, REQUIRED_WORKER_FINAL_FIELDS)
    if missing:
        return _failure("missing required worker-final fields", missing=missing)
    packet_role = str(args.get("packetRole") or "implementer").strip().lower()
    if packet_role not in PACKET_ROLES:
        return _failure("unknown packetRole", packetRole=packet_role, knownPacketRoles=sorted(PACKET_ROLES))
    blocked = bool(worker_final.get("blockers")) or str(worker_final.get("status") or "").lower() in {"blocked", "failed", "error"}
    if blocked:
        return _success(
            nextAction="manager_takeover_or_replacement",
            successorPacketRole=None,
            reason="worker final reported blockers or a failed status",
            workerFinalStatus=worker_final.get("status"),
            workerFinalInput=worker_final_input,
        )
    if packet_role == "implementer":
        successor = "spec_reviewer"
    elif packet_role == "spec_reviewer":
        successor = "code_quality_reviewer"
    elif packet_role == "code_quality_reviewer":
        successor = None
    else:
        successor = "implementer"
    if successor:
        model = tool_manager_select_worker_model(
            {
                "profile": args.get("profile") or "generic",
                "profileFile": args.get("profileFile"),
                "packetRole": successor,
                "assignmentRisk": args.get("assignmentRisk") or "routine",
                "packetShape": args.get("packetShape") or "narrow",
                "architectureSensitive": bool(args.get("architectureSensitive")),
            }
        )
        return _success(
            nextAction="dispatch_successor",
            successorPacketRole=successor,
            workerModel=model.get("workerModel") if model.get("status") == "ok" else None,
            modelSelection=model,
            reason=f"{packet_role} final accepted; next required packet is {successor}",
            workerFinalInput=worker_final_input,
        )
    return _success(
        nextAction="wait",
        successorPacketRole=None,
        reason="review chain is complete; manager should perform final acceptance or wait for new scope",
        workerFinalInput=worker_final_input,
    )


def tool_manager_recent_events(args: dict[str, Any]) -> dict[str, Any]:
    return _success(
        mcp=_mcp_log_summary(limit=int(args.get("limit") or args.get("logTailLines") or 30)),
        proxy=_proxy_log_model_events(Path(str(args.get("proxyLogFile"))) if args.get("proxyLogFile") else None),
        modelPressure=_model_pressure_summary({"evidenceFile": args.get("evidenceFile")}),
        exportHashes=_export_hashes(),
    )


def tool_manager_crash_forensics_pack(args: dict[str, Any]) -> dict[str, Any]:
    policy_packet = tool_manager_model_policy_packet({"profile": args.get("profile") or "generic", "profileFile": args.get("profileFile")})
    return _success(
        pluginVersion=PLUGIN_VERSION,
        installState=_plugin_install_state(),
        wrapperPath=WINDOWLESS_STDIO_WRAPPER_COMMAND,
        recentEvents=tool_manager_recent_events(args),
        exportHashes=_export_hashes(),
        activeModelPolicy={
            "defaultWorkerModel": policy_packet.get("defaultWorkerModel"),
            "escalationWorkerModel": policy_packet.get("escalationWorkerModel"),
            "disabledModels": policy_packet.get("disabledModels"),
            "workerModels": policy_packet.get("workerModels"),
        },
        modelExportHealth=tool_manager_model_export_health({}),
    )


def _readiness_from_audit(audit: dict[str, Any], health: dict[str, Any] | None = None) -> dict[str, Any]:
    attention = audit.get("workerAttentionCounts") or {}
    health = health or {}
    transport = 100 if health.get("overallStatus") in {None, "healthy"} else 60
    model_policy = 100 if (health.get("modelExportHealth") or {}).get("overallStatus") in {None, "healthy"} else 70
    registry_quality = max(0, 100 - int(attention.get("dead_reference") or 0) * 35 - int(attention.get("unknown") or 0) * 15)
    ledger_freshness = 100 if audit.get("ledgerSummary", {}).get("eventCount") else 70
    worker_progress = max(
        0,
        100
        - int(attention.get("dead_reference") or 0) * 50
        - int(attention.get("blocked") or 0) * 30
        - int(attention.get("silent_after_delivery") or 0) * 25
        - int(attention.get("stale") or 0) * 20
        - int(attention.get("unverified_dispatch") or 0) * 25,
    )
    automation = 100 if not any(attention.get(key) for key in ("dead_reference", "blocked", "silent_after_delivery", "stale", "unverified_dispatch")) else 50
    dimensions = {
        "transportHealth": transport,
        "modelPolicyHealth": model_policy,
        "registryEvidenceQuality": registry_quality,
        "ledgerFreshness": ledger_freshness,
        "workerProgress": worker_progress,
        "automationReadiness": automation,
    }
    return {"overallScore": int(sum(dimensions.values()) / len(dimensions)), "dimensions": dimensions}


def tool_manager_project_readiness_score(args: dict[str, Any]) -> dict[str, Any]:
    audit = tool_manager_operational_audit(args)
    if audit.get("status") != "ok":
        return audit
    health = tool_manager_environment_health(args) if args.get("includeEnvironmentHealth") else None
    readiness = _readiness_from_audit(audit, health)
    return _success(
        project=args.get("name") or args.get("project") or "project",
        overallReadiness=readiness["overallScore"],
        readinessScore=readiness["overallScore"],
        dimensions=readiness["dimensions"],
        quietHeartbeatSafe=readiness["dimensions"]["automationReadiness"] >= 85,
        actionQueue=audit.get("actionQueue") or [],
        workerAttentionCounts=audit.get("workerAttentionCounts") or {},
    )


def tool_manager_next_best_action(args: dict[str, Any]) -> dict[str, Any]:
    projects = args.get("projects")
    if not isinstance(projects, list):
        return _failure("projects must be an array")
    candidates: list[dict[str, Any]] = []
    for index, project in enumerate(projects, start=1):
        if not isinstance(project, dict):
            continue
        project_args = dict(project)
        project_args.setdefault("name", project.get("name") or project.get("project") or f"project-{index}")
        readiness = tool_manager_project_readiness_score(project_args)
        if readiness.get("status") != "ok":
            candidates.append({"project": project_args["name"], "priority": 100, "action": "repair_project_inputs", "readiness": readiness})
            continue
        queue = readiness.get("actionQueue") or []
        top = queue[0] if queue else {}
        priority = 100 - int(readiness.get("readinessScore") or 0) + int(top.get("severity") or 0) * 10
        candidates.append(
            {
                "project": project_args["name"],
                "priority": priority,
                "action": top.get("recommendedAction") or ("continue quiet heartbeat" if readiness.get("quietHeartbeatSafe") else "inspect project health"),
                "readinessScore": readiness.get("readinessScore"),
                "worker": top.get("worker"),
            }
        )
    candidates.sort(key=lambda item: (-int(item.get("priority") or 0), str(item.get("project") or "")))
    return _success(nextBestAction=candidates[0] if candidates else None, rankedActions=candidates)


def tool_manager_operator_digest(args: dict[str, Any]) -> dict[str, Any]:
    projects = args.get("projects")
    if not isinstance(projects, list):
        return _failure("projects must be an array")
    actions = tool_manager_next_best_action({"projects": projects})
    if actions.get("status") != "ok":
        return actions
    lines = ["# Project Manager Operator Digest", ""]
    for action in actions.get("rankedActions") or []:
        lines.append(
            f"- {action.get('project')}: readiness {action.get('readinessScore', 'unknown')}; next action: {action.get('action')}"
        )
    return _success(markdown="\n".join(lines), rankedActions=actions.get("rankedActions") or [])


def tool_manager_release_checklist(args: dict[str, Any]) -> dict[str, Any]:
    source_root = str(args.get("sourceRoot") or SOURCE_PLUGIN_ROOT)
    cache_root = str(args.get("cacheRoot") or (CACHE_PLUGIN_BASE / (_active_cache_version() or "")))
    python_exe = str(args.get("pythonExe") or "python")
    scripts_root = SOURCE_PLUGIN_ROOT / "scripts"
    gates = {
        "sourcePytest": {"command": f'{python_exe} -m pytest "{source_root}\\tests\\test_project_manager_mcp_server.py" -q'},
        "cachedPytest": {"command": f'{python_exe} -m pytest "{cache_root}\\tests\\test_project_manager_mcp_server.py" -q'},
        "wrapperSmoke": {"command": f'powershell -NoProfile -ExecutionPolicy Bypass -File "{scripts_root}\\Test-ProjectManagerPlugin.ps1" -SourceRoot "{source_root}" -CacheRoot "{cache_root}" -PythonExe "{python_exe}"'},
        "exportHealth": {"command": "manager_model_export_health"},
        "atomicHostActionSmoke": {"command": "manager_atomic_dispatch_prepare with smoke inputs returns create_thread/read_thread hostActions"},
        "transactionJournalSmoke": {"command": "manager_transaction_journal_record + manager_transaction_resume_plan with smoke hostResults returns read_thread"},
        "proxyExportValidation": {"command": f'powershell -NoProfile -ExecutionPolicy Bypass -File "{scripts_root}\\Test-ProjectManagerProxyExports.ps1" -PluginRoot "{source_root}"'},
        "disabledModelRouteCheck": {"command": "verify qwen3.7-plus is absent from proxy model list and disabled in runtime export"},
        "cacheSync": {"command": f'powershell -NoProfile -ExecutionPolicy Bypass -File "{scripts_root}\\Sync-ProjectManagerPlugin.ps1" -SourceRoot "{source_root}" -CacheRoot "{cache_root}"'},
    }
    return _success(pluginVersion=PLUGIN_VERSION, gates=gates, scripts={name: gate["command"] for name, gate in gates.items()})


def tool_manager_thread_supervisor_plan(args: dict[str, Any]) -> dict[str, Any]:
    read_thread_guard = _read_thread_guard_failure()
    if read_thread_guard:
        return read_thread_guard
    try:
        registry_path, registry = _read_registry(args.get("registryFile"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("registry read failed", reason=str(exc))
    transaction_id = str(args.get("transactionId") or _transaction_id("thread_supervision", args))
    max_workers = int(args.get("maxWorkers") or 10)
    host_actions: list[dict[str, Any]] = []
    for worker_id, raw_worker in list((registry.get("workers") or {}).items())[:max_workers]:
        worker = _normalize_registry_worker(raw_worker)
        thread_id = str(worker.get("thread_id") or "").strip()
        if not thread_id:
            continue
        host_actions.append(
            {
                "tool": "read_thread",
                "resultKey": f"read_{worker_id}",
                "required": True,
                "workerId": worker_id,
                "arguments": {"threadId": thread_id, "turnLimit": int(args.get("turnLimit") or 8)},
            }
        )
    return _success(
        transactionId=transaction_id,
        transactionType="thread_supervision",
        registryFile=str(registry_path),
        hostActions=host_actions,
        verificationRules={
            "assistantEvidenceRequiredForHealthy": True,
            "thinkingWithoutAssistantTurnIsAttention": True,
            "deadReferenceIfReadbackFails": True,
        },
        pendingWrites={"forbiddenUntilFinalize": True, "ledgerFile": args.get("ledgerFile")},
    )


def _supervisor_lane_class(worker: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    if result.get("success") is not True:
        return "dead_reference"
    if result.get("workerFinalDetected"):
        return "finaled"
    if result.get("assistantAuthored"):
        return "progressing"
    if result.get("thinking"):
        return "silent_after_delivery" if worker.get("deliveryVisible") else "stale"
    if worker.get("deliveryVisible") and not worker.get("workerAcknowledged"):
        return "silent_after_delivery"
    return "stale"


def tool_manager_thread_supervisor_finalize(args: dict[str, Any]) -> dict[str, Any]:
    try:
        registry_path, registry = _read_registry(args.get("registryFile"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _failure("registry read failed", reason=str(exc))
    transaction_id = str(args.get("transactionId") or _transaction_id("thread_supervision", args))
    host_results = _host_results(args)
    lane_findings: list[dict[str, Any]] = []
    quiet_allowed = True
    for worker_id, raw_worker in list((registry.get("workers") or {}).items()):
        worker = _normalize_registry_worker(raw_worker)
        result = host_results.get(f"read_{worker_id}")
        if not isinstance(result, dict):
            continue
        lane_class = _supervisor_lane_class(worker, result)
        checked_at = str(result.get("visibleTurnAt") or _now_iso8601())
        quiet_allowed = quiet_allowed and lane_class in {"progressing", "finaled"}
        lane_findings.append(
            {
                "workerId": worker_id,
                "threadId": worker.get("thread_id"),
                "laneClass": lane_class,
                "readbackSummary": result.get("readbackSummary"),
            }
        )
        update = tool_manager_update_worker_registry(
            {
                "registryFile": str(registry_path),
                "workerId": worker_id,
                "threadId": worker.get("thread_id"),
                "assignmentId": worker.get("assignment_id"),
                "status": "active" if lane_class in {"progressing", "finaled"} else lane_class,
                "deliveryVisible": bool(worker.get("deliveryVisible") or result.get("success") is True),
                "workerAcknowledged": lane_class in {"progressing", "finaled"},
                "lastVisibleTurnAt": checked_at,
                "lastVerifiedHealthyAt": checked_at if lane_class in {"progressing", "finaled"} else None,
                "progressState": lane_class,
                "evidenceSource": "registry_reconcile" if lane_class in {"progressing", "finaled"} else worker.get("evidenceSource"),
                "lastReadbackSummary": result.get("readbackSummary"),
                "activeTransactionId": transaction_id,
                "lastTransactionStatus": "supervisor_ok" if lane_class in {"progressing", "finaled"} else "supervisor_attention",
                "lastSupervisorCheckAt": checked_at,
                "updatedAt": checked_at,
            }
        )
        if update.get("status") != "ok":
            return update
    supervisor_event = _append_transaction_event(
        args,
        "supervisor_check",
        {
            "transactionId": transaction_id,
            "laneFindings": lane_findings,
            "quietHeartbeatAllowed": quiet_allowed,
            "recordedAt": _now_iso8601(),
        },
    )
    return _success(
        transactionId=transaction_id,
        laneFindings=lane_findings,
        quietHeartbeatAllowed=quiet_allowed,
        ledgerEvent=supervisor_event,
    )


def tool_manager_heartbeat_automation_plan(args: dict[str, Any]) -> dict[str, Any]:
    interval = int(args.get("heartbeatIntervalMinutes") or 5)
    transaction_id = str(args.get("transactionId") or _transaction_id("heartbeat_automation", args))
    automation_id = str(args.get("automationId") or "").strip()
    prompt = str(args.get("prompt") or "Run project-manager heartbeat using atomic transaction tools.").strip()
    arguments = {
        "mode": "update" if automation_id else "create",
        "id": automation_id or None,
        "kind": "heartbeat",
        "destination": "thread",
        "targetThreadId": args.get("managerThreadId"),
        "name": automation_id or "project-manager-heartbeat",
        "prompt": prompt,
        "rrule": f"FREQ=MINUTELY;INTERVAL={interval}",
        "status": "ACTIVE",
    }
    arguments = {key: value for key, value in arguments.items() if value is not None}
    return _success(
        transactionId=transaction_id,
        transactionType="heartbeat_automation",
        hostActions=[{"tool": "automation_update", "resultKey": "automation", "required": True, "arguments": arguments}],
        pendingWrites={"forbiddenUntilFinalize": True, "ledgerFile": args.get("ledgerFile"), "ledgerEventsOnSuccess": ["automation_updated"]},
    )


def tool_manager_heartbeat_automation_finalize(args: dict[str, Any]) -> dict[str, Any]:
    transaction_id = str(args.get("transactionId") or _transaction_id("heartbeat_automation", args))
    host_results = _host_results(args)
    automation = host_results.get("automation") if isinstance(host_results.get("automation"), dict) else {}
    if not _host_result_success(automation):
        return _record_atomic_failure(args, "host_action_failed", host_results)
    automation_id = automation.get("automationId") or args.get("automationId")
    event = _append_transaction_event(
        args,
        "automation_updated",
        {
            "transactionId": transaction_id,
            "automationId": automation_id,
            "recordedAt": _now_iso8601(),
            "hostResult": automation,
        },
    )
    return _success(transactionId=transaction_id, automationId=automation_id, ledgerEvent=event)


TOOLS: dict[str, dict[str, Any]] = {
    "manager_tick": {
        "description": "Record a compact project-manager coordination tick.",
        "fn": tool_manager_tick,
        "schema": {
            "type": "object",
            "properties": {
                "assignmentId": {"type": "string"},
                "threadId": {"type": "string"},
                "observedState": {"type": "string"},
                "dispatchRequired": {"type": "boolean"},
                "stateFile": {"type": "string"},
                "stateJson": {"type": "string"},
                "projectRoot": {"type": "string"},
                "managerThreadId": {"type": "string"},
                "mode": {"type": "string"},
                "staleAfterMinutes": {"type": "integer"},
                "now": {"type": "string"},
                "note": {"type": "string"},
            },
        },
    },
    "manager_prepare_dispatch": {
        "description": "Prepare dispatch details without registering the dispatch.",
        "fn": tool_manager_prepare_dispatch,
        "schema": {
            "type": "object",
            "properties": {
                "assignmentId": {"type": "string"},
                "targetThreadId": {"type": "string"},
                "targetLabel": {"type": "string"},
                "assignmentPath": {"type": "string"},
                "goal": {"type": "string"},
                "constraints": {"type": "string"},
                "definitionOfDone": {"type": "string"},
                "packetRole": {"type": "string"},
                "workerModel": {"type": "string"},
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
            },
            "required": REQUIRED_DISPATCH_FIELDS,
        },
    },
    "manager_model_catalog": {
        "description": "Return the canonical project-manager model catalog and optionally write proxy-facing exports.",
        "fn": tool_manager_model_catalog,
        "schema": {
            "type": "object",
            "properties": {
                "includeDisabled": {"type": "boolean"},
                "writeExports": {"type": "boolean"},
            },
        },
    },
    "manager_model_advisory": {
        "description": "Recommend the best model for a packet role, task shape, and risk profile.",
        "fn": tool_manager_model_advisory,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "goal": {"type": "string"},
                "packetRole": {"type": "string"},
                "assignmentRisk": {"type": "string"},
                "packetShape": {"type": "string"},
                "needLongContext": {"type": "boolean"},
                "architectureSensitive": {"type": "boolean"},
                "multiFileDebugging": {"type": "boolean"},
                "repeatedImplementerBlockage": {"type": "boolean"},
                "priorFlashBlocked": {"type": "boolean"},
                "evidenceFile": {"type": "string"},
            },
        },
    },
    "manager_model_compatibility": {
        "description": "Explain route type, picker visibility, provider, and follow-up viability for a model.",
        "fn": tool_manager_model_compatibility,
        "schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "workerModel": {"type": "string"},
                "evidenceFile": {"type": "string"},
            },
        },
    },
    "manager_model_policy_packet": {
        "description": "Generate a concise policy update packet describing the current model roster, defaults, and boundaries.",
        "fn": tool_manager_model_policy_packet,
        "schema": {
            "type": "object",
            "properties": {
                "audience": {"type": "string"},
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "degradedModels": {"type": "array"},
                "evidenceFile": {"type": "string"},
            },
        },
    },
    "manager_model_export_health": {
        "description": "Validate canonical model exports, proxy-facing exports, disabled-model leakage, and source/cache export parity.",
        "fn": tool_manager_model_export_health,
        "schema": {"type": "object", "properties": {}},
    },
    "manager_model_policy_validate": {
        "description": "Validate model policy/profile overlays before they affect dispatch routing.",
        "fn": tool_manager_model_policy_validate,
        "schema": {"type": "object", "properties": {"profile": {"type": "string"}, "profileFile": {"type": "string"}, "workerModels": {"type": "array"}}},
    },
    "manager_model_policy_diff": {
        "description": "Compare current canonical model policy against live/exported/cache policy surfaces.",
        "fn": tool_manager_model_policy_diff,
        "schema": {"type": "object", "properties": {}},
    },
    "manager_model_cost_policy": {
        "description": "Return cheap/default/escalation/final-review model tiers and provider usage context.",
        "fn": tool_manager_model_cost_policy,
        "schema": {"type": "object", "properties": {}},
    },
    "manager_model_roster": {
        "description": "Describe manager/worker model roles, including DeepSeek worker models.",
        "fn": tool_manager_model_roster,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "managerModel": {"type": "string"},
            },
        },
    },
    "manager_project_profile": {
        "description": "Return optional project profile defaults without hard-coding project policy.",
        "fn": tool_manager_project_profile,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
            },
        },
    },
    "manager_load_project_profile": {
        "description": "Load a project-owned profile file and merge it with built-in defaults.",
        "fn": tool_manager_load_project_profile,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
            },
        },
    },
    "manager_score_worker_final": {
        "description": "Score worker-final quality beyond required-field validation.",
        "fn": tool_manager_score_worker_final,
        "schema": {
            "type": "object",
            "properties": {
                "workerFinalJson": {"type": "string"},
                "workerFinalPath": {"type": "string"},
            },
        },
    },
    "manager_prepare_thread_action": {
        "description": "Prepare a create/send/read thread action plan plus matching ledger event guidance.",
        "fn": tool_manager_prepare_thread_action,
        "schema": {
            "type": "object",
            "properties": {
                "actionType": {"type": "string"},
                "threadId": {"type": "string"},
                "prompt": {"type": "string"},
                "model": {"type": "string"},
                "thinking": {"type": "string"},
                "assignmentId": {"type": "string"},
                "assignmentPath": {"type": "string"},
                "goal": {"type": "string"},
                "constraints": {"type": "string"},
                "definitionOfDone": {"type": "string"},
                "workerModel": {"type": "string"},
                "managerModel": {"type": "string"},
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "targetType": {"type": "string"},
                "projectId": {"type": "string"},
                "environment": {"type": "string"},
                "directoryName": {"type": "string"},
            },
            "required": ["actionType"],
        },
    },
    "manager_recommend_recovery": {
        "description": "Recommend wait/read/recover/replace/takeover from current state and optional ledger.",
        "fn": tool_manager_recommend_recovery,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "stateFile": {"type": "string"},
                "stateJson": {"type": "string"},
                "ledgerFile": {"type": "string"},
                "dispatchRequired": {"type": "boolean"},
                "staleAfterMinutes": {"type": "integer"},
                "now": {"type": "string"},
            },
        },
    },
    "manager_restart_recovery": {
        "description": "Produce the safest restart recovery action plus handoff context.",
        "fn": tool_manager_restart_recovery,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "stateFile": {"type": "string"},
                "stateJson": {"type": "string"},
                "ledgerFile": {"type": "string"},
                "dispatchRequired": {"type": "boolean"},
                "staleAfterMinutes": {"type": "integer"},
                "now": {"type": "string"},
                "title": {"type": "string"},
            },
        },
    },
    "manager_generate_handoff_pack": {
        "description": "Generate a compact markdown handoff from project state and recent ledger events.",
        "fn": tool_manager_generate_handoff_pack,
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "stateFile": {"type": "string"},
                "stateJson": {"type": "string"},
                "ledgerFile": {"type": "string"},
                "projectRoot": {"type": "string"},
                "managerThreadId": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    "manager_compact_ledger": {
        "description": "Compact a JSONL ledger into a checkpoint with retained recent events.",
        "fn": tool_manager_compact_ledger,
        "schema": {
            "type": "object",
            "properties": {
                "ledgerFile": {"type": "string"},
                "outputFile": {"type": "string"},
                "keepLast": {"type": "integer"},
            },
            "required": ["ledgerFile"],
        },
    },
    "manager_update_worker_registry": {
        "description": "Create or update a project-owned worker lane registry.",
        "fn": tool_manager_update_worker_registry,
        "schema": {
            "type": "object",
            "properties": {
                "registryFile": {"type": "string"},
                "workerId": {"type": "string"},
                "worker": {"type": "object"},
                "threadId": {"type": "string"},
                "assignmentId": {"type": "string"},
                "model": {"type": "string"},
                "status": {"type": "string"},
                "lastProgressAt": {"type": "string"},
                "deliveryTurnId": {"type": "string"},
                "deliveryMessageId": {"type": "string"},
                "deliveryVerificationEvidence": {"type": "string"},
                "acknowledgedTurnId": {"type": "string"},
                "acknowledgedMessageId": {"type": "string"},
                "lastReadbackSummary": {"type": "string"},
                "updatedAt": {"type": "string"},
            },
            "required": ["registryFile", "workerId"],
        },
    },
    "manager_read_worker_registry": {
        "description": "Read a project-owned worker lane registry.",
        "fn": tool_manager_read_worker_registry,
        "schema": {
            "type": "object",
            "properties": {
                "registryFile": {"type": "string"},
                "workerId": {"type": "string"},
            },
            "required": ["registryFile"],
        },
    },
    "manager_notification_packet": {
        "description": "Generate a concise notification prompt for managers or workers after policy changes.",
        "fn": tool_manager_notification_packet,
        "schema": {
            "type": "object",
            "properties": {
                "audience": {"type": "string"},
                "pluginVersion": {"type": "string"},
                "models": {"type": "array"},
                "degradedModels": {"type": "array"},
                "evidenceFile": {"type": "string"},
            },
        },
    },
    "manager_append_ledger_event": {
        "description": "Append a project-manager event to a JSONL ledger.",
        "fn": tool_manager_append_ledger_event,
        "schema": {
            "type": "object",
            "properties": {
                "ledgerFile": {"type": "string"},
                "eventType": {"type": "string"},
                "eventId": {"type": "string"},
                "recordedAt": {"type": "string"},
                "projectRoot": {"type": "string"},
                "managerThreadId": {"type": "string"},
                "assignmentId": {"type": "string"},
                "threadId": {"type": "string"},
                "model": {"type": "string"},
                "payload": {"type": "object"},
            },
            "required": ["ledgerFile", "eventType"],
        },
    },
    "manager_read_ledger": {
        "description": "Read recent project-manager JSONL ledger events.",
        "fn": tool_manager_read_ledger,
        "schema": {
            "type": "object",
            "properties": {
                "ledgerFile": {"type": "string"},
                "eventType": {"type": "string"},
                "assignmentId": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["ledgerFile"],
        },
    },
    "manager_ledger_summary": {
        "description": "Summarize project-manager JSONL ledger state.",
        "fn": tool_manager_ledger_summary,
        "schema": {
            "type": "object",
            "properties": {
                "ledgerFile": {"type": "string"},
            },
            "required": ["ledgerFile"],
        },
    },
    "manager_prepare_worker_thread": {
        "description": "Prepare a create_thread request for a managed worker thread.",
        "fn": tool_manager_prepare_worker_thread,
        "schema": {
            "type": "object",
            "properties": {
                "assignmentId": {"type": "string"},
                "assignmentPath": {"type": "string"},
                "goal": {"type": "string"},
                "constraints": {"type": "string"},
                "definitionOfDone": {"type": "string"},
                "workerModel": {"type": "string"},
                "managerModel": {"type": "string"},
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "thinking": {"type": "string"},
                "title": {"type": "string"},
                "targetType": {"type": "string"},
                "projectId": {"type": "string"},
                "environment": {"type": "string"},
                "directoryName": {"type": "string"},
            },
            "required": ["assignmentId", "assignmentPath", "goal", "constraints", "definitionOfDone"],
        },
    },
    "manager_select_worker_model": {
        "description": "Select the worker model from project policy, defaulting to DeepSeek Flash and escalating to Pro only for higher-risk slices.",
        "fn": tool_manager_select_worker_model,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "workerModel": {"type": "string"},
                "assignmentRisk": {"type": "string"},
                "packetShape": {"type": "string"},
                "architectureSensitive": {"type": "boolean"},
            },
        },
    },
    "manager_verified_dispatch": {
        "description": "Prepare or finalize a fail-closed verified worker dispatch, writing ledger/registry state only after readback confirms a visible new turn.",
        "fn": tool_manager_verified_dispatch,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "registryFile": {"type": "string"},
                "ledgerFile": {"type": "string"},
                "projectRoot": {"type": "string"},
                "managerThreadId": {"type": "string"},
                "workerId": {"type": "string"},
                "assignmentId": {"type": "string"},
                "assignmentPath": {"type": "string"},
                "goal": {"type": "string"},
                "constraints": {"type": "string"},
                "definitionOfDone": {"type": "string"},
                "threadId": {"type": "string"},
                "prompt": {"type": "string"},
                "workerModel": {"type": "string"},
                "dispatchSucceeded": {"type": "boolean"},
                "deliveryVerified": {"type": "boolean"},
                "observedThreadId": {"type": "string"},
                "visibleTurnAt": {"type": "string"},
                "observedTurnId": {"type": "string"},
                "observedMessageId": {"type": "string"},
                "deliveryVerificationEvidence": {"type": "string"},
                "readbackSummary": {"type": "string"},
            },
            "required": ["assignmentId", "assignmentPath", "goal", "constraints", "definitionOfDone"],
        },
    },
    "manager_replace_dead_lane": {
        "description": "Prepare or finalize a verified replacement for a dead or unreadable worker lane.",
        "fn": tool_manager_replace_dead_lane,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "registryFile": {"type": "string"},
                "ledgerFile": {"type": "string"},
                "projectRoot": {"type": "string"},
                "managerThreadId": {"type": "string"},
                "workerId": {"type": "string"},
                "deadWorkerId": {"type": "string"},
                "deadThreadId": {"type": "string"},
                "deadReferenceReason": {"type": "string"},
                "assignmentId": {"type": "string"},
                "assignmentPath": {"type": "string"},
                "goal": {"type": "string"},
                "constraints": {"type": "string"},
                "definitionOfDone": {"type": "string"},
                "workerModel": {"type": "string"},
                "dispatchSucceeded": {"type": "boolean"},
                "deliveryVerified": {"type": "boolean"},
                "observedThreadId": {"type": "string"},
                "visibleTurnAt": {"type": "string"},
                "observedTurnId": {"type": "string"},
                "observedMessageId": {"type": "string"},
                "deliveryVerificationEvidence": {"type": "string"},
                "readbackSummary": {"type": "string"},
            },
            "required": ["deadThreadId", "deadReferenceReason", "assignmentId", "assignmentPath", "goal", "constraints", "definitionOfDone"],
        },
    },
    "manager_environment_health": {
        "description": "Check project-manager plugin, model routing, ledger/registry paths, MCP log path, and heartbeat readiness.",
        "fn": tool_manager_environment_health,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "projectRoot": {"type": "string"},
                "ledgerFile": {"type": "string"},
                "registryFile": {"type": "string"},
                "heartbeatIntervalMinutes": {"type": "integer"},
                "wrapperSmokeTimeoutSeconds": {"type": "integer"},
                "logTailLines": {"type": "integer"},
                "scanOrphanProcesses": {"type": "boolean"},
                "cleanupOrphans": {"type": "boolean"},
                "scanHostHealth": {"type": "boolean"},
                "scanCodexDesktopLogs": {"type": "boolean"},
                "codexDesktopLogFiles": {"type": "integer"},
                "codexDesktopLogTailChars": {"type": "integer"},
                "evidenceFile": {"type": "string"},
            },
        },
    },
    "manager_repair_plan": {
        "description": "Return exact operator-safe repair steps for degraded health findings without mutating state.",
        "fn": tool_manager_repair_plan,
        "schema": {"type": "object", "properties": {"profile": {"type": "string"}, "profileFile": {"type": "string"}}},
    },
    "manager_self_repair": {
        "description": "Run safe local project-manager repair steps: cleanup stale MCP runtime buildup, refresh install wiring, and re-check health.",
        "fn": tool_manager_self_repair,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "projectRoot": {"type": "string"},
                "ledgerFile": {"type": "string"},
                "registryFile": {"type": "string"},
            },
        },
    },
    "manager_health_snapshot": {
        "description": "Return a compact JSON health snapshot suitable for pasting into manager threads after crashes.",
        "fn": tool_manager_health_snapshot,
        "schema": {"type": "object", "properties": {"profile": {"type": "string"}, "profileFile": {"type": "string"}, "audience": {"type": "string"}}},
    },
    "manager_loaded_turn_recovery_packet": {
        "description": "Generate the canonical packet that tells a stale already-loaded turn how to rebind project-manager MCP on the next fresh turn or heartbeat.",
        "fn": tool_manager_loaded_turn_recovery_packet,
        "schema": {
            "type": "object",
            "properties": {
                "audience": {"type": "string"},
                "pluginVersion": {"type": "string"},
                "trigger": {"type": "string"},
            },
        },
    },
    "manager_loaded_turn_rescue_plan": {
        "description": "Prepare a same-thread rescue plan that sends a fresh rebind follow-up into a stale manager thread and then verifies the new turn is visible.",
        "fn": tool_manager_loaded_turn_rescue_plan,
        "schema": {
            "type": "object",
            "properties": {
                "managerThreadId": {"type": "string"},
                "threadId": {"type": "string"},
                "reason": {"type": "string"},
                "resumeInstruction": {"type": "string"},
                "audience": {"type": "string"},
                "pluginVersion": {"type": "string"},
                "trigger": {"type": "string"},
                "transactionId": {"type": "string"},
                "ledgerFile": {"type": "string"},
            },
            "required": ["managerThreadId"],
        },
    },
    "manager_registry_maintenance": {
        "description": "Archive dead, replaced, or completed workers out of the active lane registry.",
        "fn": tool_manager_registry_maintenance,
        "schema": {
            "type": "object",
            "properties": {
                "registryFile": {"type": "string"},
                "archiveDeadReferences": {"type": "boolean"},
                "archiveReplacedWorkers": {"type": "boolean"},
                "archiveCompletedWorkers": {"type": "boolean"},
                "recordedAt": {"type": "string"},
            },
            "required": ["registryFile"],
        },
    },
    "manager_operational_audit": {
        "description": "Score project-manager lane health, worker attention, and next operator actions from registry and ledger state.",
        "fn": tool_manager_operational_audit,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "registryFile": {"type": "string"},
                "ledgerFile": {"type": "string"},
                "staleAfterMinutes": {"type": "integer"},
                "now": {"type": "string"},
            },
            "required": ["registryFile"],
        },
    },
    "manager_operator_runbook": {
        "description": "Translate transport-health operator actions into concrete human recovery steps.",
        "fn": tool_manager_operator_runbook,
        "schema": {
            "type": "object",
            "properties": {
                "recommendedOperatorAction": {"type": "string"},
            },
        },
    },
    "manager_cross_project_summary": {
        "description": "Summarize multiple project-manager ledgers, registries, and worker lists into one dashboard payload.",
        "fn": tool_manager_cross_project_summary,
        "schema": {
            "type": "object",
            "properties": {
                "projects": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["projects"],
        },
    },
    "manager_cross_project_dashboard": {
        "description": "Render a manager-facing multi-project dashboard payload with cards, ranked projects, operator queue, and markdown.",
        "fn": tool_manager_cross_project_dashboard,
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "now": {"type": "string"},
                "includeEnvironmentHealth": {"type": "boolean"},
                "projects": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["projects"],
        },
    },
    "manager_project_readiness_score": {
        "description": "Score a project across transport, model policy, registry evidence, ledger freshness, worker progress, and automation readiness.",
        "fn": tool_manager_project_readiness_score,
        "schema": {"type": "object", "properties": {"registryFile": {"type": "string"}, "ledgerFile": {"type": "string"}, "includeEnvironmentHealth": {"type": "boolean"}}, "required": ["registryFile"]},
    },
    "manager_next_best_action": {
        "description": "Rank the next best operator action across multiple project-manager projects.",
        "fn": tool_manager_next_best_action,
        "schema": {"type": "object", "properties": {"projects": {"type": "array", "items": {"type": "object"}}}, "required": ["projects"]},
    },
    "manager_operator_digest": {
        "description": "Generate a short Markdown operator digest across multiple project-manager projects.",
        "fn": tool_manager_operator_digest,
        "schema": {"type": "object", "properties": {"projects": {"type": "array", "items": {"type": "object"}}}, "required": ["projects"]},
    },
    "manager_heartbeat_bootstrap": {
        "description": "Generate a recurring manager-heartbeat prompt plus ledger and registry setup checklist.",
        "fn": tool_manager_heartbeat_bootstrap,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "projectRoot": {"type": "string"},
                "managerThreadId": {"type": "string"},
                "ledgerFile": {"type": "string"},
                "registryFile": {"type": "string"},
                "heartbeatIntervalMinutes": {"type": "integer"},
                "automationId": {"type": "string"},
                "maintenanceEveryHeartbeats": {"type": "integer"},
            },
            "required": ["projectRoot", "managerThreadId"],
        },
    },
    "manager_automation_rollout_helper": {
        "description": "Prepare rollout packets for live manager threads, including updated heartbeat prompts, notification messages, and ledger event plans.",
        "fn": tool_manager_automation_rollout_helper,
        "schema": {
            "type": "object",
            "properties": {
                "pluginVersion": {"type": "string"},
                "releaseNotes": {"type": "string"},
                "targets": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["targets"],
        },
    },
    "manager_rollout_execution_bundle": {
        "description": "Prepare fail-closed rollout execution bundles that package exact thread-message, heartbeat-automation, and post-success ledger action plans.",
        "fn": tool_manager_rollout_execution_bundle,
        "schema": {
            "type": "object",
            "properties": {
                "pluginVersion": {"type": "string"},
                "releaseNotes": {"type": "string"},
                "targets": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["targets"],
        },
    },
    "manager_release_checklist": {
        "description": "Produce the project-manager release gate checklist with source/cache/wrapper/export validation commands.",
        "fn": tool_manager_release_checklist,
        "schema": {"type": "object", "properties": {"sourceRoot": {"type": "string"}, "cacheRoot": {"type": "string"}, "pythonExe": {"type": "string"}}},
    },
    "manager_register_dispatch_after_send": {
        "description": "Register a dispatch only after send_message_to_thread succeeds.",
        "fn": tool_manager_register_dispatch_after_send,
        "schema": {
            "type": "object",
            "properties": {
                "sendSucceeded": {"type": "boolean"},
                "assignmentId": {"type": "string"},
                "targetThreadId": {"type": "string"},
                "targetLabel": {"type": "string"},
                "assignmentPath": {"type": "string"},
                "managerThreadId": {"type": "string"},
                "promptSummary": {"type": "string"},
                "sourceFinalId": {"type": "string"},
                "runId": {"type": "string"},
                "candidateHash": {"type": "string"},
            },
            "required": ["sendSucceeded", *REQUIRED_DISPATCH_FIELDS],
        },
    },
    "manager_register_worker_final": {
        "description": "Register a worker final and validate its required fields.",
        "fn": tool_manager_register_worker_final,
        "schema": {
            "type": "object",
            "properties": {
                "workerFinalJson": {"type": "string"},
                "workerFinalPath": {"type": "string"},
            },
        },
    },
    "manager_summarize_thread_observation": {
        "description": "Summarize a thread observation into compact text.",
        "fn": tool_manager_summarize_thread_observation,
        "schema": {
            "type": "object",
            "properties": {
                "observationText": {"type": "string"},
            },
            "required": ["observationText"],
        },
    },
    "manager_model_pressure_summary": {
        "description": "Summarize per-model reliability evidence, recent failures, and degraded routing status.",
        "fn": tool_manager_model_pressure_summary,
        "schema": {
            "type": "object",
            "properties": {
                "evidenceFile": {"type": "string"},
                "proxyLogFile": {"type": "string"},
                "writeEvidence": {"type": "boolean"},
                "observations": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
        },
    },
    "manager_recent_events": {
        "description": "Summarize recent MCP logs, proxy route events, model pressure evidence, and export hashes.",
        "fn": tool_manager_recent_events,
        "schema": {"type": "object", "properties": {"limit": {"type": "integer"}, "proxyLogFile": {"type": "string"}, "evidenceFile": {"type": "string"}}},
    },
    "manager_crash_forensics_pack": {
        "description": "Gather a compact crash forensics pack with versions, logs, proxy/model export hashes, and active model policy.",
        "fn": tool_manager_crash_forensics_pack,
        "schema": {"type": "object", "properties": {"profile": {"type": "string"}, "profileFile": {"type": "string"}, "limit": {"type": "integer"}}},
    },
    "manager_model_transport_health": {
        "description": "Check model transport health: caching, version drift, model availability.",
        "fn": tool_manager_model_transport_health,
        "schema": {
            "type": "object",
            "properties": {
                "profile": {"type": "string"},
                "profileFile": {"type": "string"},
                "wrapperSmokeTimeoutSeconds": {"type": "integer"},
                "logTailLines": {"type": "integer"},
                "scanOrphanProcesses": {"type": "boolean"},
                "evidenceFile": {"type": "string"},
            },
        },
    },
    "manager_worker_canary": {
        "description": "Check if a known worker thread is still reachable via registry readback fields.",
        "fn": tool_manager_worker_canary,
        "schema": {
            "type": "object",
            "properties": {
                "workerId": {"type": "string"},
                "registryFile": {"type": "string"},
            },
            "required": ["workerId", "registryFile"],
        },
    },
    "manager_lane_health_from_readback": {
        "description": "Classify lane health from a fresh readback observation, distinguishing silent-after-delivery from healthy progress.",
        "fn": tool_manager_lane_health_from_readback,
        "schema": {
            "type": "object",
            "properties": {
                "registryFile": {"type": "string"},
                "workerId": {"type": "string"},
                "hasVisibleTurn": {"type": "boolean"},
                "visibleTurnAt": {"type": "string"},
                "deliveryTurnId": {"type": "string"},
                "deliveryMessageId": {"type": "string"},
                "deliveryVerificationEvidence": {"type": "string"},
                "acknowledgedTurnId": {"type": "string"},
                "acknowledgedMessageId": {"type": "string"},
                "threadState": {"type": "string"},
                "readbackSummary": {"type": "string"},
                "laneClass": {"type": "string"},
                "assistantAuthored": {"type": "boolean"},
                "workerFinalDetected": {"type": "boolean"},
                "blockedDetected": {"type": "boolean"},
                "deadReference": {"type": "boolean"},
                "staleReadback": {"type": "boolean"},
                "writeRegistry": {"type": "boolean"},
            },
            "required": ["registryFile", "workerId"],
        },
    },
    "manager_registry_reconcile": {
        "description": "Reconcile registry evidence gating: verify active/healthy workers have evidence sources.",
        "fn": tool_manager_registry_reconcile,
        "schema": {
            "type": "object",
            "properties": {
                "registryFile": {"type": "string"},
                "recordedAt": {"type": "string"},
            },
            "required": ["registryFile"],
        },
    },
    "manager_accept_worker_final_and_plan_next": {
        "description": "Accept a worker final, validate it, register in registry/ledger, and plan the next phase.",
        "fn": tool_manager_accept_worker_final_and_plan_next,
        "schema": {
            "type": "object",
            "properties": {
                "workerFinalJson": {"type": "string"},
                "workerFinalPath": {"type": "string"},
                "workerId": {"type": "string"},
                "registryFile": {"type": "string"},
                "ledgerFile": {"type": "string"},
                "recordedAt": {"type": "string"},
                "eventId": {"type": "string"},
            },
        },
    },
    "manager_dispatch_transaction_plan": {
        "description": "Plan or finalize a fail-closed dispatch transaction spanning send/create, readback, registry, and ledger state.",
        "fn": tool_manager_dispatch_transaction_plan,
        "schema": {"type": "object", "properties": {"assignmentId": {"type": "string"}, "assignmentPath": {"type": "string"}, "goal": {"type": "string"}, "constraints": {"type": "string"}, "definitionOfDone": {"type": "string"}, "dispatchSucceeded": {"type": "boolean"}, "deliveryVerified": {"type": "boolean"}}},
    },
    "manager_atomic_dispatch_prepare": {
        "description": "Prepare an atomic host-action dispatch transaction without mutating registry or ledger state.",
        "fn": tool_manager_atomic_dispatch_prepare,
        "schema": {"type": "object", "properties": {"assignmentId": {"type": "string"}, "assignmentPath": {"type": "string"}, "goal": {"type": "string"}, "constraints": {"type": "string"}, "definitionOfDone": {"type": "string"}, "registryFile": {"type": "string"}, "ledgerFile": {"type": "string"}, "workerId": {"type": "string"}}},
    },
    "manager_atomic_dispatch_finalize": {
        "description": "Finalize an atomic dispatch transaction from host results, writing state only after verified readback.",
        "fn": tool_manager_atomic_dispatch_finalize,
        "schema": {"type": "object", "properties": {"transactionId": {"type": "string"}, "hostResults": {"type": "object"}, "registryFile": {"type": "string"}, "ledgerFile": {"type": "string"}, "workerId": {"type": "string"}, "assignmentId": {"type": "string"}}},
    },
    "manager_atomic_lane_recovery_prepare": {
        "description": "Prepare an atomic dead-lane replacement transaction without mutating registry or ledger state.",
        "fn": tool_manager_atomic_lane_recovery_prepare,
        "schema": {"type": "object", "properties": {"deadThreadId": {"type": "string"}, "deadReferenceReason": {"type": "string"}, "assignmentId": {"type": "string"}, "assignmentPath": {"type": "string"}, "goal": {"type": "string"}, "constraints": {"type": "string"}, "definitionOfDone": {"type": "string"}}},
    },
    "manager_atomic_lane_recovery_finalize": {
        "description": "Finalize an atomic dead-lane replacement transaction from host results.",
        "fn": tool_manager_atomic_lane_recovery_finalize,
        "schema": {"type": "object", "properties": {"transactionId": {"type": "string"}, "hostResults": {"type": "object"}, "deadWorkerId": {"type": "string"}, "deadThreadId": {"type": "string"}, "registryFile": {"type": "string"}, "ledgerFile": {"type": "string"}}},
    },
    "manager_loaded_turn_rescue_finalize": {
        "description": "Finalize a same-thread loaded-turn rescue after send/readback proves a fresh follow-up turn is visible.",
        "fn": tool_manager_loaded_turn_rescue_finalize,
        "schema": {"type": "object", "properties": {"transactionId": {"type": "string"}, "managerThreadId": {"type": "string"}, "hostResults": {"type": "object"}, "ledgerFile": {"type": "string"}, "reason": {"type": "string"}}},
    },
    "manager_host_action_result_validate": {
        "description": "Validate host action results for fail-closed atomic transaction finalization.",
        "fn": tool_manager_host_action_result_validate,
        "schema": {"type": "object", "properties": {"transactionId": {"type": "string"}, "hostResults": {"type": "object"}}},
    },
    "manager_thread_supervisor_plan": {
        "description": "Prepare bounded read_thread host actions for supervising active worker lanes.",
        "fn": tool_manager_thread_supervisor_plan,
        "schema": {"type": "object", "properties": {"registryFile": {"type": "string"}, "ledgerFile": {"type": "string"}, "maxWorkers": {"type": "integer"}}, "required": ["registryFile"]},
    },
    "manager_thread_supervisor_finalize": {
        "description": "Finalize thread supervision from readback results, classifying stale/silent/dead/thinking lanes.",
        "fn": tool_manager_thread_supervisor_finalize,
        "schema": {"type": "object", "properties": {"transactionId": {"type": "string"}, "registryFile": {"type": "string"}, "ledgerFile": {"type": "string"}, "hostResults": {"type": "object"}}, "required": ["registryFile", "hostResults"]},
    },
    "manager_heartbeat_automation_plan": {
        "description": "Prepare a fail-closed heartbeat automation host-action transaction.",
        "fn": tool_manager_heartbeat_automation_plan,
        "schema": {"type": "object", "properties": {"automationId": {"type": "string"}, "managerThreadId": {"type": "string"}, "heartbeatIntervalMinutes": {"type": "integer"}, "prompt": {"type": "string"}, "ledgerFile": {"type": "string"}}},
    },
    "manager_heartbeat_automation_finalize": {
        "description": "Finalize heartbeat automation host results and record automation_updated only after success.",
        "fn": tool_manager_heartbeat_automation_finalize,
        "schema": {"type": "object", "properties": {"transactionId": {"type": "string"}, "automationId": {"type": "string"}, "ledgerFile": {"type": "string"}, "hostResults": {"type": "object"}}},
    },
    "manager_transaction_journal_record": {
        "description": "Append a durable dispatcher transaction journal record for prepare, host result, readback, finalize, or failure phases.",
        "fn": tool_manager_transaction_journal_record,
        "schema": {"type": "object", "properties": {"journalFile": {"type": "string"}, "transactionId": {"type": "string"}, "transactionType": {"type": "string"}, "phase": {"type": "string"}, "hostActions": {"type": "array"}, "hostResults": {"type": "object"}, "registryFile": {"type": "string"}, "ledgerFile": {"type": "string"}, "failureReason": {"type": "string"}}},
    },
    "manager_transaction_journal_read": {
        "description": "Read and compact the durable dispatcher transaction journal, returning incomplete transactions first.",
        "fn": tool_manager_transaction_journal_read,
        "schema": {"type": "object", "properties": {"journalFile": {"type": "string"}, "transactionId": {"type": "string"}, "limit": {"type": "integer"}, "ledgerFile": {"type": "string"}, "projectRoot": {"type": "string"}}},
    },
    "manager_transaction_resume_plan": {
        "description": "Plan the next safe dispatcher action for an incomplete transaction without mutating registry or ledger success state.",
        "fn": tool_manager_transaction_resume_plan,
        "schema": {"type": "object", "properties": {"journalFile": {"type": "string"}, "transactionId": {"type": "string"}, "ledgerFile": {"type": "string"}, "projectRoot": {"type": "string"}}},
    },
    "manager_transaction_close": {
        "description": "Close a durable dispatcher transaction as finalized, failed, or abandoned with required evidence.",
        "fn": tool_manager_transaction_close,
        "schema": {"type": "object", "properties": {"journalFile": {"type": "string"}, "transactionId": {"type": "string"}, "closeStatus": {"type": "string"}, "finalizeEvidence": {"type": "object"}, "finalizeResult": {"type": "object"}, "failureReason": {"type": "string"}}},
    },
    "manager_dispatcher_runbook": {
        "description": "Return the canonical Codex-side dispatcher sequence for atomic transactions, journaling, resume, finalize, and close.",
        "fn": tool_manager_dispatcher_runbook,
        "schema": {"type": "object", "properties": {"transactionType": {"type": "string"}, "hostActions": {"type": "array"}}},
    },
    "manager_worker_packet_contract": {
        "description": "Generate a role/model-specific worker packet contract with evidence, scope, reasoning, and escalation boundaries.",
        "fn": tool_manager_worker_packet_contract,
        "schema": {"type": "object", "properties": {"packetRole": {"type": "string"}, "workerModel": {"type": "string"}, "thinking": {"type": "string"}}},
    },
    "manager_successor_packet_plan": {
        "description": "Given an accepted strict worker final, determine the deterministic successor packet or manager action.",
        "fn": tool_manager_successor_packet_plan,
        "schema": {"type": "object", "properties": {"workerFinalJson": {"type": "string"}, "workerFinalPath": {"type": "string"}, "packetRole": {"type": "string"}, "profile": {"type": "string"}, "profileFile": {"type": "string"}}},
    },
}


def _send(message: dict[str, Any]) -> None:
    try:
        if isinstance(message, dict):
            if "result" in message:
                _log_event("response_sent", requestId=message.get("id"), hasResult=True)
            elif "error" in message:
                _log_event("response_sent", requestId=message.get("id"), hasError=True, error=message.get("error"))
    except Exception:
        pass
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _jsonrpc_error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _tool_list() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": meta["description"],
            "inputSchema": meta["schema"],
        }
        for name, meta in TOOLS.items()
    ]


def _call_tool(params: Mapping[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if not isinstance(arguments, Mapping):
        raise ValueError("Invalid params")
    if name not in TOOLS:
        raise ValueError(f"Unknown tool: {name}")
    _log_event(
        "tool_call_start",
        tool=str(name),
        argumentKeys=sorted(str(key) for key in arguments.keys()),
    )
    result = TOOLS[name]["fn"](arguments)
    _log_event(
        "tool_call_complete",
        tool=str(name),
        status=result.get("status"),
        resultKeys=sorted(str(key) for key in result.keys()) if isinstance(result, Mapping) else [],
    )
    return {
        "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
        "isError": result.get("status") == "failed",
    }


def _handle_request(request: Any) -> None:
    if not isinstance(request, Mapping):
        _send(_jsonrpc_error_response(None, -32600, "Invalid Request"))
        return

    method = request.get("method")
    request_id = request.get("id")
    try:
        params = request.get("params")
        if isinstance(params, Mapping):
            param_keys = sorted(str(key) for key in params.keys())
        else:
            param_keys = []
        _log_event(
            "request_received",
            method=str(method),
            requestId=request_id,
            paramKeys=param_keys,
        )
    except Exception:
        pass
    try:
        if method == "initialize":
            _send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "project-manager",
                            "version": PLUGIN_VERSION,
                        },
                    },
                }
            )
            return
        if method in ("notifications/initialized", "$/cancelRequest"):
            return
        if method == "resources/list":
            _send({"jsonrpc": "2.0", "id": request_id, "result": {"resources": []}})
            return
        if method == "resources/templates/list":
            _send({"jsonrpc": "2.0", "id": request_id, "result": {"resourceTemplates": []}})
            return
        if method == "prompts/list":
            _send({"jsonrpc": "2.0", "id": request_id, "result": {"prompts": []}})
            return
        if method == "ping":
            _send({"jsonrpc": "2.0", "id": request_id, "result": {}})
            return
        if method == "tools/list":
            _send({"jsonrpc": "2.0", "id": request_id, "result": {"tools": _tool_list()}})
            return
        if method == "tools/call":
            params = request.get("params") or {}
            if not isinstance(params, Mapping):
                _send(_jsonrpc_error_response(request_id, -32602, "Invalid params"))
                return
            _send({"jsonrpc": "2.0", "id": request_id, "result": _call_tool(params)})
            return
        if request_id is not None:
            _send(_jsonrpc_error_response(request_id, -32601, f"Method not found: {method}"))
    except ValueError as exc:
        if request_id is not None and str(exc) == "Invalid params":
            _send(_jsonrpc_error_response(request_id, -32602, "Invalid params"))
    except Exception as exc:  # pragma: no cover - defensive JSON-RPC envelope
        _log_event("request_exception", method=str(method), error=str(exc), traceback=traceback.format_exc())
        if request_id is not None:
            _send(_jsonrpc_error_response(request_id, -32000, str(exc)))


def main() -> None:
    install_state = _plugin_install_state()
    wrapper_start_event = "server_start"
    if str(os.environ.get("PROJECT_MANAGER_WRAPPER_SUPPRESS_SERVER_START") or "").strip() == "1":
        wrapper_start_event = "server_start_suppressed"
    _log_event(
        wrapper_start_event,
        pluginVersion=PLUGIN_VERSION,
        pluginRoot=str(PLUGIN_ROOT),
        canonicalPluginVersion=CANONICAL_PLUGIN_VERSION,
        canonicalPluginRoot=str(CANONICAL_PLUGIN_ROOT),
        resolvedPluginRoot=install_state.get("resolvedPluginRoot"),
        resolvedPluginVersion=install_state.get("resolvedPluginVersion"),
        resolvedWrapperPath=os.environ.get("PROJECT_MANAGER_WRAPPER_PATH") or install_state.get("resolvedWrapperPath"),
        resolvedWrapperHash=os.environ.get("PROJECT_MANAGER_WRAPPER_HASH") or install_state.get("resolvedWrapperHash"),
        wrapperLaunchReason=os.environ.get("PROJECT_MANAGER_WRAPPER_LAUNCH_REASON") or "stdio_initialize",
        wrapperParentPid=os.environ.get("PROJECT_MANAGER_WRAPPER_PARENT_PID"),
        sourceAlignmentStatus=install_state.get("sourceAlignmentStatus"),
        argv=sys.argv,
    )
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            _log_event("json_decode_error", error=str(exc))
            _send(_jsonrpc_error_response(None, -32700, str(exc)))
            continue
        _handle_request(request)
    _log_event("server_stop")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - pythonw-safe startup diagnostics
        _log_event("fatal_exception", error=str(exc), traceback=traceback.format_exc())
        raise
