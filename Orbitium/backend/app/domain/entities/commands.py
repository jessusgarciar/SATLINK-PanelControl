from typing import Literal

CommandType = Literal["PING", "STATUS", "TELEMETRY", "START_MISSION", "RELEASE_NOW"]
COMMAND_TYPES = ("PING", "STATUS", "TELEMETRY", "START_MISSION", "RELEASE_NOW")


class CommandConflict(ValueError):
    pass


class CommandUnavailable(ValueError):
    pass
