
import datetime as dt

from sqlalchemy import TypeDecorator, Integer, Float, Text

from ch2.lib.date import parse_datetime, parse_date


class Ordinal(TypeDecorator):

    impl = Integer

    def process_literal_param(self, date, dialect):
        if date is None:
            return date
        if isinstance(date, str):
            date = parse_date(date)
        return date.toordinal()

    process_bind_param = process_literal_param

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            return dt.date.fromordinal(value)


class Epoch(TypeDecorator):

    impl = Float

    def process_literal_param(self, datetime, dialect):
        if datetime is None:
            return datetime
        if isinstance(datetime, str):
            datetime = parse_datetime(datetime)
        elif isinstance(datetime, dt.date):
            datetime = dt.datetime.combine(datetime, dt.time())
        elif isinstance(datetime, int) or isinstance(datetime, float):
            datetime = dt.datetime.utcfromtimestamp(datetime)
        return datetime.replace(tzinfo=dt.timezone.utc).timestamp()

    process_bind_param = process_literal_param

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            return dt.datetime.utcfromtimestamp(value)


class Cls(TypeDecorator):

    impl = Text

    def process_literal_param(self, cls, dialect):
        if cls is None:
            return cls
        if not isinstance(cls, str) and not isinstance(cls, type):
            cls = type(cls)
        if isinstance(cls, type):
            cls = cls.__name__
        return cls

    process_bind_param = process_literal_param

    def process_result_value(self, value, dialect):
        return value
