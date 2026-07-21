"""Provider selection policy stays explicit and testable."""
import pytest

from app.models import ImageProviderName
from app.services.provider_selection import (
    ProviderUnavailableError,
    list_provider_options,
    resolve_image_provider,
)


def test_auto_prefers_azure_when_configured():
    gemini = object()
    azure = object()

    resolved = resolve_image_provider(ImageProviderName.AUTO, gemini, azure)

    assert resolved.name is ImageProviderName.AZURE
    assert resolved.provider is azure


def test_auto_falls_back_to_gemini():
    gemini = object()
    resolved = resolve_image_provider(ImageProviderName.AUTO, gemini, None)
    assert resolved.name is ImageProviderName.GEMINI
    assert resolved.provider is gemini


def test_unconfigured_explicit_provider_fails_honestly():
    with pytest.raises(ProviderUnavailableError, match="Azure"):
        resolve_image_provider(ImageProviderName.AZURE, object(), None)
    with pytest.raises(ProviderUnavailableError, match="agent-mediated"):
        resolve_image_provider(ImageProviderName.HYPERAGENT, object(), object())


def test_provider_options_expose_experimental_and_availability():
    options = {item.id: item for item in list_provider_options(azure_available=True)}
    assert options[ImageProviderName.AUTO].available is True
    assert options[ImageProviderName.AZURE].available is True
    assert options[ImageProviderName.HYPERAGENT].experimental is True
    assert options[ImageProviderName.HYPERAGENT].available is False
