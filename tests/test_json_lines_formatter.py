# Test puri per JsonLinesFormatter (logs/events.jsonl): una riga JSON valida
# per record, con i campi base e gli extra del chiamante. Non deve mai
# solleva un'eccezione, anche con input anomalo.
import json
import logging

from src.core.logging_setup import JsonLinesFormatter


def _make_record(msg="hello", level=logging.INFO, args=(), extra=None, exc_info=None):
    record = logging.LogRecord(
        name="test.jsonlines", level=level, pathname="test_file.py", lineno=10,
        msg=msg, args=args, exc_info=exc_info,
    )
    if extra:
        for k, v in extra.items():
            setattr(record, k, v)
    return record


def test_basic_record_has_base_fields():
    record = _make_record(msg="ciao mondo", level=logging.INFO)
    payload = json.loads(JsonLinesFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.jsonlines"
    assert payload["msg"] == "ciao mondo"
    assert "ts" in payload
    assert "thread" in payload


def test_extra_fields_are_included():
    record = _make_record(msg="evento", extra={"event_type": "session_start", "pid": 123})
    payload = json.loads(JsonLinesFormatter().format(record))
    assert payload["event_type"] == "session_start"
    assert payload["pid"] == 123


def test_non_serializable_extra_does_not_raise():
    class Weird:
        def __str__(self):
            return "weird-obj"

    record = _make_record(msg="evento", extra={"event_type": "x", "obj": Weird()})
    payload = json.loads(JsonLinesFormatter().format(record))
    assert payload["obj"] == "weird-obj"  # serializzato con default=str


def test_exception_info_includes_traceback():
    import sys
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        exc_info = sys.exc_info()
        record = _make_record(msg="errore", level=logging.ERROR, exc_info=exc_info)
    payload = json.loads(JsonLinesFormatter().format(record))
    assert "RuntimeError: boom" in payload["exc"]


def test_non_string_msg_is_handled():
    record = _make_record(msg=12345)
    payload = json.loads(JsonLinesFormatter().format(record))
    assert payload["msg"] == "12345"


def test_formatter_never_raises_on_message_format_mismatch():
    # getMessage() solleva TypeError se gli args non bastano per i
    # placeholder %s nel messaggio: il formatter deve intercettarlo e
    # produrre comunque una riga JSON valida (con _formatter_error=True).
    record = _make_record(msg="valore %s %s", args=("only_one",))
    payload = json.loads(JsonLinesFormatter().format(record))
    assert payload.get("_formatter_error") is True
    assert payload["level"] == "INFO"
