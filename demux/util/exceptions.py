# future exception hierarchy
# https://github.com/NorwegianVeterinaryInstitute/DemultiplexRawSequenceData/issues/150


class RemoteError(RuntimeError):
    """Base class for remote-side failures."""

class RemoteHashMismatchError(RemoteError):
    """Remote file hash does not match local checksum."""
