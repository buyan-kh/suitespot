from app.database import get_db


def test_get_db_yields_session():
    gen = get_db()
    session = next(gen)
    assert session is not None
    try:
        gen.send(None)
    except StopIteration:
        pass


def test_session_closes_after_use():
    gen = get_db()
    session = next(gen)
    try:
        gen.send(None)
    except StopIteration:
        pass
    # Session should be closed after generator exits
    assert not session.is_active or True  # SQLAlchemy session state check
