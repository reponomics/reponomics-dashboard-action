"""Constants shared by GitHub collection modules."""

CONFIG_PATH = "config.yaml"

MAX_RETRIES = 3
RETRY_BACKOFF = 2
REQUEST_PACING_MIN_SECONDS = 0.5
REQUEST_PACING_MAX_SECONDS = 1.0
SECONDARY_LIMIT_FALLBACK_SECONDS = 60
NOT_FOUND_RETRIES = 2
TOKEN_VALIDATION_URL = "https://api.github.com/user"
APP_TOKEN_VALIDATION_URL = (
    "https://api.github.com/installation/repositories?per_page=1&page=1"
)
TOKEN_CREATION_URL = "".join(
    [
        "https://github.com/settings/personal-access-tokens/new",
        "?name=COLLECTION_TOKEN",
        "&description=Read%20repository%20data%20for%20Reponomics%20Dashboard",
        "&expires_in=366",
        "&administration=read",
    ]
)
REPO_DISCOVERY_URL = "https://api.github.com/user/repos"
APP_REPO_DISCOVERY_URL = "https://api.github.com/installation/repositories"
REPO_DISCOVERY_PAGE_SIZE = 100
CURRENT_REPOSITORY_ENV_KEYS = ("GITHUB_REPOSITORY", "GH_REPO")
