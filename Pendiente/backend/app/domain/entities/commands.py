from typing import Literal

CommandType = Literal["PING", "STATUS", "TELEMETRY", "START_MISSION"]
COMMAND_TYPES = ("PING", "STATUS", "TELEMETRY", "START_MISSION")


class CommandConflict(ValueError):
    pass


class CommandUnavailable(ValueError):
    pass
