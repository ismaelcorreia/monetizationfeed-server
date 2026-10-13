import sys
import os
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from ingestion.article_fetcher import ArticleFetcher, FetchedArticleData

def test_article_fetcher_init():
    fetcher = ArticleFetcher(language="pt", request_timeout=10)
    assert fetcher._language == "pt"
    assert fetcher._timeout == 10

def test_map_data():
    # Mocking internal _map to check if it returns the right dataclass
    class MockArticle:
        title = "Teste"
        text = "Conteúdo de teste"
        authors = ["Autor 1"]
        summary = "Sumário"
        top_image = "http://image.jpg"
        images = ["http://image.jpg"]
        publish_date = None
        meta_lang = "pt"
        keywords = ["news"]

    fetcher = ArticleFetcher()
    data = fetcher._map(MockArticle(), "http://test.com")
    
    assert isinstance(data, FetchedArticleData)
    assert data.title == "Teste"
    assert data.url == "http://test.com"
    assert data.language == "pt"

@pytest.mark.skip(reason="Requires internet access")
def test_fetch_real_url():
    fetcher = ArticleFetcher()
    url = "https://www.google.com" # Just to test connectivity/parser
    result = fetcher.fetch(url)
    assert result is not None
    assert result.url == url
