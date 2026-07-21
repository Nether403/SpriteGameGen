"""Provider selection policy stays explicit and testable."""
import pytest

from app.models import ImageProviderName
from app.services.provider_selection import (
    ProviderRegistry,
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


def test_auto_fails_when_no_image_provider_is_configured():
    with pytest.raises(ProviderUnavailableError, match="No image provider"):
        resolve_image_provider(ImageProviderName.AUTO, None, None)


def test_explicit_gemini_fails_when_unconfigured():
    with pytest.raises(ProviderUnavailableError, match="Gemini"):
        resolve_image_provider(ImageProviderName.GEMINI, None, object())


def test_unconfigured_explicit_provider_fails_honestly():
    with pytest.raises(ProviderUnavailableError, match="Azure"):
        resolve_image_provider(ImageProviderName.AZURE, object(), None)
    with pytest.raises(ProviderUnavailableError, match="agent-mediated"):
        resolve_image_provider(ImageProviderName.HYPERAGENT, object(), object())


def test_provider_options_expose_experimental_and_availability():
    options = {
        item.id: item
        for item in list_provider_options(
            azure_available=True, gemini_available=False
        )
    }
    assert options[ImageProviderName.AUTO].available is True
    assert options[ImageProviderName.AZURE].available is True
    assert options[ImageProviderName.GEMINI].available is False
    assert options[ImageProviderName.HYPERAGENT].experimental is True
    assert options[ImageProviderName.HYPERAGENT].available is False


def test_provider_registry_owns_selection_options_and_prompt_enhancer():
    gemini = object()
    azure = object()
    registry = ProviderRegistry(gemini=gemini, azure=azure)

    assert registry.resolve(ImageProviderName.AUTO).provider is azure
    assert registry.prompt_enhancer is gemini
    assert {
        option.id: option.available for option in registry.options()
    }[ImageProviderName.GEMINI]
