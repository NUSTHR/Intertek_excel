from app.core.errors import UploadValidationError
from app.ports.pdf_parser import PdfParser, PdfParserProfile, PdfParserRuntimeStatus


class PdfParserProfileRegistry:
    """Owns configured PDF parsers and the active parser profile."""

    def __init__(
        self,
        *,
        parser: PdfParser,
        parser_status: PdfParserRuntimeStatus | None = None,
        parser_profiles: dict[str, PdfParser] | None = None,
        parser_profile_statuses: dict[str, PdfParserRuntimeStatus] | None = None,
        parser_profile_descriptors: list[PdfParserProfile] | None = None,
        default_parser_profile_id: str | None = None,
    ) -> None:
        configured_status = parser_status or PdfParserRuntimeStatus(
            backend=parser.__class__.__name__,
            available=True,
            detail="PDF parser instance is configured.",
        )
        requested_default_profile_id = (
            default_parser_profile_id
            or configured_status.backend
            or parser.__class__.__name__
        )
        self._parsers = parser_profiles or {requested_default_profile_id: parser}
        self._statuses = parser_profile_statuses or {
            requested_default_profile_id: configured_status
        }
        self._default_profile_id = (
            requested_default_profile_id
            if requested_default_profile_id in self._parsers
            else next(iter(self._parsers))
        )
        self._selected_profile_id = self._default_profile_id
        self._descriptors = parser_profile_descriptors or [
            PdfParserProfile(
                profile_id=profile_id,
                label=profile_id,
                kind="local",
                status=self.status_for(profile_id),
                is_default=profile_id == self._default_profile_id,
            )
            for profile_id in self._parsers
        ]

    @property
    def selected_profile_id(self) -> str:
        return self._selected_profile_id

    def selected_status(self) -> PdfParserRuntimeStatus:
        return self.status_for(self._selected_profile_id)

    def list_profiles(self) -> list[PdfParserProfile]:
        selected = self._selected_profile_id
        profiles: list[PdfParserProfile] = []
        known_ids = {profile.profile_id for profile in self._descriptors}
        for profile in self._descriptors:
            profiles.append(
                PdfParserProfile(
                    profile_id=profile.profile_id,
                    label=profile.label,
                    kind=profile.kind,
                    status=self.status_for(profile.profile_id),
                    description=profile.description,
                    is_default=profile.profile_id == self._default_profile_id,
                    is_selected=profile.profile_id == selected,
                )
            )
        for profile_id in self._parsers:
            if profile_id in known_ids:
                continue
            profiles.append(
                PdfParserProfile(
                    profile_id=profile_id,
                    label=profile_id,
                    kind="local",
                    status=self.status_for(profile_id),
                    is_default=profile_id == self._default_profile_id,
                    is_selected=profile_id == selected,
                )
            )
        return profiles

    def select(self, profile_id: str) -> list[PdfParserProfile]:
        normalized_profile_id = profile_id.strip()
        if normalized_profile_id not in self._parsers:
            raise UploadValidationError("unknown PDF parser profile")
        status = self.status_for(normalized_profile_id)
        if not status.available:
            raise UploadValidationError(
                f"PDF parser profile '{normalized_profile_id}' is unavailable: {status.detail}"
            )
        self._selected_profile_id = normalized_profile_id
        return self.list_profiles()

    def parser_for(self, profile_id: str | None = None) -> PdfParser:
        normalized_profile_id = (profile_id or self._selected_profile_id).strip()
        parser = self._parsers.get(normalized_profile_id)
        if parser is not None:
            return parser
        fallback = self._parsers.get(self._default_profile_id)
        if fallback is not None:
            return fallback
        return next(iter(self._parsers.values()))

    def status_for(self, profile_id: str | None = None) -> PdfParserRuntimeStatus:
        normalized_profile_id = (profile_id or self._selected_profile_id).strip()
        status = self._statuses.get(normalized_profile_id)
        if status is not None:
            return status
        if normalized_profile_id in self._parsers:
            return PdfParserRuntimeStatus(
                backend=normalized_profile_id,
                available=True,
                detail="PDF parser profile is configured.",
            )
        fallback = self._statuses.get(self._default_profile_id)
        if fallback is not None:
            return fallback
        return PdfParserRuntimeStatus(
            backend=normalized_profile_id or "unknown",
            available=False,
            detail="PDF parser profile is not configured.",
        )
