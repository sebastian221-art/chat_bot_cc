"""
services/content_matching.py

Reconoce si el cliente mencionó un evento, sorteo o promoción de
marketing específico por nombre en su mensaje — mismo mecanismo que ya
usa store_transfer.py para tiendas (nombre completo o palabra
distintiva), para poder mandar la foto correcta cuando preguntan por
algo puntual.
"""
import re
from sqlalchemy.orm import Session
from models.event import Event
from models.raffle import Raffle
from models.marketing import Marketing

STOPWORDS_ES = {"la", "el", "los", "las", "de", "del", "y", "un", "una", "en", "por", "para"}


def _significant_words(name: str) -> list[str]:
    words = re.findall(r"[a-záéíóúñü']+", name.lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS_ES]


def _contains_word(message: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", message) is not None


def find_event_by_message(db: Session, message: str) -> Event | None:
    msg = message.lower()
    events = db.query(Event).all()

    exact = [e for e in events if e.name.lower() in msg]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    word_matches = [e for e in events if any(_contains_word(msg, w) for w in _significant_words(e.name))]
    if len(word_matches) == 1:
        return word_matches[0]
    return None


def find_raffle_by_message(db: Session, message: str) -> Raffle | None:
    msg = message.lower()
    raffles = db.query(Raffle).filter(Raffle.active == True).all()

    exact = [r for r in raffles if r.name.lower() in msg]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    word_matches = [r for r in raffles if any(_contains_word(msg, w) for w in _significant_words(r.name))]
    if len(word_matches) == 1:
        return word_matches[0]
    return None


def find_marketing_by_message(db: Session, message: str) -> Marketing | None:
    msg = message.lower()
    promos = db.query(Marketing).filter(Marketing.active == True).all()

    exact = [m for m in promos if m.title.lower() in msg]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    word_matches = [m for m in promos if any(_contains_word(msg, w) for w in _significant_words(m.title))]
    if len(word_matches) == 1:
        return word_matches[0]
    return None