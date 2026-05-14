from __future__ import annotations

from contracts.automation import AutomationFireRequest, AutomationFormReadRequest, AutomationPreviewRequest
from contracts.common import ServiceHealth as HealthResponse
from contracts.discovery import DiscoveryPlanRequest, DiscoveryRunResponse, DiscoveryScanRequest
from contracts.generation import GenerationPackageRequest, GenerationPackageResponse
from contracts.graph import GraphStatsRequest
from contracts.profile import (
    ProfileImportRequest,
    ProfileIngestGithubRequest,
    ProfileIngestLinkedInRequest,
    ProfileIngestPortfolioRequest,
    ProfileIngestResumeRequest,
)
from contracts.ranking import RankingFeedbackRequest, RankingRequest, RankingResponse

__all__ = [
    "AutomationFireRequest",
    "AutomationFormReadRequest",
    "AutomationPreviewRequest",
    "DiscoveryPlanRequest",
    "DiscoveryRunResponse",
    "DiscoveryScanRequest",
    "GenerationPackageRequest",
    "GenerationPackageResponse",
    "GraphStatsRequest",
    "HealthResponse",
    "ProfileImportRequest",
    "ProfileIngestGithubRequest",
    "ProfileIngestLinkedInRequest",
    "ProfileIngestPortfolioRequest",
    "ProfileIngestResumeRequest",
    "RankingFeedbackRequest",
    "RankingRequest",
    "RankingResponse",
]
