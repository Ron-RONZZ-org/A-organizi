"""Service layer for A-organizi using CRUDService."""

from A_organizi.service.etikedo import EtikedoService, get_etikedo_service
from A_organizi.service.kalendaro import (
    CalendarService,
    EventService,
    get_evento_service,
    get_kalendaro_service,
)
from A_organizi.service.taglibro import TaglibroService, get_taglibro_service
from A_organizi.service.todo import TodoService, get_todo_service

__all__ = [
    "CalendarService",
    "EtikedoService",
    "EventService",
    "TaglibroService",
    "TodoService",
    "get_etikedo_service",
    "get_evento_service",
    "get_kalendaro_service",
    "get_taglibro_service",
    "get_todo_service",
]

