from app.adapters.pdf.fake_parser import FakePdfParser
from app.adapters.pdf.mineru_cloud_parser import MinerUCloudPdfParser, check_mineru_cloud_runtime
from app.adapters.pdf.mineru_parser import MinerUPdfParser, check_mineru_runtime
from app.core.config import Settings
from app.ports.pdf_parser import PdfParser, PdfParserProfile, PdfParserRuntimeStatus

LOCAL_MINERU_PROFILE_ID = "mineru-local"
MINERU_CLOUD_PROFILE_ID = "mineru-cloud"


def create_pdf_parser(settings: Settings) -> PdfParser:
    backend = settings.pdf_parser_backend.strip().lower()
    if backend == "mineru":
        return MinerUPdfParser(
            command=settings.mineru_command,
            timeout_seconds=settings.mineru_timeout_seconds,
            cli_backend=settings.mineru_cli_backend,
            extra_args=_split_cli_args(settings.mineru_extra_args),
        )
    return FakePdfParser()


def create_pdf_parser_profiles(settings: Settings) -> dict[str, PdfParser]:
    backend = settings.pdf_parser_backend.strip().lower()
    if backend == "mineru":
        return {
            LOCAL_MINERU_PROFILE_ID: create_local_mineru_parser(settings),
            MINERU_CLOUD_PROFILE_ID: create_mineru_cloud_parser(settings),
        }
    return {"fake": FakePdfParser()}


def create_local_mineru_parser(settings: Settings) -> MinerUPdfParser:
    return MinerUPdfParser(
        command=settings.mineru_command,
        timeout_seconds=settings.mineru_timeout_seconds,
        cli_backend=settings.mineru_cli_backend,
        extra_args=_split_cli_args(settings.mineru_extra_args),
    )


def create_mineru_cloud_parser(settings: Settings) -> MinerUCloudPdfParser:
    return MinerUCloudPdfParser(
        api_base_url=settings.mineru_cloud_api_base_url,
        api_token=settings.mineru_cloud_api_token,
        model_version=settings.mineru_cloud_model_version,
        timeout_seconds=settings.mineru_cloud_timeout_seconds,
        poll_interval_seconds=settings.mineru_cloud_poll_interval_seconds,
        language=settings.mineru_cloud_language,
        enable_formula=settings.mineru_cloud_enable_formula,
        enable_table=settings.mineru_cloud_enable_table,
        is_ocr=settings.mineru_cloud_is_ocr,
    )


def get_pdf_parser_status(settings: Settings) -> PdfParserRuntimeStatus:
    backend = settings.pdf_parser_backend.strip().lower()
    if backend == "mineru":
        status = check_mineru_runtime(command=settings.mineru_command)
        details = [status.detail]
        if settings.mineru_cli_backend.strip():
            details.append(f"CLI backend: {settings.mineru_cli_backend.strip()}.")
        extra_args = _split_cli_args(settings.mineru_extra_args)
        if extra_args:
            details.append(f"Extra CLI args: {' '.join(extra_args)}.")
        return PdfParserRuntimeStatus(
            backend=status.backend,
            available=status.available,
            command=status.command,
            version=status.version,
            detail=" ".join(detail for detail in details if detail),
        )
    if backend == "fake":
        return PdfParserRuntimeStatus(
            backend="fake",
            available=True,
            detail="Fake PDF parser is active for local development and tests.",
        )
    return PdfParserRuntimeStatus(
        backend=backend or "unknown",
        available=False,
        detail=f"Unsupported PDF parser backend '{settings.pdf_parser_backend}'.",
    )


def get_pdf_parser_profiles(settings: Settings) -> list[PdfParserProfile]:
    backend = settings.pdf_parser_backend.strip().lower()
    if backend == "mineru":
        local_status = _local_mineru_status(settings)
        cloud_status = _mineru_cloud_status(settings)
        return [
            PdfParserProfile(
                profile_id=LOCAL_MINERU_PROFILE_ID,
                label="Local MinerU",
                kind="local",
                status=local_status,
                description=(
                    "Runs the installed MinerU CLI on this workstation. Uses existing "
                    "model caches and does not require network access during parsing."
                ),
                is_default=True,
            ),
            PdfParserProfile(
                profile_id=MINERU_CLOUD_PROFILE_ID,
                label="MinerU Cloud",
                kind="cloud",
                status=cloud_status,
                description=(
                    "Uses MinerU official v4 cloud parsing with the vlm model, signed "
                    "upload URLs, batch polling, and result zip download."
                ),
            ),
        ]
    return [
        PdfParserProfile(
            profile_id="fake",
            label="Fake PDF Parser",
            kind="local",
            status=get_pdf_parser_status(settings),
            description="Development parser for tests and local UI work.",
            is_default=True,
        )
    ]


def get_default_pdf_parser_profile_id(settings: Settings) -> str:
    backend = settings.pdf_parser_backend.strip().lower()
    if backend == "mineru":
        return LOCAL_MINERU_PROFILE_ID
    if backend == "fake":
        return "fake"
    return backend or "unknown"


def _split_cli_args(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _local_mineru_status(settings: Settings) -> PdfParserRuntimeStatus:
    status = check_mineru_runtime(command=settings.mineru_command)
    details = [status.detail]
    if settings.mineru_cli_backend.strip():
        details.append(f"CLI backend: {settings.mineru_cli_backend.strip()}.")
    extra_args = _split_cli_args(settings.mineru_extra_args)
    if extra_args:
        details.append(f"Extra CLI args: {' '.join(extra_args)}.")
    return PdfParserRuntimeStatus(
        backend=LOCAL_MINERU_PROFILE_ID,
        available=status.available,
        command=status.command,
        version=status.version,
        detail=" ".join(detail for detail in details if detail),
    )


def _mineru_cloud_status(settings: Settings) -> PdfParserRuntimeStatus:
    status = check_mineru_cloud_runtime(
        api_base_url=settings.mineru_cloud_api_base_url,
        api_token=settings.mineru_cloud_api_token,
        model_version=settings.mineru_cloud_model_version,
    )
    if settings.mineru_cloud_access_key.strip() or settings.mineru_cloud_secret_key.strip():
        return PdfParserRuntimeStatus(
            backend=status.backend,
            available=status.available,
            command=status.command,
            version=status.version,
            detail=(
                status.detail
                + " MinerU official v4 parsing uses Bearer API Token; Access Key/Secret "
                "Key values are present but are not sent by this adapter."
            ),
        )
    return status
