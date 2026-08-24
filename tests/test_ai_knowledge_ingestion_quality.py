from services.ai.retrieval.ingestion import extract_sections


def test_html_ingestion_prefers_article_content_and_removes_navigation_noise():
    payload = b"""
    <html><body>
      <header>Site banner</header>
      <nav>Products Pricing Login</nav>
      <main>
        <article>
          <h1>Receiving inventory</h1>
          <p>Verify the manifest and purchase order before receiving the package.</p>
        </article>
      </main>
      <footer>Privacy Careers Copyright</footer>
      <script>window.secretNoise = true;</script>
    </body></html>
    """
    sections = extract_sections("guide.html", payload)
    assert len(sections) == 1
    text = sections[0][1]
    assert "Receiving inventory" in text
    assert "Verify the manifest" in text
    assert "Products Pricing Login" not in text
    assert "Privacy Careers" not in text
    assert "secretNoise" not in text
