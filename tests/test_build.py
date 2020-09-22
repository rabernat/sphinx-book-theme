from pathlib import Path
from shutil import copytree, rmtree

from bs4 import BeautifulSoup
import pytest
from sphinx.errors import ThemeError
from sphinx.testing.util import SphinxTestApp
from sphinx.testing.path import path as sphinx_path


path_tests = Path(__file__).parent.resolve()
path_base = path_tests.joinpath("sites", "base")


class SphinxBuild:
    def __init__(self, app: SphinxTestApp, src: Path):
        self.app = app
        self.src = src

    def build(self, assert_pass=True):
        self.app.build()
        assert self.warnings == "", self.status
        return self

    @property
    def status(self):
        return self.app._status.getvalue()

    @property
    def warnings(self):
        return self.app._warning.getvalue()

    @property
    def outdir(self):
        return Path(self.app.outdir)

    def html_tree(self, *path):
        path_page = self.outdir.joinpath(*path)
        if not path_page.exists():
            raise ValueError(f"{path_page} does not exist")
        return BeautifulSoup(path_page.read_text("utf8"), "html.parser")

    def clean(self):
        self.app.cleanup()
        rmtree(self.src.parent, self.src.name)


@pytest.fixture()
def sphinx_build_factory(make_app, tmp_path):
    def _func(src_folder, **kwargs):
        copytree(path_tests / "sites" / src_folder, tmp_path / src_folder)
        app = make_app(
            srcdir=sphinx_path(str((tmp_path / src_folder).absolute())), **kwargs
        )
        return SphinxBuild(app, tmp_path / src_folder)

    yield _func


def test_build_book(sphinx_build_factory, file_regression):
    """Test building the base book template and config."""
    sphinx_build = sphinx_build_factory("base")  # type: SphinxBuild
    sphinx_build.build(assert_pass=True)
    assert (sphinx_build.outdir / "index.html").exists(), sphinx_build.outdir.glob("*")

    # Check for correct kernel name in jupyter notebooks
    kernels_expected = {
        "ntbk.html": "python3",
        "ntbk_octave.html": "octave",
        "ntbk_julia.html": "julia-1.4",
    }
    for filename, kernel in kernels_expected.items():
        ntbk_html = sphinx_build.html_tree("section1", filename)
        thebe_config = ntbk_html.find("script", attrs={"type": "text/x-thebe-config"})
        kernel_name = 'kernelName: "{}",'.format(kernel)
        if kernel_name not in thebe_config.prettify():
            raise AssertionError(f"{kernel_name} not in {kernels_expected}")

    # Check a few components that should be true on each page
    index_html = sphinx_build.html_tree("index.html")
    sidebar = index_html.find_all(attrs={"class": "bd-sidebar"})[0]
    file_regression.check(sidebar.prettify(), extension=".html", encoding="utf8")

    # Opengraph should not be in the HTML because we have no baseurl specified
    assert (
        '<meta property="og:url"         content="https://blah.com/foo/section1/ntbk.html" />'  # noqa E501
        not in str(index_html)
    )
    # Edit button should not be on page
    assert '<a class="edit-button"' not in str(index_html)
    # Title should be just text, no HTML
    assert "Index with code in title" in str(index_html)
    # Check navbar numbering
    sidebar_ntbk = sphinx_build.html_tree("section1", "ntbk.html").find(
        "nav", id="bd-docs-nav"
    )
    # Pages and sub-pages should be numbered
    assert "1. Page 1" in str(sidebar_ntbk)
    assert "3.1. Section 1 page1" in str(sidebar_ntbk)
    # Check opengraph metadata
    html_escaped = sphinx_build.html_tree("page1.html")
    escaped_description = html_escaped.find("meta", property="og:description")
    file_regression.check(
        escaped_description.prettify(),
        basename="escaped_description",
        extension=".html",
        encoding="utf8",
    )


def test_navbar_options_home_page_in_toc(sphinx_build_factory):

    sphinx_build = sphinx_build_factory(
        "base", confoverrides={"html_theme_options.home_page_in_toc": True}
    ).build(
        assert_pass=True
    )  # type: SphinxBuild
    navbar = sphinx_build.html_tree("section1", "ntbk.html").find(
        "nav", id="bd-docs-nav"
    )
    assert "Index with code in title" in str(navbar)


def test_navbar_options_single_page(sphinx_build_factory):
    sphinx_build = sphinx_build_factory(
        "base", confoverrides={"html_theme_options.single_page": True}
    ).build(
        assert_pass=True
    )  # type: SphinxBuild
    sidebar = sphinx_build.html_tree("section1", "ntbk.html").find(
        "div", id="site-navigation"
    )
    assert len(sidebar.find_all("div")) == 0
    assert "col-md-2" in sidebar.attrs["class"]


@pytest.mark.parametrize(
    "option,value",
    [
        ("extra_navbar", "<div>EXTRA NAVBAR</div>"),
        ("navbar_footer_text", "<div>EXTRA NAVBAR</div>"),
        ("extra_footer", "<div>EXTRA FOOTER</div>"),
    ],
)
def test_navbar_options(sphinx_build_factory, option, value):
    sphinx_build = sphinx_build_factory(
        "base", confoverrides={f"html_theme_options.{option}": value}
    ).build(
        assert_pass=True
    )  # type: SphinxBuild
    assert value in str(sphinx_build.html_tree("section1", "ntbk.html"))


def test_navbar_options_expand_sections(sphinx_build_factory):
    """Explicitly expanded sections are expanded when not active."""
    sphinx_build = sphinx_build_factory(
        "base",
        confoverrides={"html_theme_options.expand_sections": "section1/index"},
    ).build(
        assert_pass=True
    )  # type: SphinxBuild
    sidebar = sphinx_build.html_tree("section1", "ntbk.html").find_all(
        attrs={"class": "bd-sidebar"}
    )[0]
    assert "Section 1 page1" in str(sidebar)


def test_header_info(sphinx_build_factory):
    confoverrides = {
        "html_baseurl": "https://blah.com/foo/",
        "html_logo": str(path_tests.parent.joinpath("docs", "_static", "logo.png")),
    }
    sphinx_build = sphinx_build_factory("base", confoverrides=confoverrides).build(
        assert_pass=True
    )

    # opengraph is generated when baseurl is given
    header = sphinx_build.html_tree("section1", "ntbk.html").find("head")
    assert (
        '<meta content="https://blah.com/foo/section1/ntbk.html" property="og:url"/>'
        in str(header)
    )
    assert (
        '<meta content="https://blah.com/foo/_static/logo.png" property="og:image"/>'
        in str(header)
    )


def test_topbar_edit_buttons_on(sphinx_build_factory, file_regression):
    confoverrides = {
        "html_theme_options.use_edit_page_button": True,
        "html_theme_options.use_repository_button": True,
        "html_theme_options.use_issues_button": True,
    }
    sphinx_build = sphinx_build_factory("base", confoverrides=confoverrides).build(
        assert_pass=True
    )

    source_btns = sphinx_build.html_tree("section1", "ntbk.html").find_all(
        "div", attrs={"class": "sourcebuttons"}
    )[0]
    file_regression.check(source_btns.prettify(), extension=".html", encoding="utf8")


def test_topbar_edit_buttons_off(sphinx_build_factory, file_regression):
    confoverrides = {
        "html_theme_options.use_edit_page_button": False,
        "html_theme_options.use_repository_button": False,
        "html_theme_options.use_issues_button": True,
    }
    sphinx_build = sphinx_build_factory("base", confoverrides=confoverrides).build(
        assert_pass=True
    )

    source_btns = sphinx_build.html_tree("section1", "ntbk.html").find_all(
        "div", attrs={"class": "sourcebuttons"}
    )[0]
    file_regression.check(source_btns.prettify(), extension=".html", encoding="utf8")


def test_topbar_launchbtns(sphinx_build_factory, file_regression):
    """Test launch buttons."""
    sphinx_build = sphinx_build_factory("base").build(assert_pass=True)
    launch_btns = sphinx_build.html_tree("section1", "ntbk.html").find_all(
        "div", attrs={"class": "dropdown-buttons"}
    )[1]
    file_regression.check(launch_btns.prettify(), extension=".html", encoding="utf8")


def test_repo_custombranch(sphinx_build_factory, file_regression):
    """Test custom branch for launch buttons."""
    sphinx_build = sphinx_build_factory(
        "base", confoverrides={"html_theme_options.repository_branch": "foo"}
    ).build(assert_pass=True)
    launch_btns = sphinx_build.html_tree("section1", "ntbk.html").find_all(
        "div", attrs={"class": "dropdown-buttons"}
    )[1]
    file_regression.check(launch_btns.prettify(), extension=".html", encoding="utf8")


def test_singlehtml(sphinx_build_factory):
    """Test building with a single HTML page."""
    sphinx_build = sphinx_build_factory("base", buildername="singlehtml").build(
        assert_pass=True
    )
    assert (sphinx_build.outdir / "index.html").exists(), sphinx_build.outdir.glob("*")


def test_missing_title(sphinx_build_factory):
    """Test building with a book w/ no title on the master page."""
    with pytest.raises(ThemeError, match="Landing page missing a title: index"):
        sphinx_build_factory("notitle").build()
