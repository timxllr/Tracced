"""Pytest Fixtures für isolierte Tests mit SQLite In-Memory Datenbank."""
import pytest
import pytest_asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.database import Base, get_db
from app.main import app
from app.models import User, MeasurementSeries, Reading, SeriesType
from app.auth import hash_password, create_session_token, generate_csrf_token

# Test-Datenbank SQLite In-Memory
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Erstellt eine frische In-Memory Datenbank pro Testfall."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()
        
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession):
    """HTTPX AsyncClient mit überschriebener Datenbank-Dependency."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
        
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> User:
    """Legt einen Testbenutzer an."""
    user = User(
        id=uuid.uuid4(),
        email="tester@example.com",
        hashed_password=hash_password("GeheimesPasswort123!"),
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def second_user(db_session: AsyncSession) -> User:
    """Legt einen zweiten Benutzer an (zur Prüfung der Datenisolation)."""
    user = User(
        id=uuid.uuid4(),
        email="hacker@example.com",
        hashed_password=hash_password("AnderesPasswort456!"),
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(test_user: User):
    """Liefert Session-Token und passenden CSRF-Header für Testanfragen."""
    token = create_session_token(test_user.id)
    csrf = generate_csrf_token(token)
    return {
        "headers": {"X-CSRF-Token": csrf},
        "cookies": {"tracced_session": token}
    }
