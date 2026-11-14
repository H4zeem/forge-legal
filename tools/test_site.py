"""Validate the static legal site with Python's standard library."""
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.tags = []
        self.ids = []
        self.links = []
        self.version = None
        self.lang = None
        self.feed(path.read_text())

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        self.tags.append((tag, attrs))
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'html':
            self.lang = attrs.get('lang')
        if tag in ('a', 'link'):
            self.links.append(attrs.get('href', ''))
        if tag == 'meta' and attrs.get('name') == 'forge-app-version':
            self.version = attrs.get('content')


class LegalSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = [Page(ROOT / name) for name in
                     ('index.html', 'privacy.html', 'terms.html', 'support.html')]

    def test_document_structure_and_accessibility(self):
        for page in self.pages:
            with self.subTest(page=page.path.name):
                for tag in ('html', 'head', 'body', 'title', 'main', 'h1'):
                    self.assertEqual(sum(t == tag for t, _ in page.tags), 1, tag)
                self.assertEqual(page.lang, 'en')
                self.assertEqual(len(page.ids), len(set(page.ids)))
                self.assertIn('main-content', page.ids)
                self.assertIn('#main-content', page.links)
                self.assertTrue(any(t == 'meta' and a.get('name') == 'viewport'
                                    for t, a in page.tags))

    def test_internal_links_and_fragments_resolve(self):
        for page in self.pages:
            for href in page.links:
                with self.subTest(page=page.path.name, href=href):
                    url = urlsplit(href)
                    if url.scheme or url.netloc:
                        continue
                    destination = ROOT / (unquote(url.path) or page.path.name)
                    if destination.is_dir():
                        destination /= 'index.html'
                    self.assertTrue(destination.is_file(), str(destination))
                    self.assertTrue(destination.resolve().is_relative_to(ROOT))
                    if url.fragment:
                        self.assertIn(unquote(url.fragment), Page(destination).ids)

    def test_links_use_safe_schemes(self):
        for page in self.pages:
            for href in page.links:
                self.assertIn(urlsplit(href).scheme, ('', 'https', 'mailto'))
                self.assertNotIn('\\', href)

    def test_brand_returns_home(self):
        for page in self.pages:
            brands = [a for t, a in page.tags if t == 'a' and a.get('class') == 'brand']
            self.assertEqual(len(brands), 1)
            self.assertEqual(brands[0]['href'], './')
            self.assertTrue(brands[0].get('aria-label'))

    def test_navigation_current_page_matches_document(self):
        for page in self.pages:
            current = [a['href'] for t, a in page.tags if t == 'a' and a.get('aria-current') == 'page']
            self.assertEqual(current, [] if page.path.name == 'index.html' else [page.path.name])

    def test_every_page_describes_same_app_version(self):
        version = self.pages[0].version
        self.assertRegex(version or '', r'^\d+\.\d+\.\d+$')
        for page in self.pages:
            self.assertEqual(page.version, version)
        self.assertIn(f'FORGE {version}', (ROOT / 'index.html').read_text())

    def test_policies_have_matching_effective_dates(self):
        dates = [re.search(r'Effective date: ([^<]+)', (ROOT / name).read_text())[1]
                 for name in ('privacy.html', 'terms.html')]
        self.assertEqual(dates[0], dates[1])

    def test_removed_paid_logging_and_reward_claims_do_not_return(self):
        text = ' '.join(page.path.read_text() for page in self.pages)
        for obsolete in ('Pro or Max', 'requires a subscription to log',
                         'choose a rewarded ad', 'rewarded-ad claim',
                         'hashed installation identifier may be sent to AdMob'):
            self.assertNotIn(obsolete, text)


if __name__ == '__main__':
    unittest.main()
