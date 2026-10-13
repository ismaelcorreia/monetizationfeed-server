import sys
import os

# Add src to path if running directly
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from ingestion.article_fetcher import ArticleFetcher


def main():

    fetcher = ArticleFetcher()

    url = "https://www.bbc.com/news"

    urls = fetcher.fetch_source_urls(url)

    print(f"Encontradas: {len(urls)}")

    if not urls:
        return

    article = fetcher.fetch(urls[0])

    if article is None:
        print("Falha ao extrair")
        return

    print()

    print("Título:")
    print(article.title)

    print()

    print("Autores:")
    print(article.authors)

    print()

    print("Idioma:")
    print(article.language)

    print()

    print("Data:")
    print(article.publish_date)

    print()

    print("Imagem principal:")
    print(article.top_image)

    print()

    print("Keywords:")
    print(article.keywords)

    print()

    print("Texto:")

    print(article.text[:1000])


if __name__ == "__main__":
    main()