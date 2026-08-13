param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl,
    [string]$ReleaseVersion = "restore-verification"
)

$ErrorActionPreference = "Stop"

if ($DatabaseUrl -match "localhost|@db:|scholarship:scholarship") {
    throw "Refusing a non-isolated database URL. Restore verification requires distinct credentials and host."
}

$env:APP_ENV = "development"
$env:APP_DATABASE_URL = $DatabaseUrl
$env:APP_RELEASE_VERSION = $ReleaseVersion
$env:APP_JWT_SECRET = "restore-verification-secret-at-least-32-characters"

& .\.venv\Scripts\python.exe -m alembic upgrade head
& .\.venv\Scripts\python.exe -c "from app.core.config import get_settings; get_settings.cache_clear(); from app.main import app; assert app.title; print('restore schema and application import verified')"
