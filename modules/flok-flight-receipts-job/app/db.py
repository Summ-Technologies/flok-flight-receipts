from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

def setup_db_session(db_uri: str):
    db_engine = create_engine(db_uri, poolclass=NullPool)
    Session = sessionmaker(bind=db_engine)
    session = Session()
    return session