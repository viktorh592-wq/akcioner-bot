"""Tests for marketplace parsers."""

import pytest
from app.parsers.base import BaseParser, get_parser, ParseError


class MockParser(BaseParser):
    """Mock parser for testing."""
    
    marketplace = "test"
    url_patterns = [r"test\.com"]
    
    async def parse(self, url: str) -> dict:
        """Return mock parsed data."""
        return {
            "title": "Test Product",
            "price": 1000.0,
            "image_url": "https://test.com/image.jpg",
        }


def test_can_parse_url():
    """Test URL pattern matching."""
    parser = MockParser()
    
    assert parser.can_parse("https://test.com/product/123") is True
    assert parser.can_parse("http://test.com/item") is True
    assert parser.can_parse("https://example.com/product") is False


def test_extract_price():
    """Test price extraction from various formats."""
    parser = MockParser()
    
    # Russian format with spaces and ruble symbol
    assert parser._extract_price("1 234 ₽") == 1234.0
    
    # US format with comma separator
    assert parser._extract_price("1,234.56") == 1234.56
    
    # Russian format with comma as decimal
    assert parser._extract_price("1234,56 руб.") == 1234.56
    
    # Simple integer
    assert parser._extract_price("1000") == 1000.0
    
    # Invalid format
    assert parser._extract_price("not a price") is None


def test_get_parser_factory():
    """Test parser factory function."""
    # Should raise error for unsupported URL
    with pytest.raises(ParseError):
        get_parser("https://unsupported-marketplace.com/product")


@pytest.mark.asyncio
async def test_parser_base_methods():
    """Test base parser methods."""
    parser = MockParser()
    
    # Test User-Agent rotation
    assert parser.user_agent is not None
    assert len(parser.user_agent) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
