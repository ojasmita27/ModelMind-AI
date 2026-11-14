"""Guards that the test run can never damage a developer's real database."""
import tempfile
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import PROJECT_ROOT, get_settings
from tests.conftest import TEST_DATABASE_URL


def test_tests_use_the_isolated_database():
    # SQLite URLs render with OS-native separators; normalize before comparing.
    actual = get_settings().database_url.replace("\\", "/")
    expected = make_url(TEST_DATABASE_URL).render_as_string(hide_password=False).replace("\\", "/")
    assert actual == expected
    assert get_settings().environment == "test"


def test_default_test_database_is_a_temp_file_not_the_dev_database():
    url = make_url(get_settings().database_url)
    if url.get_backend_name() == "sqlite":
        path = Path(url.database).resolve()
        assert Path(tempfile.gettempdir()).resolve() in path.parents
        assert PROJECT_ROOT / "data" not in path.parents
    else:
        assert url.database.endswith("_test")
